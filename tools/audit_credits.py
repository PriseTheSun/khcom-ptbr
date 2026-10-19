#!/usr/bin/env python3
"""Audita roteiro, códigos e larguras dos créditos sem alterar a ROM."""

import argparse
import json
from pathlib import Path
import sys

from khcom.credits import audit_credits
from khcom.errors import KhcomError
from khcom.rom import read_rom
from khcom.text import json_bytes, write_private


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", type=Path, required=True)
    ap.add_argument("--member")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fetch-upstream", action="store_true")
    args = ap.parse_args()
    try:
        rom = read_rom(args.rom, member=args.member)
        report = audit_credits(rom.data, fetch=args.fetch_upstream)
        report["input"] = rom.identity["input"]
        write_private(args.out, json_bytes(report))
        print(json.dumps({"ok": True, "rows": len(report["rows"]), "output": str(args.out), "runtime_verified": False, "visible_advance_warnings": report["visible_advance_warnings"]}))
        return 0
    except (KhcomError, OSError, ValueError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
