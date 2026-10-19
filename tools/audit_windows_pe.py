#!/usr/bin/env python3
"""Inspect declared PE imports without loading code; use on the Windows runner."""
import argparse
import json
from pathlib import Path

from khcom.errors import KhcomError
from khcom.io import read_file, write_json_new
from khcom.windows_pe import audit_windows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--system32", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(read_file(args.package / "package-manifest.json", 4 * 1024 * 1024))
        report = audit_windows(args.package, manifest, args.system32)
        write_json_new(args.report, report)
        print(json.dumps({"audit_passed": report["audit_passed"], "images": len(report["images"]),
                          "dependencies": len(report["dependencies"]), "report": str(args.report)}))
        return 0 if report["audit_passed"] else 2
    except (KhcomError, OSError, ValueError) as error:
        print(json.dumps({"audit_passed": False,
                          "error": error.as_dict() if isinstance(error, KhcomError) else str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
