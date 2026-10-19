#!/usr/bin/env python3
"""Plano, prontidão e assinatura Apple de uma cópia auditada; sem credenciais em argumentos."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
from khcom.apple_signing import Settings, execute, plan, readiness, resume
from khcom.errors import KhcomError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, help="payload macOS do empacotador; permanece intacto")
    parser.add_argument("--out", type=Path, help="diretório novo para cópia e proveniência")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="padrão: plano e prontidão; não escreve/envia")
    mode.add_argument("--readiness", action="store_true", help="somente prontidão; exit 3 se indisponível")
    mode.add_argument("--execute", action="store_true", help="assina cópia e envia uma única vez à Apple")
    mode.add_argument("--resume", type=Path, help="consulta ID persistido; finaliza só após Accepted")
    parser.add_argument("--identity", default=os.environ.get("KHCOM_APPLE_IDENTITY_SHA1", ""), help="SHA-1 público de Developer ID Application")
    parser.add_argument("--profile", default=os.environ.get("KHCOM_NOTARY_PROFILE", ""), help="nome de profile já provisionado no Keychain")
    parser.add_argument("--keychain", default=os.environ.get("KHCOM_APPLE_KEYCHAIN", ""), help="Keychain já provisionado/desbloqueado, opcional")
    args = parser.parse_args()
    settings = Settings(args.identity, args.profile, args.keychain)
    try:
        if args.resume:
            if args.payload or args.out:
                parser.error("--resume não combina com --payload/--out")
            result = resume(args.resume, settings)
        elif args.readiness:
            result = readiness(settings)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["ready_to_attempt"] else 3
        else:
            if not args.payload or (args.execute and not args.out):
                parser.error("informe --payload; --execute também exige --out")
            if args.execute:
                result = execute(args.payload, args.out, settings)
            else:
                result = {"ok": True, "mode": "dry-run", "plan": plan(args.payload), "readiness": readiness(settings),
                          "writes": False, "network_submission": False}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (KhcomError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        # Never print raw subprocess argv/output, the environment, or password material.
        error = exc.as_dict() if isinstance(exc, KhcomError) else {"code": "apple_execution", "message": "Falha local/timeout; saídas parciais foram preservadas.", "type": type(exc).__name__}
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
