#!/usr/bin/env python3
"""Audita ocorrências e paginação US, sem alterar ROM ou autorizar tradução."""
import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.event_contract import audit_event_text
from khcom.rom import read_rom
from khcom.text import json_bytes, write_private


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--member")
    ap.add_argument("--matching-tree", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink():
            raise KhcomError("output_exists", "Escolha um relatório novo.")
        rom = read_rom(args.rom, member=args.member)
        report = audit_event_text(rom.data, matching_tree=args.matching_tree, rom_identity=rom.identity)
        report["input"] = rom.identity["input"]
        write_private(args.out, json_bytes(report))
        print(json.dumps({"ok": True, "events": report["event_count"], "occurrences": report["occurrence_count"],
                          "layout_counts": report["layout_counts"], "unknown_counts": report["unknown_counts"],
                          "edit_authorized": False}))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
