#!/usr/bin/env python3
"""Cria piloto privado de realocação limitada, após auditar o baseline matching."""
import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.io import write_json_new
from khcom.matching import audit_matching_bytes
from khcom.relocation_probe import build_relocation_probe
from khcom.rom import read_rom
from khcom.text import write_private


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--member')
    ap.add_argument('--matching-tree', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    try:
        rom = read_rom(args.rom, member=args.member)
        root = args.matching_tree
        facts = audit_matching_bytes(rom.data, rom_identity=rom.identity['input'], rebuild_path=root/'build/us/com_us.gba',
                                     elf_path=root/'build/us/com_us.elf', map_path=root/'build/us/com_us.map', source_root=root)
        candidate, report = build_relocation_probe(rom.data, facts)
        write_private(args.out, candidate)
        write_json_new(args.out.with_suffix('.json'), report)
        print(json.dumps({'ok': True, 'target_sha256': report['target_sha256'], 'references': len(report['references']),
                          'output': str(args.out)}, ensure_ascii=False))
        return 0
    except (KhcomError, OSError, ValueError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {'code': 'relocation_input', 'message': str(error)}
        print(json.dumps({'ok': False, 'error': detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
