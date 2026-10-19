#!/usr/bin/env python3
"""Smoke privado com saída pública fechada; não equivale a QA completo de release."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from khcom.io import read_file, write_json_new
from khcom.package import digest
from khcom.rom import read_rom


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    summary = {"schema_version": 1, "operation": "private-game-smoke", "commit": args.commit,
               "result": "fail", "complete_campaign_qa": False, "release_approved": False}
    try:
        rom_path = Path(os.environ["KHCOM_QA_ROM"])
        package = Path(os.environ["KHCOM_QA_PACKAGE"])
        private_root = Path(os.environ["KHCOM_PRIVATE_QA_DIR"])
        if not private_root.is_dir() or private_root.is_symlink():
            raise ValueError("private_storage_not_prepared")
        original = read_rom(rom_path)
        package_manifest = json.loads(read_file(package, 1024 * 1024))
        summary["source_sha256"] = original.identity["sha256"]
        summary["build_sha256"] = digest(read_file(args.binary, 128 * 1024 * 1024))
        work = Path(tempfile.mkdtemp(prefix="khcom-qa-", dir=private_root))
        with (work / "process.log").open("wb") as output:
            result = subprocess.run([str(args.binary.absolute()), "--rom", str(rom_path), "--package", str(package),
                                     "--data-dir", str(work / "data"), "--headless", "--mute", "--frames", "180",
                                     "--report", str(work / "runtime.json")],
                                    stdout=output, stderr=subprocess.STDOUT, timeout=120, check=False)
        if result.returncode:
            raise ValueError("desktop_smoke_failed")
        runtime = json.loads(read_file(work / "runtime.json", 1024 * 1024))
        if runtime.get("simulated_frames") != 180 or runtime.get("save_error") is not False:
            raise ValueError("desktop_report_incomplete")
        if runtime.get("target_sha256") != package_manifest.get("target_sha256"):
            raise ValueError("target_digest_mismatch")
        after = read_rom(rom_path)
        if after.identity != original.identity or after.data != original.data:
            raise ValueError("source_not_preserved")
        # Only selected primitive measurements cross the private/public boundary.
        for key in ("simulated_frames", "elapsed_seconds", "active_wall_seconds", "audio_queue_peak_bytes"):
            if type(runtime.get(key)) not in (int, float):
                raise ValueError("report_field_type")
            summary[key] = runtime[key]
        summary.update(result="pass", target_sha256=runtime["target_sha256"],
                       original_preserved=True, dummy_devices=True,
                       coverage="180-frame boot only; no captures, ROM, saves or application log exported")
    except Exception:
        # Detailed process output remains in the owner-controlled private directory.
        summary["failure"] = "private_smoke_failed_or_configuration_missing"
    write_json_new(args.report, summary)
    print(json.dumps(summary))
    return 0 if summary["result"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
