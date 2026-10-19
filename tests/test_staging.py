import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from stage_sources import stage


class StagingTests(unittest.TestCase):
    def test_source_allowlist_excludes_data_and_bundled_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            fixtures = {"README.md": "own documentation", "tools/identify.py": "# own source",
                        "core/session.cpp": "// own source", "private/rom.gba": "private",
                        "private/text.json": "private", ".deps/third-party.cpp": "dependency",
                        "build/program": "binary", "tools/dump.gba": "private",
                        "tools/__pycache__/cached.pyc": "cache"}
            for relative, content in fixtures.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            destination = Path(temporary) / "stage"
            report = stage(root, destination)
            self.assertEqual({"README.md", "tools/identify.py", "core/session.cpp"},
                             {item["path"] for item in report["files"]})
            self.assertFalse(report["release_ready"])
            self.assertFalse((destination / "private").exists())
            with self.assertRaises(KhcomError):
                stage(root, destination)

    def test_symlink_cannot_import_files_outside_source_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            outside = Path(temporary) / "private"
            outside.mkdir()
            (outside / "payload.py").write_text("private")
            (root / "tools").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(KhcomError) as caught:
                stage(root, Path(temporary) / "out")
            self.assertEqual("stage_symlink", caught.exception.code)

    def test_nested_workflow_area_rejects_symlink_ancestor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            outside = Path(temporary) / "private"
            (outside / "workflows").mkdir(parents=True)
            (outside / "workflows" / "ci.yml").write_text("private")
            (root / ".github").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(KhcomError) as caught:
                stage(root, Path(temporary) / "out")
            self.assertEqual("stage_symlink", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
