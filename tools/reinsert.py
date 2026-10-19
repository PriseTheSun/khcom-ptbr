#!/usr/bin/env python3
"""Reinsere texto em reservas fixas somente com contrato de ocorrência verificado."""

import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.rom import read_rom
from khcom.text import json_bytes, read_catalog, write_private
from khcom.credits_profile import PROFILE_ID
from khcom.validation import plan_translations, apply_translation_plan
from khcom.upstream import load_textgen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--member")
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="Nova ROM derivada em private/")
    ap.add_argument("--report", required=True, type=Path, help="Novo relatório por intervalo em private/")
    ap.add_argument("--fetch-upstream", action="store_true")
    ap.add_argument("--profile", choices=[PROFILE_ID], help="Perfil explícito de candidato; não aprova tradução/release")
    ap.add_argument("--matching-tree", type=Path, help="Árvore de build matching para revalidar referências do perfil")
    args = ap.parse_args()
    try:
        if args.out.resolve() == args.report.resolve():
            raise KhcomError("output_collision", "ROM e relatório exigem caminhos distintos.")
        for path in (args.out, args.report):
            if path.exists() or path.is_symlink():
                raise KhcomError("output_exists", "Uma saída já existe; escolha novos caminhos.", path=str(path))
        rom = read_rom(args.rom, member=args.member)
        parser = load_textgen(fetch=args.fetch_upstream)
        plan = plan_translations(rom.data, read_catalog(args.catalog), parser=parser, profile_id=args.profile,
                                 matching_tree=args.matching_tree, rom_identity=rom.identity)
        report = plan.report
        report["input"] = rom.identity["input"]
        report["catalog_path"] = str(args.catalog.absolute())
        if report["blocked_items"]:
            write_private(args.report, json_bytes(report))
            print(json.dumps({"ok": False, "report": str(args.report), "rom_written": False,
                              "blocked_items": report["blocked_items"], "diagnostic_counts": report["diagnostic_counts"]}))
            return 2
        result, report = apply_translation_plan(rom.data, plan)
        # Success evidence is last; a write failure cannot publish a successful
        # reinsertion report for a ROM that was never created.
        write_private(args.out, result)
        write_private(args.report, json_bytes(report))
        print(json.dumps({"ok": True, "output": str(args.out), "report": str(args.report),
                          "target_sha256": report["target_sha256"], "changed_items": report["changed_items"],
                          "bytes_changed": report["bytes_changed"], "release_approved": False}, ensure_ascii=False))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
