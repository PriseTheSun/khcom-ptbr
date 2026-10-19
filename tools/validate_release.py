#!/usr/bin/env python3
"""Valida identidades e todos os gates do candidato antes de disponibilizar pacotes."""
import argparse
import json
from pathlib import Path
from khcom.errors import KhcomError
from khcom.io import read_file, write_json_new
from khcom.release import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(read_file(args.candidate / "release.json", 4 * 1024 * 1024))
        report = verify(args.candidate, manifest, args.commit)
        write_json_new(args.report, report)
        print(json.dumps(report))
        return 0
    except (KhcomError, ValueError, OSError) as error:
        print(json.dumps({"release_gate_passed": False, "error": error.as_dict() if isinstance(error, KhcomError) else str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
