#!/usr/bin/env python3
"""Reconstrói um piloto audiovisual privado derivado da ROM US do usuário."""
import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.io import write_json_new
from khcom.movie_title import build_opening_title_probe
from khcom.movies import build_opening_subtitle_probe
from khcom.rom import read_rom
from khcom.text import write_private


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom',type=Path,required=True)
    ap.add_argument('--member')
    ap.add_argument('--kind',choices=('opening-subtitles','opening-title'),required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:
        rom=read_rom(args.rom,member=args.member)
        producer=build_opening_subtitle_probe if args.kind=='opening-subtitles' else build_opening_title_probe
        candidate,report=producer(rom.data)
        report['input']=rom.identity['input']
        write_private(args.out,candidate)
        write_json_new(args.out.with_suffix('.json'),report)
        print(json.dumps({'ok':True,'output':str(args.out),'target_sha256':report['target_sha256']},ensure_ascii=False))
        return 0
    except (KhcomError,OSError,ValueError) as error:
        detail=error.as_dict() if isinstance(error,KhcomError) else {'code':'movie_probe_input','message':str(error)}
        print(json.dumps({'ok':False,'error':detail},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
