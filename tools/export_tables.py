#!/usr/bin/env python3
"""Gera tabelas dos codecs conhecidos; não comprova fontes nem cria mapas fictícios."""

import argparse
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.io import write_new
from khcom.text import export_tables
from khcom.upstream import load_textgen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path, help="Novo diretório de tabelas")
    ap.add_argument("--fetch-upstream", action="store_true")
    args = ap.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink():
            raise KhcomError("output_exists", "O diretório de saída já existe; escolha um novo caminho.", path=str(args.out))
        tables = export_tables(load_textgen(fetch=args.fetch_upstream))
        # These tables contain character mappings, not extracted game prose.
        args.out.mkdir(parents=True, exist_ok=False)
        for name, content in tables.items():
            write_new(args.out / name, content.encode("utf-8"))
        print(json.dumps({"ok": True, "output": str(args.out), "tables": sorted(tables), "limitations": ["Fonte pequena ainda não mapeada; nenhuma tabela fictícia foi gerada.", "Codecs conhecidos não comprovam glifos ou limites visuais."]}, ensure_ascii=False, indent=2))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
