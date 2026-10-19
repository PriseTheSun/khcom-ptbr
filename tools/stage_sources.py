#!/usr/bin/env python3
"""Stage authored source only. This is not the executable release packager."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from khcom.errors import KhcomError
from khcom.io import read_file, write_json_new, write_new

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", ".gitignore", "pyproject.toml", "requirements-tools.txt", "requirements-build.txt", "CMakeLists.txt"}
SOURCE_AREAS = {
    "app": {".cpp", ".hpp"}, "core": {".cpp", ".hpp"},
    "platform": {".cpp", ".hpp", ".txt"}, "cmake": {".cmake"},
    "packaging": {".iss"},
    "tools": {".py"}, "tests": {".py", ".cpp", ".hpp"},
    "manifests": {".json"}, "docs": {".md"},
    ".github/workflows": {".yml"},
    ".github": {".yaml"},
}


def inventory(root: Path) -> list[tuple[Path, bytes]]:
    entries = []
    candidates = [root / name for name in ROOT_FILES if (root / name).exists()]
    for directory, suffixes in SOURCE_AREAS.items():
        parent = root / directory
        ancestor = root
        for part in Path(directory).parts:
            ancestor /= part
            if ancestor.is_symlink():
                raise KhcomError("stage_symlink", "Uma área de fontes é um link.", path=str(ancestor))
        if not parent.exists():
            continue
        for path in parent.rglob("*"):
            if path.is_symlink():
                raise KhcomError("stage_symlink", "Links não entram no pacote de fontes.", path=str(path))
            if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts:
                candidates.append(path)
    for path in sorted(candidates):
        if path.is_symlink():
            raise KhcomError("stage_symlink", "Links não entram no pacote de fontes.", path=str(path))
        entries.append((path.relative_to(root), read_file(path, 4 * 1024 * 1024)))
    return entries


def stage(root: Path, destination: Path) -> dict:
    entries = inventory(root)
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise KhcomError("stage_destination", "Escolha uma pasta de staging nova.",
                         path=str(destination), reason=str(exc)) from exc
    report = {"schema_version": 1, "kind": "authored-source-only", "release_ready": False,
              "excluded_areas": ["private", ".deps", ".venv", ".build-tools", "build*", "dist", "stage"],
              "files": []}
    # On error, leave the partial owned directory and report the failure. Never
    # remove a pre-existing directory or pretend that partial staging succeeded.
    for relative, data in entries:
        write_new(destination / relative, data)
        report["files"].append({"path": relative.as_posix(), "size": len(data),
                                "sha256": hashlib.sha256(data).hexdigest()})
    write_json_new(destination / "source-inventory.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = stage(ROOT, args.out)
        print(json.dumps({"ok": True, "files": len(report["files"]),
                          "path": str(args.out.absolute()), "release_ready": False}))
        return 0
    except KhcomError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
