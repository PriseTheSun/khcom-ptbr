#!/usr/bin/env python3
"""Audita o diretório fechado criado por package_desktop.py, sem dados de jogo."""
import argparse
import json
from pathlib import Path
from khcom.errors import KhcomError
from khcom.io import read_file, write_json_new
from khcom.package import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(read_file(args.package / "package-manifest.json", 4 * 1024 * 1024))
        report = audit(args.package, manifest)
        if args.report:
            write_json_new(args.report, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (KhcomError, ValueError, OSError) as error:
        print(json.dumps({"ok": False, "error": error.as_dict() if isinstance(error, KhcomError) else str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
