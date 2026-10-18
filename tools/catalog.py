#!/usr/bin/env python3
"""Intercâmbio CSV/JSON UTF-8, preservando origem e identidade de cada item."""

import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.io import read_file
from khcom.text import CATALOG_MAX_BYTES, export_csv, import_csv, json_bytes, read_catalog, write_private


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="operation", required=True)
    for name in ("export-csv", "import-csv"):
        command = sub.add_parser(name)
        command.add_argument("--catalog", required=True, type=Path)
        command.add_argument("--out", required=True, type=Path, help="Novo arquivo dentro de private/")
        if name == "import-csv":
            command.add_argument("--csv", required=True, type=Path)
    args = ap.parse_args()
    try:
        catalog = read_catalog(args.catalog)
        if args.operation == "export-csv":
            result = export_csv(catalog).encode("utf-8")
        else:
            result = json_bytes(import_csv(catalog, read_file(args.csv, CATALOG_MAX_BYTES).decode("utf-8")))
        write_private(args.out, result)
        print(json.dumps({"ok": True, "operation": args.operation, "output": str(args.out), "items": len(catalog["items"])}, ensure_ascii=False))
        return 0
    except (KhcomError, OSError, UnicodeError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
