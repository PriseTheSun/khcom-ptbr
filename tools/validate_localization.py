#!/usr/bin/env python3
"""Diagnostica edições UTF-8 sem alterar a ROM ou aprovar cobertura."""
import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.rom import read_rom
from khcom.text import json_bytes, read_catalog, write_private
from khcom.upstream import load_textgen
from khcom.validation import validate_translations
from khcom.credits_profile import PROFILE_ID


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--member")
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--fetch-upstream", action="store_true")
    ap.add_argument("--profile", choices=[PROFILE_ID])
    ap.add_argument("--matching-tree", type=Path, help="Árvore de build matching para revalidar referências do perfil")
    args = ap.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink():
            raise KhcomError("output_exists", "Escolha um relatório novo.")
        rom = read_rom(args.rom, member=args.member)
        report = validate_translations(rom.data, read_catalog(args.catalog), parser=load_textgen(fetch=args.fetch_upstream),
                                       profile_id=args.profile, matching_tree=args.matching_tree, rom_identity=rom.identity)
        report["input"] = rom.identity["input"]
        report["catalog_path"] = str(args.catalog.absolute())
        write_private(args.out, json_bytes(report))
        print(json.dumps({"ok": True, "changed_items": report["changed_items"], "blocked_items": report["blocked_items"],
                          "diagnostic_counts": report["diagnostic_counts"], "release_approved": False}))
        return 2 if report["blocked_items"] else 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
