#!/usr/bin/env python3
"""Gera uma candidata privada do aviso gráfico APERTE INICIAR para QA."""
import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.graphic_probe import build_title_probe
from khcom.rom import read_rom
from khcom.text import json_bytes, write_private


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--member")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--fetch-upstream", action="store_true")
    args = parser.parse_args()
    try:
        if args.out.resolve() == args.report.resolve() or any(p.exists() or p.is_symlink() for p in (args.out, args.report)):
            raise KhcomError("output_exists", "ROM e relatório exigem destinos novos e distintos.")
        rom = read_rom(args.rom, member=args.member)
        candidate, report = build_title_probe(rom.data, fetch=args.fetch_upstream)
        report["input"] = rom.identity["input"]
        write_private(args.report, json_bytes(report))
        write_private(args.out, candidate)
        print(json.dumps({"ok": True, "sha256": report["target_sha256"], "bytes_changed": report["bytes_changed"], "release_approved": False}))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
