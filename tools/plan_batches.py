#!/usr/bin/env python3
"""Particiona o inventário conhecido em sessões UTF-8 sem iniciar tradução."""
import argparse
import json
from pathlib import Path
import sys

from khcom.assets import inventory_assets
from khcom.batches import plan, editable_batches, checklist
from khcom.coverage import inventory_from_sources
from khcom.errors import KhcomError
from khcom.io import read_file
from khcom.rom import read_rom
from khcom.text import extract_catalog, json_bytes, write_private
from khcom.upstream import PROJECT_ROOT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom", required=True, type=Path)
    p.add_argument("--member")
    p.add_argument("--events", type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--max-items", type=int, default=48)
    p.add_argument("--max-characters", type=int, default=12000)
    a = p.parse_args()
    try:
        out = a.out.resolve()
        if not out.is_relative_to(PROJECT_ROOT / "private") or out.exists() or a.out.is_symlink():
            raise KhcomError("batch_output", "Escolha uma pasta privada nova para os textos de origem.")
        rom = read_rom(a.rom, member=a.member)
        catalog = extract_catalog(rom.data)
        inventory = inventory_from_sources(catalog, inventory_assets(rom.data))
        events = json.loads(read_file(a.events, 64 * 1024 * 1024)) if a.events else None
        value = plan(catalog, inventory, events, max_items=a.max_items, max_characters=a.max_characters)
        out.mkdir(parents=True)
        write_private(out / "plan.json", json_bytes(value))
        write_private(out / "catalog.json", json_bytes(catalog))
        write_private(out / "inventory.json", json_bytes(inventory))
        write_private(out / "sessions.md", checklist(value).encode())
        sessions = editable_batches(value, catalog)
        for session in sessions:
            write_private(out / "text" / (session["batch_id"] + ".json"), json_bytes(session))
        print(json.dumps({"ok": True, "items": value["items_total"], "batches": len(value["batches"]),
                          "text_sessions": len(sessions), "full_translation": False}))
        return 0
    except (KhcomError, OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": e.as_dict() if isinstance(e, KhcomError) else str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
