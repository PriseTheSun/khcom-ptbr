#!/usr/bin/env python3
"""Reconstrói localmente as fontes experimentais PT-BR dos créditos US."""

import argparse
import json
from pathlib import Path
import sys

from khcom.credits_profile import build_profile
from khcom.errors import KhcomError
from khcom.rom import read_rom
from khcom.text import json_bytes, write_private
from khcom.upstream import PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--member")
    parser.add_argument("--out", required=True, type=Path, help="Nova pasta dentro de private/")
    parser.add_argument("--fetch-upstream", action="store_true")
    args = parser.parse_args()
    try:
        destination = args.out.resolve()
        if not destination.is_relative_to(PROJECT_ROOT / "private"):
            raise KhcomError("private_output_required", "Derivados de fontes devem permanecer em private/.")
        if args.out.exists() or args.out.is_symlink():
            raise KhcomError("output_exists", "Escolha uma pasta nova.")
        rom = read_rom(args.rom, member=args.member)
        candidate, report, files = build_profile(rom.data, fetch=args.fetch_upstream)
        report["input"] = rom.identity["input"]
        destination.mkdir(parents=True, exist_ok=False)
        for name, payload in files.items():
            write_private(destination / name, payload)
        write_private(destination / "font-candidate.gba", candidate)
        # Publish the completion report last. Failed partial outputs are retained.
        write_private(destination / "report.json", json_bytes(report))
        print(json.dumps({"ok": True, "profile_id": report["profile_id"],
                          "target_sha256": report["target_sha256"],
                          "changed_bytes": report["changed_bytes"], "release_approved": False}))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
