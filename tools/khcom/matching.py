"""Source-bound occupancy and linker relocation facts for a matching US rebuild.

An ABS32 relocation is stronger evidence than a pointer-shaped word. Neither
this map nor absence of a relocation proves absence of calculated references.
No occupied bytes or trailing cartridge padding are advertised as free space.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import struct

from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError
from elftools.elf.relocation import RelocationSection

from .errors import KhcomError
from .io import read_file
from .matching_assets import classify_encoded_words

ROM_BASE = 0x08000000
ROM_CAPACITY = 0x2000000
BASELINE_SHA256 = '6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d'


def identity(path: Path, data: bytes) -> dict:
    return {'path': str(path.absolute()), 'size': len(data), 'sha256': sha256(data).hexdigest()}


def parse_sections(text: str) -> list[dict]:
    """Parse GNU ld 2.10 input-section placement records, including wrapped names."""
    records = []
    pending = None
    pattern = re.compile(r'^ (\.\S+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(\S+\.o)$')
    wrapped = re.compile(r'^\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(\S+\.o)$')
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if match:
            name, address, size, owner = match.groups()
            records.append({'section': name, 'address': int(address, 16), 'size': int(size, 16), 'owner': owner})
            pending = None
        elif re.fullmatch(r' \.\S+', line):
            pending = line.strip()
        elif pending and (match := wrapped.fullmatch(line)):
            address, size, owner = match.groups()
            records.append({'section': pending, 'address': int(address, 16), 'size': int(size, 16), 'owner': owner})
            pending = None
        else:
            pending = None
    if not records:
        raise KhcomError('matching_map', 'Mapa não contém seções de entrada reconhecidas.')
    seen = set()
    for record in records:
        key = record['owner'], record['section']
        if key in seen:
            raise KhcomError('matching_map', 'Seção de objeto ambígua no mapa.', key=key)
        seen.add(key)
    return records


def _elf(data: bytes) -> ELFFile:
    try:
        elf = ELFFile(BytesIO(data))
    except (ELFError, struct.error) as error:
        raise KhcomError('matching_elf', 'ELF inválido ou truncado.', reason=str(error)) from error
    if elf.elfclass != 32 or not elf.little_endian or elf['e_machine'] != 'EM_ARM':
        raise KhcomError('matching_elf', 'É necessário um ELF ARM de 32 bits little-endian.')
    return elf


def _symbols(elf: ELFFile) -> list[dict]:
    table = elf.get_section_by_name('.symtab')
    if table is None:
        raise KhcomError('matching_symbols', 'ELF sem tabela de símbolos.')
    return [{'name': symbol.name, 'address': symbol['st_value'], 'size': symbol['st_size'],
             'type': symbol['st_info']['type'], 'binding': symbol['st_info']['bind']}
            for symbol in table.iter_symbols() if symbol.name and symbol['st_shndx'] != 'SHN_UNDEF']


def _containers(symbols: list[dict], address: int) -> list[dict]:
    # Owner attribution is performed only for selected words, not every relocation.
    contained = [s for s in symbols if s['type'] in ('STT_OBJECT', 'STT_FUNC', 'STT_LOPROC') and
                 (s['address'] & ~1 if s['type'] == 'STT_FUNC' else s['address']) <= address <
                 (s['address'] & ~1 if s['type'] == 'STT_FUNC' else s['address']) + s['size']]
    return sorted(contained, key=lambda s: (s['size'], s['name']))


def branch_displacement(instruction: bytes, kind: int) -> int:
    """Decode the supported ARMv4T relocation field, preserving its signed addend."""
    if len(instruction) != 4:
        raise KhcomError('matching_branch_range', 'Instrução de desvio truncada.')
    if kind == 10:
        first, second = struct.unpack('<HH', instruction)
        if first & 0xf800 != 0xf000 or second & 0xf800 != 0xf800:
            raise KhcomError('matching_thumb_branch', 'Relocação Thumb não contém BL ARMv4T suportado.')
        value = ((first & 0x7ff) << 12) | ((second & 0x7ff) << 1)
        return value - (1 << 23) if value & (1 << 22) else value
    if kind == 1:
        value = struct.unpack('<I', instruction)[0]
        if value & 0x0e000000 != 0x0a000000:
            raise KhcomError('matching_arm_branch', 'Relocação ARM não contém B/BL suportado.')
        value = (value & 0xffffff) << 2
        return value - (1 << 26) if value & (1 << 25) else value
    raise KhcomError('matching_branch_kind', 'Tipo de relocação de desvio não suportado.')


def audit_matching(rom_path: Path, rebuild_path: Path, elf_path: Path, map_path: Path,
                   source_root: Path, candidate_offsets: list[int] | None = None) -> dict:
    """Produce canonical linked facts and bind every input to its SHA-256.

    Only exact baseline rebuilds are admitted. The executable ROM section must
    equal the ROM after the gbafix header, and the explicit ROM tail must be FF.
    Each emitted ABS32 edge is checked against the linked ROM word. ARM/Thumb
    branch relocations are checked separately and never treated as data pointers.
    """
    rom = read_file(rom_path, ROM_CAPACITY)
    return audit_matching_bytes(rom, rom_identity=identity(rom_path, rom), rebuild_path=rebuild_path,
                                elf_path=elf_path, map_path=map_path, source_root=source_root,
                                candidate_offsets=candidate_offsets)


def audit_matching_bytes(rom: bytes, *, rom_identity: dict, rebuild_path: Path, elf_path: Path,
                         map_path: Path, source_root: Path, candidate_offsets: list[int] | None = None) -> dict:
    """In-memory entry point; preserves caller provenance without reopening a ZIP."""
    if len(rom) != ROM_CAPACITY:
        raise KhcomError('matching_capacity', 'A origem deve ocupar o cartucho US de 32 MiB.')
    rebuilt = read_file(rebuild_path, ROM_CAPACITY)
    if sha256(rom).hexdigest() != BASELINE_SHA256 or rebuilt != rom:
        raise KhcomError('matching_baseline', 'A reconstrução precisa ser idêntica à ROM US aprovada.')
    elf_data = read_file(elf_path, 64 << 20)
    elf = _elf(elf_data)
    section = elf.get_section_by_name('.text')
    if section is None or section['sh_addr'] != ROM_BASE or section['sh_type'] != 'SHT_PROGBITS':
        raise KhcomError('matching_rom_section', 'Seção ROM não reconhecida.')
    linked = section.data()
    if len(linked) > len(rom) or linked[:4] != rom[:4] or linked[0xc0:] != rom[0xc0:len(linked)] or any(b != 255 for b in rom[len(linked):]):
        raise KhcomError('matching_elf_rom', 'ELF não corresponde à ROM fora do cabeçalho corrigido por gbafix.')
    map_data = read_file(map_path, 16 << 20)
    placements = parse_sections(map_data.decode('utf-8'))
    symbols = _symbols(elf)
    globals_by_name = {s['name']: s for s in symbols if s['binding'] == 'STB_GLOBAL'}
    by_owner = {}
    for item in placements:
        by_owner.setdefault(item['owner'], {})[item['section']] = item
    relocations = []
    direct_calls = []
    objects = []
    kinds = Counter()
    skipped = Counter()
    for owner, placed in sorted(by_owner.items()):
        path = (source_root / owner).resolve()
        if not path.is_relative_to(source_root.resolve()):
            raise KhcomError('matching_object_path', 'Objeto fora da árvore selecionada.', owner=owner)
        raw = read_file(path, 64 << 20)
        obj = _elf(raw)
        objects.append({**identity(path, raw), 'owner': owner})
        for relsec in obj.iter_sections():
            if not isinstance(relsec, RelocationSection):
                continue
            if relsec.is_RELA():
                raise KhcomError('matching_rela', 'Relocações RELA não pertencem ao perfil suportado.', owner=owner)
            target = obj.get_section(relsec['sh_info'])
            placement = placed.get(target.name)
            if placement is None or not ROM_BASE <= placement['address'] < ROM_BASE + ROM_CAPACITY:
                skipped['non_rom_section'] += relsec.num_relocations()
                continue
            if placement['size'] != target['sh_size']:
                raise KhcomError('matching_section_size', 'Tamanho de seção diverge do mapa.', owner=owner, section=target.name)
            symtab = obj.get_section(relsec['sh_link'])
            section_data = target.data()
            for relocation in relsec.iter_relocations():
                kind = relocation['r_info_type']
                kinds[str(kind)] += 1
                if kind not in (1, 2, 10):
                    continue
                at = relocation['r_offset']
                if at + 4 > len(section_data):
                    raise KhcomError('matching_relocation_range', 'Relocação fora da seção.', owner=owner)
                symbol = symtab.get_symbol(relocation['r_info_sym'])
                if symbol['st_shndx'] in ('SHN_UNDEF', 'SHN_COMMON'):
                    resolved = globals_by_name.get(symbol.name)
                    if resolved is None:
                        raise KhcomError('matching_unresolved', 'Símbolo externo sem destino único.', owner=owner, symbol=symbol.name)
                    value = resolved['address']
                    thumb = resolved['type'] == 'STT_LOPROC'
                elif symbol['st_shndx'] == 'SHN_ABS':
                    value = symbol['st_value']
                    thumb = symbol['st_info']['type'] == 'STT_LOPROC'
                elif isinstance(symbol['st_shndx'], int):
                    symbol_section = obj.get_section(symbol['st_shndx'])
                    symbol_placement = placed.get(symbol_section.name)
                    if symbol_placement is None:
                        raise KhcomError('matching_symbol_section', 'Seção de destino ausente do mapa.', owner=owner, symbol=symbol.name, section=symbol_section.name)
                    value = symbol_placement['address'] + symbol['st_value']
                    thumb = symbol['st_info']['type'] == 'STT_LOPROC'
                else:
                    raise KhcomError('matching_symbol_kind', 'Símbolo não suportado.', owner=owner, symbol=symbol.name)
                source_offset = placement['address'] - ROM_BASE + at
                if kind in (1, 10):
                    source_address = ROM_BASE + source_offset
                    addend = branch_displacement(section_data[at:at + 4], kind)
                    pc_bias = 4 if kind == 10 else 8
                    target_address = source_address + pc_bias + branch_displacement(rom[source_offset:source_offset + 4], kind)
                    expected_target = ((value & ~1) + addend + pc_bias) & 0xffffffff
                    if target_address != expected_target:
                        raise KhcomError('matching_call_value', 'Alvo da chamada diverge da relocação.', owner=owner, symbol=symbol.name, source_offset=source_offset)
                    direct_calls.append({'symbol': symbol.name or obj.get_section(symbol['st_shndx']).name,
                                         'source_offset': source_offset, 'target_offset': target_address - ROM_BASE,
                                         'target_address': target_address, 'symbol_address': value,
                                         'addend': addend, 'kind': 'R_ARM_THM_CALL' if kind == 10 else 'R_ARM_PC24',
                                         'owner': owner, 'source_section': target.name, 'source_section_offset': at})
                    continue
                addend = struct.unpack_from('<I', section_data, at)[0]
                expected = ((value + addend) | int(thumb)) & 0xffffffff
                if source_offset < 0 or source_offset + 4 > len(rom) or struct.unpack_from('<I', rom, source_offset)[0] != expected:
                    raise KhcomError('matching_relocation_value', 'Relocação resolvida diverge da ROM.', owner=owner, symbol=symbol.name, source_offset=source_offset, expected=expected)
                relocations.append({'symbol': symbol.name or obj.get_section(symbol['st_shndx']).name,
                                    'source_offset': source_offset, 'target_offset': expected - ROM_BASE if ROM_BASE <= expected < ROM_BASE + ROM_CAPACITY else None,
                                    'target_address': expected, 'symbol_address': value,
                                    'addend': addend, 'thumb_function': thumb, 'kind': 'R_ARM_ABS32', 'owner': owner,
                                    'source_section': target.name, 'source_section_offset': at})
    relocations.sort(key=lambda r: (r['source_offset'], r['owner']))
    by_source = {r['source_offset']: r for r in relocations}
    classifications = []
    for offset in candidate_offsets or []:
        if offset < 0 or offset + 4 > len(rom):
            raise KhcomError('matching_candidate_range', 'Palavra candidata fora da ROM.', offset=offset)
        containing_sections = [p for p in placements if p['address'] <= ROM_BASE + offset and ROM_BASE + offset + 4 <= p['address'] + p['size']]
        containing_symbols = _containers(symbols, ROM_BASE + offset)
        classifications.append({'source_offset': offset, 'value': struct.unpack_from('<I', rom, offset)[0],
                                'classification': 'linker_abs32_reference' if offset in by_source else 'word_without_linker_abs32_reference',
                                'relocation': by_source.get(offset), 'sections': containing_sections,
                                'symbols': containing_symbols})
    classify_encoded_words(classifications, rom, source_root, symbols)
    memory = []
    for name, base, capacity in (('.iwram', 0x03000000, 32768), ('.ewram', 0x02000000, 262144)):
        ram = elf.get_section_by_name(name)
        if ram is None or ram['sh_addr'] != base or ram['sh_size'] > capacity:
            raise KhcomError('matching_ram', 'Orçamento estático de RAM inválido.', section=name)
        memory.append({'section': name, 'address': base, 'static_reserved': ram['sh_size'], 'capacity': capacity,
                       'remaining_unassigned': capacity - ram['sh_size'], 'runtime_high_water': None})
    return {'schema': 'khcom-matching-facts-v1', 'rom': {'input': rom_identity, 'size': len(rom), 'sha256': sha256(rom).hexdigest()}, 'rebuild': identity(rebuild_path, rebuilt),
            'elf': identity(elf_path, elf_data), 'map': identity(map_path, map_data), 'objects': objects,
            'baseline_byte_identical': True, 'elf_rom_agreement': {'compared_spans': [[0, 4], [192, len(linked)]],
            'gbafix_header_span': [4, 192], 'cartridge_tail_span': [len(linked), len(rom)], 'cartridge_tail_byte': 255},
            'placements': placements, 'symbols': symbols, 'relocations': relocations,
            'direct_calls': sorted(direct_calls, key=lambda call: call['source_offset']), 'candidate_words': classifications,
            'ram': memory, 'cartridge': {'capacity': ROM_CAPACITY, 'occupied_linked_end': len(linked), 'free_space_proven': []},
            'relocation_kinds': dict(kinds), 'skipped': dict(skipped),
            'limitations': ['ABS32 facts are linker references, not complete ARM value-flow analysis.',
                            'No-relocation words can be encoded data or hand-written addresses; semantic classification requires owner evidence.',
                            'Static RAM reservations do not measure stack/heap high-water marks.',
                            'Trailing FF bytes and gaps are not declared reusable.']}
