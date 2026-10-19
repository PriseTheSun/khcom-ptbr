#!/usr/bin/env python3
"""Extrai o inventário textual privado e verificado da revisão USA."""

import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.rom import read_rom
from khcom.text import extract_catalog, json_bytes, sanitized_summary, write_private


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--member", help="Membro exato quando o ZIP contém mais de uma candidata")
    ap.add_argument("--out", required=True, type=Path, help="Novo catálogo dentro de private/")
    ap.add_argument("--fetch-upstream", action="store_true", help="Obter arquivos oficiais ausentes da revisão/hash fixados")
    args = ap.parse_args()
    try:
        rom = read_rom(args.rom, member=args.member)
        catalog = extract_catalog(rom.data, fetch=args.fetch_upstream)
        catalog["input"] = rom.identity["input"]
        write_private(args.out, json_bytes(catalog))
        print(json.dumps({"ok": True, "output": str(args.out), **sanitized_summary(catalog)}, ensure_ascii=False, indent=2))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
