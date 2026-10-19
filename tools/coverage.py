#!/usr/bin/env python3
"""Inventário e gate de cobertura ligados à ROM original e a recibos de QA."""

import argparse
import json
from pathlib import Path
import sys

from khcom.assets import inventory_assets
from khcom.coverage import bind_inventory, evaluate, inventory_from_sources
from khcom.errors import KhcomError
from khcom.io import read_file
from khcom.rom import read_rom
from khcom.text import extract_catalog, json_bytes, write_private


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inventory", "check"))
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--member")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--fetch-upstream", action="store_true")
    args = parser.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink():
            raise KhcomError("output_exists", "Escolha um relatório novo para preservar a revisão anterior.")
        rom = read_rom(args.rom, member=args.member)
        catalog = extract_catalog(rom.data, fetch=args.fetch_upstream)
        actual = inventory_from_sources(catalog, inventory_assets(rom.data))
        if args.operation == "inventory":
            actual["input"] = rom.identity["input"]
            write_private(args.out, json_bytes(actual))
            print(json.dumps({"ok": True, "items": len(actual["items"]), "discovery_closed": False}))
            return 0
        if not all((args.inventory, args.ledger, args.evidence_root)):
            raise KhcomError("coverage_arguments", "check exige --inventory, --ledger e --evidence-root.")
        inventory = json.loads(read_file(args.inventory, 64 * 1024 * 1024))
        ledger = json.loads(read_file(args.ledger, 64 * 1024 * 1024))
        bind_inventory(inventory, actual, rom.data)
        report = evaluate(inventory, ledger, args.evidence_root)
        report["input"] = rom.identity["input"]
        write_private(args.out, json_bytes(report))
        print(json.dumps({"ok": True, "items": report["items_total"],
                          "coverage_complete": report["coverage_complete"],
                          "blocker_counts": report["blocker_counts"]}))
        return 0 if report["coverage_complete"] else 2
    except (KhcomError, OSError, ValueError, RecursionError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "coverage_input", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
