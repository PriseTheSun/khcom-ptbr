#!/usr/bin/env python3
"""Apply a BPS candidate with the exact source, patch and target digests."""
import argparse
import json
import sys

from khcom.bps import apply, digest, MAX_PATCH
from khcom.errors import KhcomError
from khcom.io import read_file, write_new
from khcom.rom import read_rom


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--member")
    parser.add_argument("--patch", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        source = read_rom(args.source, member=args.member)
        manifest = json.loads(read_file(args.manifest, 32 * 1024 * 1024).decode("utf-8"))
        if not isinstance(manifest, dict) or manifest.get("format") != "BPS1":
            raise KhcomError("invalid_manifest", "Manifesto BPS1 inválido.")
        patch = read_file(args.patch, MAX_PATCH)
        if (source.identity["sha256"] != manifest.get("source_sha256")
                or digest(patch) != manifest.get("patch_sha256")):
            raise KhcomError("patch_identity", "Origem ou patch divergem do manifesto.")
        target_digest = manifest.get("target_sha256")
        if not isinstance(target_digest, str) or len(target_digest) != 64:
            raise KhcomError("invalid_manifest", "Digest de destino ausente/inválido.")
        output = apply(source.data, patch, expected_target_sha256=target_digest)
        if len(output) != manifest.get("target_size"):
            raise KhcomError("patch_identity", "Tamanho de destino diverge do manifesto.")
        write_new(args.out, output)
        print(json.dumps({"ok": True, "size": len(output), "sha256": digest(output)}))
        return 0
    except KhcomError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 2
    except (ValueError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": {"code": "invalid_manifest", "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
