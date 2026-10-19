#!/usr/bin/env python3
"""Audita ocupação e referências de uma reconstrução integral matching privada."""
import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.io import write_json_new
from khcom.matching import audit_matching


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'rebuild', 'elf', 'map', 'source-root', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--word', type=lambda value: int(value, 0), action='append', default=[])
    args = ap.parse_args()
    try:
        report = audit_matching(args.rom, args.rebuild, args.elf, args.map, args.source_root, args.word)
        write_json_new(args.out, report)
        print(json.dumps({'ok': True, 'objects': len(report['objects']), 'references': len(report['relocations']),
                          'ram': report['ram'], 'output': str(args.out)}, ensure_ascii=False))
        return 0
    except (KhcomError, OSError, ValueError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {'code': 'matching_input', 'message': str(error)}
        print(json.dumps({'ok': False, 'error': detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
