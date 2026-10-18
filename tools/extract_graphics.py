#!/usr/bin/env python3
"""Extrai cinco fontes verificadas em PNG privado, sem modificar a ROM."""

import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.graphics import extract_fonts
from khcom.rom import read_rom
from khcom.text import json_bytes, write_private


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--member")
    ap.add_argument("--out", required=True, type=Path, help="Nova pasta dentro de private/")
    ap.add_argument("--fetch-upstream", action="store_true")
    args = ap.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink():
            raise KhcomError("output_exists", "Escolha uma nova pasta de saída.", path=str(args.out))
        rom = read_rom(args.rom, member=args.member)
        report, files = extract_fonts(rom.data, fetch=args.fetch_upstream)
        for name, content in files.items():
            write_private(args.out / name, content)
        write_private(args.out / "report.json", json_bytes(report))
        print(json.dumps({"ok": True, "output": str(args.out), "fonts": len(report["fonts"]), "glyphs": sum(font["glyph_count"] for font in report["fonts"]), "complete_graphics_inventory": False}, ensure_ascii=False))
        return 0
    except (KhcomError, OSError, ValueError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
