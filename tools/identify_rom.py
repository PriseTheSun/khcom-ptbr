#!/usr/bin/env python3
"""Identifica a revisão e opcionalmente materializa uma cópia em destino novo."""

import argparse
import json
import sys

from khcom.errors import KhcomError
from khcom.io import write_json_new, write_new
from khcom.rom import read_rom


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="ROM GBA ou ZIP escolhido pelo usuário")
    parser.add_argument("--member", help="Nome exato da ROM dentro do ZIP")
    parser.add_argument("--copy-to", help="Destino novo para cópia local da ROM validada")
    parser.add_argument("--out", help="Destino novo para relatório JSON")
    args = parser.parse_args()
    try:
        rom = read_rom(args.input, member=args.member)
        if args.copy_to:
            write_new(args.copy_to, rom.data)
        result = {"ok": True, "identity": rom.identity}
        if args.out:
            write_json_new(args.out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KhcomError, OSError) as exc:
        error = exc if isinstance(exc, KhcomError) else KhcomError("io_error", str(exc))
        print(json.dumps({"ok": False, "error": error.as_dict()}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
