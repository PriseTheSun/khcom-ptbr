#!/usr/bin/env python3
"""Inventaria framing audiovisual e ocorrências de legenda sem editar a ROM."""
import argparse
import json
from pathlib import Path
import sys
from khcom.errors import KhcomError
from khcom.movies import inventory_movies
from khcom.rom import read_rom
from khcom.text import write_private, json_bytes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--member')
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    try:
        rom = read_rom(args.rom, member=args.member)
        result = inventory_movies(rom.data)
        result['input'] = rom.identity['input']
        write_private(args.out, json_bytes(result))
        print(json.dumps({'ok': True, 'movies': len(result['movies']), 'frames': result['declared_frames'],
                          'subtitle_rows': result['declared_subtitle_rows'], 'selected_rows': result['selected_subtitle_rows']}))
        return 0
    except (KhcomError, OSError, ValueError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {'code': 'movie_input', 'message': str(error)}
        print(json.dumps({'ok': False, 'error': detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
