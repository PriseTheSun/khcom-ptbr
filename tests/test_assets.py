"""Real format-owner checks over authored records and payloads."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.assets import inspect_asset_layouts
from khcom.errors import KhcomError
from khcom.upstream import load_assetgen


class AssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = load_assetgen()

    def fixture(self, changes=None):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        doc = {"group": "own", "types": {"Pointers": {"kind": "table", "type": "void*"}},
               "objects": {"us": [{"name": "own.s", "start": 0x08000010, "end": 0x08000020}]},
               "entries": [
                   {"name": "payload", "format": "raw", "us": {"address": 0x08000010, "size": 4}},
                   {"name": "refs", "record": "Pointers", "items": ["payload", "unknown_function"], "us": {"address": 0x08000014}},
                   {"name": "padding", "format": "fill", "value": 0xFF, "us": {"address": 0x0800001C, "size": 4}},
               ]}
        if changes:
            changes(doc)
        path = root / "own.yaml"
        path.write_text(yaml.safe_dump(doc))
        raw = bytes(16) + b"ours" + struct.pack("<II", 0x08000010, 0x0800FFFF) + b"\xff" * 4
        return raw, root, self.owner.Manifest(path)

    def inspect(self, raw, root, manifest):
        return inspect_asset_layouts(raw, [manifest], self.owner, source_root=root, commit="authored-fixture")

    def test_unresolved_fields_are_not_counted_as_verified_or_free(self):
        report = self.inspect(*self.fixture())
        self.assertEqual(report["asset_bytes"], 16)
        refs = report["assets"][1]
        self.assertEqual(refs["verification"], {"kind": "partial_record_match", "checked_bytes": 4})
        self.assertEqual(report["unresolved_reference_fields"], 1)
        self.assertEqual(refs["references"][1]["observed_value"], 0x0800FFFF)
        self.assertIsNone(report["assets"][2]["reusable"])
        self.assertFalse(report["complete_graphics_inventory"])
        self.assertFalse(report["runtime_verified"])

    def test_corrupt_known_pointer_and_fill_fail(self):
        raw, root, manifest = self.fixture()
        for changed in (raw[:20] + struct.pack("<I", 0x08000011) + raw[24:], raw[:-1] + b"\0"):
            with self.assertRaises(KhcomError):
                self.inspect(changed, root, manifest)

    def test_unknown_pointer_value_is_retained_without_claiming_match(self):
        raw, root, manifest = self.fixture()
        changed = raw[:24] + struct.pack("<I", 0xDEADBEEF) + raw[28:]
        result = self.inspect(changed, root, manifest)
        field = result["assets"][1]["references"][1]
        self.assertEqual(field["observed_value"], 0xDEADBEEF)
        self.assertFalse(field["resolved_against_asset_layout"])

    def test_manifest_identity_stays_separate_from_emitted_us_symbol(self):
        raw, root, manifest = self.fixture(lambda d: d["entries"][0]["us"].update(symbol="gOwnEmittedPayload"))
        report = self.inspect(raw, root, manifest)
        payload = report["assets"][0]
        self.assertEqual(payload["entry_name"], "payload")
        self.assertEqual(payload["id"], "us/asset/own/payload")
        self.assertEqual(payload["emitted_symbols"], ["gOwnEmittedPayload"])
        self.assertTrue(payload["emitted_symbol_addresses_resolved"])
        self.assertTrue(report["assets"][1]["references"][0]["resolved_against_asset_layout"])

    def test_layout_gaps_and_out_of_bounds_are_rejected(self):
        raw, root, manifest = self.fixture(lambda d: d["objects"]["us"][0].update(end=0x08000030))
        with self.assertRaises(KhcomError):
            self.inspect(raw, root, manifest)
        raw, root, manifest = self.fixture()
        with self.assertRaises(KhcomError):
            self.inspect(raw[:-1], root, manifest)


if __name__ == "__main__":
    unittest.main()
