"""One bounded menu relocation backed by fresh matching linker facts.

This is a diagnostic proof, not permission for arbitrary text relocation.
The 46-byte union belongs to three adjacent text objects. Shortening one
releases capacity used by the next; the next unrelated symbol stays fixed.
"""
from hashlib import sha256
import struct

from .errors import KhcomError
from .graphics import extract_fonts
from .matching import BASELINE_SHA256, ROM_BASE, ROM_CAPACITY
from .upstream import load_textgen

MENU = (
    ('gMapSaveConfirmText', 1416688, 32, 'Save your game?{END}', 'Salvar jogo?{END}'),
    ('gYesChoiceText', 1416720, 8, 'Yes{END}', 'Sim{END}'),
    ('gNoChoiceText', 1416728, 6, 'No{END}', 'Não{END}'),
)


def validate_cartridge_size(size: int, capacity: int = ROM_CAPACITY) -> None:
    if type(size) is not int or size <= 0 or size > capacity:
        raise KhcomError('relocation_cartridge_capacity', 'Resultado excede o cartucho suportado.', size=size, maximum=capacity)


def build_relocation_probe(data: bytes, facts: dict) -> tuple[bytes, dict]:
    """facts must come from audit_matching_bytes in this invocation, never JSON."""
    validate_cartridge_size(len(data))
    if sha256(data).hexdigest() != BASELINE_SHA256 or facts['rom']['sha256'] != BASELINE_SHA256 or not facts['baseline_byte_identical']:
        raise KhcomError('relocation_baseline', 'Prova exige origem US e fatos matching frescos.')
    codec = load_textgen().load_charmap('us')['game']
    font_report, _ = extract_fonts(data)
    widths = font_report['latin_metrics']['values']
    latin = next(font for font in font_report['fonts'] if font['id'] == 'message_latin')
    symbols = {s['name']: s for s in facts['symbols'] if s['binding'] == 'STB_GLOBAL'}
    start, end = MENU[0][1], MENU[-1][1] + MENU[-1][2]
    at = start
    payload = bytearray()
    translations = []
    for name, offset, size, original, translated in MENU:
        symbol = symbols.get(name)
        old = codec.encode(original, name)
        encoded = codec.encode(translated, name)
        if symbol is None or symbol['address'] != ROM_BASE + offset or symbol['size'] != size or old != data[offset:offset+size]:
            raise KhcomError('relocation_symbol', 'Objeto do piloto diverge do baseline.', symbol=name)
        codes = [int.from_bytes(encoded[i:i+2], 'little') for i in range(0, len(encoded)-2, 2)]
        if any(not 32 <= code <= 255 or (code != 32 and not latin['glyphs'][code]['nonzero_pixels']) for code in codes):
            raise KhcomError('relocation_font', 'Glifo latino não verificado no piloto.', symbol=name)
        translations.append({'symbol': name, 'old_offset': offset, 'new_offset': at, 'old_size': size,
                             'new_size': len(encoded), 'text': translated, 'advance_pixels': sum(widths[code] for code in codes),
                             'source_advance_pixels': sum(widths[int.from_bytes(old[i:i+2], 'little')] for i in range(0,len(old)-2,2))})
        payload += encoded
        at += len(encoded)
    if at > end:
        raise KhcomError('relocation_pool_capacity', 'Traduções excedem a união comprovada de objetos.', required=len(payload), capacity=end-start)
    # Explicit padding belongs to the reclaimed union; nothing outside is allocated.
    padding = end - at
    payload += bytes(padding)
    by_old = {entry['old_offset']: entry for entry in translations}
    references = [ref for ref in facts['relocations'] if ref['target_offset'] is not None and start <= ref['target_offset'] < end]
    sources = {ref['source_offset']: ref for ref in references}
    if len(sources) != len(references):
        raise KhcomError('relocation_duplicate', 'Mais de uma relocação atribui a mesma palavra.')
    # This all-byte scan also detects unaligned/interior raw pointer values.
    for pointer in range(start, end):
        needle = struct.pack('<I', ROM_BASE + pointer)
        position = data.find(needle)
        while position != -1:
            if position not in sources or sources[position]['target_offset'] != pointer:
                raise KhcomError('relocation_unknown_reference', 'Valor de endereço fora das referências do linker.', source_offset=position, target_offset=pointer)
            position = data.find(needle, position + 1)
    result = bytearray(data)
    result[start:end] = payload
    updates = []
    for reference in references:
        entry = by_old.get(reference['target_offset'])
        if entry is None or reference['addend'] != 0 or reference['symbol'] != entry['symbol']:
            raise KhcomError('relocation_interior', 'Referência interior ou indireta sem contrato.', reference=reference)
        source = reference['source_offset']
        if start <= source < end or struct.unpack_from('<I', data, source)[0] != ROM_BASE + entry['old_offset']:
            raise KhcomError('relocation_source', 'Fonte de referência inválida.', source_offset=source)
        struct.pack_into('<I', result, source, ROM_BASE + entry['new_offset'])
        updates.append({**reference, 'new_target_offset': entry['new_offset'], 'changed': entry['new_offset'] != entry['old_offset']})
    validate_cartridge_size(len(result))
    if len(result) != len(data):
        raise KhcomError('relocation_length', 'Piloto não pode mudar o tamanho do cartucho.')
    return bytes(result), {'schema': 'khcom-relocation-probe-v1', 'source_sha256': sha256(data).hexdigest(),
                           'target_sha256': sha256(result).hexdigest(), 'rom_size': len(result), 'translations': translations,
                           'pool_span': [start, end], 'explicit_padding_bytes': padding, 'references': updates,
                           'matching_elf': facts['elf'], 'matching_map': facts['map'], 'matching_object_count': len(facts['objects']),
                           'ram': facts['ram'], 'scope': 'three adjacent common_text objects; all other asset positions unchanged',
                           'status': 'diagnostic_candidate_requires_relink_and_runtime_proof', 'release_approved': False,
                           'limitations': ['A complete ARM value-flow proof is not implied by linker references.',
                                           'Menu visual and consumer contracts remain required for production.']}


def build_verified_relocation_probe(data: bytes) -> tuple[bytes, dict]:
    """Replay the frozen, independently relinked pilot without the private toolchain.

    The source and expected destination are SHA-bound. The public contract only
    contains addresses, sizes, provenance and hashes, never commercial bytes.
    Changing any recipe input requires a new audit and contract version.
    """
    import json
    from pathlib import Path
    from .io import read_file

    path = Path(__file__).resolve().parents[2] / 'manifests/relocation-menu-v1.json'
    raw = read_file(path, 32 << 10)
    expected = '119ea062cbcbb55a39c3d6e8262e51a83ed805f60f219ae3761a222bae9fd65f'
    if sha256(raw).hexdigest() != expected:
        raise KhcomError('relocation_contract_identity', 'Contrato de realocação diverge da versão verificada.')
    contract = json.loads(raw)
    facts = {**contract, 'rom': {'sha256': contract['rom_sha256']}, 'baseline_byte_identical': True}
    candidate, report = build_relocation_probe(data, facts)
    if sha256(candidate).hexdigest() != contract['candidate_sha256']:
        raise KhcomError('relocation_recipe_identity', 'Receita não reproduz o candidato relinkado e observado.')
    report['contract'] = {'path': str(path), 'sha256': expected, 'schema': contract['schema']}
    report['status'] = 'verified_diagnostic_recipe_one_save_menu_occurrence'
    report['provenance'] = contract['evidence']
    return candidate, report
