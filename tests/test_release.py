import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.package import digest
from khcom.release import DELIVERABLES, GATES, verify


class ReleaseGateTests(unittest.TestCase):
    def fixture(self, root):
        manifest = {"schema_version": 1, "commit": "a" * 40, "status": "complete",
                    **{k: "b" * 64 for k in ("source_sha256", "target_sha256", "patch_sha256", "inventory_sha256")},
                    "artifacts": {}, "gates": {}}
        for name in DELIVERABLES:
            data = ("authored " + name).encode()
            (root / name).write_bytes(data)
            manifest["artifacts"][name] = {"path": name, "sha256": digest(data)}
        for name in GATES:
            receipt = {"schema_version": 1, "gate": name, "commit": manifest["commit"], "result": "pass",
                       "artifact_sha256": {n: d["sha256"] for n, d in manifest["artifacts"].items()},
                       **{k: manifest[k] for k in ("source_sha256", "target_sha256", "patch_sha256", "inventory_sha256")},
                       "evidence_sha256": ["c" * 64], "reviewer": "Synthetic fixture, not human approval",
                       "unknowns": 0, "unreviewed": 0, "untranslated": 0, "items_total": 18083,
                       "developer_id_verified": True, "notarization_status": "Accepted", "staple_verified": True,
                       "gatekeeper_clean_download": True, "human_approval": True, "execution": "native-physical"}
            self.receipt(root, manifest, name, receipt)
        return manifest

    def receipt(self, root, manifest, name, value):
        data = json.dumps(value).encode()
        path = name + ".json"
        (root / path).write_bytes(data)
        manifest["gates"][name] = {"path": path, "sha256": digest(data)}

    def test_positive_fixture_and_bad_artifact_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m = self.fixture(root)
            self.assertTrue(verify(root, m, "a" * 40)["release_gate_passed"])
            (root / "windows-installer").write_bytes(b"changed")
            with self.assertRaises(KhcomError) as caught:
                verify(root, m, "a" * 40)
            self.assertEqual(caught.exception.code, "release_digest")

    def test_missing_qa_signature_human_and_native_checks_fail(self):
        mutations = [("coverage", "unknowns", 1), ("owner-review", "human_approval", False),
                     ("apple-signature-notarization", "notarization_status", "Not Submitted"),
                     ("macos-intel-native", "execution", "Rosetta"), ("sora-campaign", "result", "pending"),
                     ("riku-campaign", "target_sha256", "d" * 64)]
        for gate, key, value in mutations:
            with self.subTest(gate=gate), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                m = self.fixture(root)
                receipt = json.loads((root / (gate + ".json")).read_bytes())
                receipt[key] = value
                self.receipt(root, m, gate, receipt)
                with self.assertRaises(KhcomError):
                    verify(root, m, "a" * 40)

    def test_incomplete_wrong_commit_missing_gate_and_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m = self.fixture(root)
            for change in [lambda c: c.update(status="experimental"), lambda c: c.update(commit="f" * 40),
                           lambda c: c["gates"].pop("sora-campaign"),
                           lambda c: c["artifacts"]["windows-installer"].update(path="../outside")]:
                changed = copy.deepcopy(m)
                change(changed)
                with self.assertRaises(KhcomError):
                    verify(root, changed, "a" * 40)


if __name__ == "__main__":
    unittest.main()
