import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.package import architecture, audit, deterministic_zip, digest


def macho(cpu=0x100000C):
    return struct.pack("<IIIIIIII", 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0)


class PackageTests(unittest.TestCase):
    def fixture(self, root):
        entries = {"program": (macho(), "executable"), "notices.txt": (b"authored notices", "notices"),
                   "source.zip": (b"authored fixture", "sources"), "sbom.json": (b"{}", "sbom"),
                   "readme.txt": (b"authored instructions", "instructions")}
        manifest = {"schema_version": 1, "kind": "desktop-without-game-data", "architectures": ["arm64"], "files": []}
        for name, (data, role) in entries.items():
            (root / name).write_bytes(data)
            manifest["files"].append({"path": name, "role": role, "size": len(data), "sha256": digest(data)})
        return manifest

    def test_package_rechecks_contents_and_does_not_approve_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.fixture(root)
            result = audit(root, manifest)
            self.assertTrue(result["audit_passed"])
            self.assertFalse(result["release_approved"])
            (root / "program").write_bytes(macho(0x1000007))
            with self.assertRaises(KhcomError) as error:
                audit(root, manifest)
            self.assertEqual(error.exception.code, "package_digest")

    def test_missing_extra_and_nested_reserved_files_are_rejected(self):
        for name in ["extra.txt", "nested/package-manifest.json", "private/dump.json"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                manifest = self.fixture(root)
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"unlisted")
                with self.assertRaises(KhcomError):
                    audit(root, manifest)
                target.unlink()
                (root / "source.zip").unlink()
                with self.assertRaises(KhcomError) as error:
                    audit(root, manifest)
                self.assertEqual(error.exception.code, "package_missing")

    def test_forbidden_payload_and_symlink_cannot_hide_behind_inventory(self):
        for name in ["data.gba", "private/data.json", "patch.bps"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                manifest = self.fixture(root)
                manifest["files"].append({"path": name, "role": "sources", "size": 0, "sha256": digest(b"")})
                with self.assertRaises(KhcomError) as error:
                    audit(root, manifest)
                self.assertEqual(error.exception.code, "package_game_data")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.fixture(root)
            (root / "link").symlink_to(root / "program")
            with self.assertRaises(KhcomError) as error:
                audit(root, manifest)
            self.assertEqual(error.exception.code, "package_symlink")

    def test_duplicate_paths_unknown_roles_and_missing_license_materials_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.fixture(root)
            for mutation in [lambda m: m["files"].append(m["files"][0]),
                             lambda m: m["files"][0].update(path="../outside"),
                             lambda m: m["files"][0].update(role="private-data"),
                             lambda m: m["files"][1].update(role="instructions")]:
                changed = copy.deepcopy(manifest)
                mutation(changed)
                with self.assertRaises(KhcomError):
                    audit(root, changed)

    def test_universal_identity_and_bounds(self):
        arm, intel = macho(), macho(0x1000007)
        universal = struct.pack(">II", 0xCAFEBABE, 2)
        universal += struct.pack(">IIIII", 0x100000C, 0, 48, 32, 0)
        universal += struct.pack(">IIIII", 0x1000007, 0, 80, 32, 0)
        universal += arm + intel
        self.assertEqual(architecture(universal), ["arm64", "x86_64"])
        for invalid in [universal[:-1], universal[:48] + arm + arm, b"MZ" + bytes(62)]:
            with self.assertRaises(KhcomError):
                architecture(invalid)

    def test_archive_is_deterministic_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.zip", Path(folder) / "b.zip"
            entries = [("src/a.cpp", b"own source", 0o644), ("run", b"own executable", 0o755)]
            deterministic_zip(a, entries)
            deterministic_zip(b, list(reversed(entries)))
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with self.assertRaises(KhcomError):
                deterministic_zip(a, entries)


if __name__ == "__main__":
    unittest.main()
