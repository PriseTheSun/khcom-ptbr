import struct
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from map_rom import map_regions
from khcom.upstream import sha256


class MappingTests(unittest.TestCase):
    def test_unknowns_partition_entire_rom_and_equal_words_stay_candidates(self):
        data = bytearray(512)
        struct.pack_into("<I", data, 0, 0xEA00002E)
        struct.pack_into("<I", data, 300, 0x080000C0)
        catalog = {"origin": {"size": 512}, "upstream": {"commit": "synthetic"},
                   "intervals": [{"id": "own/text", "kind": "text", "span": {"start": 192, "end": 200}}]}
        result = map_regions(bytes(data), catalog)
        self.assertEqual(0x080000C0, result["entry_branch"]["target"])
        self.assertEqual(312, result["unknown_bytes"])
        self.assertEqual(512, sum(r["end"] - r["start"] for r in result["regions"]))
        self.assertTrue(result["pointer_scan"]["complete_for_aligned_exact_words"])
        self.assertEqual(0, result["pointer_scan"]["confirmed_references"])
        self.assertEqual("candidate_not_confirmed_reference", result["pointer_scan"]["candidates"][0]["status"])
        catalog["intervals"][0]["span"]["start"] = 4
        with self.assertRaises(KhcomError) as caught:
            map_regions(bytes(data), catalog)
        self.assertEqual("map_ownership", caught.exception.code)

    def test_asset_identity_overlap_and_partial_evidence_are_preserved(self):
        data = bytes(512)
        catalog = {"origin": {"size": 512}, "upstream": {"commit": "synthetic"}, "intervals": []}
        assets = {"source_sha256": sha256(data), "assets": [{"id": "own/asset", "kind": "asset", "start": 300, "end": 320, "verification": {"kind": "partial_record_match", "checked_bytes": 12}}]}
        result = map_regions(data, catalog, assets)
        self.assertEqual(result["unknown_bytes"], 300)
        observed = next(r for r in result["regions"] if r.get("id") == "own/asset")
        self.assertEqual(observed["verification"]["kind"], "partial_record_match")
        assets["source_sha256"] = "0" * 64
        with self.assertRaises(KhcomError) as caught:
            map_regions(data, catalog, assets)
        self.assertEqual(caught.exception.code, "map_identity")
        assets["source_sha256"] = sha256(data)
        assets["assets"][0]["start"] = 180
        with self.assertRaises(KhcomError) as caught:
            map_regions(data, catalog, assets)
        self.assertEqual(caught.exception.code, "map_ownership")


if __name__ == "__main__":
    unittest.main()
