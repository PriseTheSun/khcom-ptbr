#!/usr/bin/env python3
"""Cria uma fala fixa experimental de Sora/Riku para QA em runtime."""

import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.rom import read_rom
from khcom.text import DIALOGUE_PROBES, build_dialogue_probe, json_bytes, write_private


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--member")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--fetch-upstream", action="store_true")
    ap.add_argument("--scene", choices=list(DIALOGUE_PROBES), default="sora-opening")
    args = ap.parse_args()
    try:
        if args.out.resolve() == args.report.resolve() or any(path.exists() or path.is_symlink() for path in (args.out, args.report)):
            raise KhcomError("output_exists", "ROM e relatório precisam de destinos novos e distintos.")
        rom = read_rom(args.rom, member=args.member)
        candidate, report = build_dialogue_probe(rom.data, fetch=args.fetch_upstream, scene=args.scene)
        report["input"] = rom.identity["input"]
        write_private(args.out, candidate)
        write_private(args.report, json_bytes(report))
        print(json.dumps({"ok": True, "operation": report["operation"], "output": str(args.out), "report": str(args.report), "sha256": report["target_sha256"], "release_approved": False}, ensure_ascii=False))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
