#!/usr/bin/env python3
"""Verifica reinserção sem edição; alterações exigem validação gráfica ainda pendente."""

import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.rom import read_rom
from khcom.text import json_bytes, read_catalog, reinsert_unedited, write_private
from khcom.upstream import load_textgen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--member")
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="Nova ROM derivada em private/")
    ap.add_argument("--report", required=True, type=Path, help="Novo relatório por intervalo em private/")
    ap.add_argument("--fetch-upstream", action="store_true")
    args = ap.parse_args()
    try:
        if args.out.resolve() == args.report.resolve():
            raise KhcomError("output_collision", "ROM e relatório exigem caminhos distintos.")
        for path in (args.out, args.report):
            if path.exists() or path.is_symlink():
                raise KhcomError("output_exists", "Uma saída já existe; escolha novos caminhos.", path=str(path))
        rom = read_rom(args.rom, member=args.member)
        parser = load_textgen(fetch=args.fetch_upstream)
        result, report = reinsert_unedited(rom.data, read_catalog(args.catalog), parser=parser)
        report["input"] = rom.identity["input"]
        report["catalog_path"] = str(args.catalog.absolute())
        write_private(args.report, json_bytes(report))
        write_private(args.out, result)
        print(json.dumps({"ok": True, "output": str(args.out), "report": str(args.report), **{key: value for key, value in report.items() if key != "intervals"}}, ensure_ascii=False, indent=2))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
