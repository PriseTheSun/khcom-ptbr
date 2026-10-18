#!/usr/bin/env python3
"""Create a local BPS candidate; the manifest never grants release approval."""
import argparse
import json
from pathlib import Path
import sys

from khcom.bps import apply, create, MAX_IMAGE
from khcom.errors import KhcomError
from khcom.io import read_file, write_json_new, write_new
from khcom.rom import read_rom


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--member")
    parser.add_argument("--target", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    try:
        outputs = [Path(args.out), Path(args.manifest)]
        if outputs[0].resolve() == outputs[1].resolve():
            raise KhcomError("output_collision", "Patch e manifesto exigem caminhos distintos.")
        if any(path.exists() or path.is_symlink() for path in outputs):
            raise KhcomError("output_exists", "Patch e manifesto exigem destinos novos.")
        source = read_rom(args.source, member=args.member)
        target = read_file(args.target, MAX_IMAGE)
        patch, report = create(source.data, target)
        apply(source.data, patch, expected_target_sha256=report["target_sha256"])
        report["reapply_verified"] = True
        report["source_identity"] = source.identity
        write_new(args.out, patch)
        write_json_new(args.manifest, report)
        print(json.dumps({"ok": True, "patch_size": len(patch),
                          "target_sha256": report["target_sha256"],
                          "distribution_approved": False}))
        return 0
    except KhcomError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 2
    except OSError as exc:
        print(json.dumps({"ok": False, "error": {"code": "file_io", "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
