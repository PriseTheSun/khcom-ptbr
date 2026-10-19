#!/usr/bin/env python3
"""Reúne sessões editoriais sem conceder aprovação para reinserção na ROM."""
import argparse
import json
from pathlib import Path
import sys

from khcom.assets import inventory_assets
from khcom.batches import assemble, verify_partition
from khcom.coverage import inventory_from_sources
from khcom.errors import KhcomError
from khcom.io import read_file
from khcom.rom import read_rom
from khcom.text import extract_catalog, json_bytes, write_private


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom", required=True, type=Path)
    p.add_argument("--member")
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--sessions", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    try:
        rom = read_rom(a.rom, member=a.member)
        catalog = extract_catalog(rom.data)
        inventory = inventory_from_sources(catalog, inventory_assets(rom.data))
        value = json.loads(read_file(a.plan, 64 * 1024 * 1024))
        verify_partition(value, inventory)
        expected = {b["id"] + ".json" for b in value["batches"] if b["kind"] == "text"}
        paths = list(a.sessions.iterdir())
        if any(p.is_symlink() or not p.is_file() for p in paths) or {p.name for p in paths} != expected:
            raise KhcomError("batch_sessions", "A pasta deve conter exatamente os lotes textuais previstos.")
        sessions, total = [], 0
        for path in sorted(paths):
            raw = read_file(path, min(4 * 1024 * 1024, 64 * 1024 * 1024 - total))
            total += len(raw)
            if total >= 64 * 1024 * 1024:
                raise KhcomError("batch_budget", "Sessões excedem o orçamento agregado de 64 MiB.")
            sessions.append(json.loads(raw))
        result = assemble(value, sessions, catalog)
        write_private(a.out, json_bytes(result))
        print(json.dumps({"ok": True, "items": len(result["items"]),
                          "translated_fields": sum(i.get("translation") is not None for i in result["items"]),
                          "reinsertion_approved": False, "full_translation": False}))
        return 0
    except (KhcomError, OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": e.as_dict() if isinstance(e, KhcomError) else str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__": sys.exit(main())
