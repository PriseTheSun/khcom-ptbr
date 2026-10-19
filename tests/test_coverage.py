import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.coverage import SURFACES, bind_inventory, canonical_digest, evaluate
from khcom.errors import KhcomError


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = b"Authored fixture, not commercial content."
        digest = hashlib.sha256(self.source).hexdigest()
        self.item = {"id": "fixture/line", "kind": "text", "domain": "dialogue",
                     "source_sha256": digest, "span": [0, len(self.source)],
                     "occurrences_closed": True,
                     "occurrences": [{"id": "fixture/scene/line", "surface": "sora"}]}
        self.inventory = {"schema_version": 1, "source_sha256": digest, "items": [self.item],
                          "surfaces": list(SURFACES), "discovery_closed": True, "unknowns": []}
        self.ledger = {"schema_version": 1, "source_sha256": digest,
                       "target_sha256": "a" * 64, "build_sha256": "b" * 64,
                       "patch_sha256": "c" * 64, "inventory_sha256": canonical_digest(self.inventory),
                       "receipts": {}, "surfaces": {}, "items": []}
        self.review = {"id": self.item["id"], "source_sha256": digest,
                       "classification": "visible_text", "translation_sha256": "d" * 64,
                       "unchanged": False, "visual_evidence": {}}
        self.ledger["items"].append(self.review)
        for kind in ("classification", "linguistic", "binary"):
            self.review[kind + "_evidence"] = self.receipt(kind, self.item["id"])
        self.review["visual_evidence"]["fixture/scene/line"] = self.receipt("visual", "fixture/scene/line")
        for surface in SURFACES:
            self.ledger["surfaces"][surface] = self.receipt("surface", surface)

    def receipt(self, kind, subject):
        identity = f"receipt-{len(self.ledger['receipts'])}"
        payload = {"schema_version": 1, "kind": kind, "subject_id": subject,
                   "source_sha256": self.inventory["source_sha256"],
                   "target_sha256": self.ledger["target_sha256"],
                   "build_sha256": self.ledger["build_sha256"],
                   "translation_sha256": self.review["translation_sha256"],
                   "result": "pass", "reviewer": "synthetic fixture",
                   "method": "Synthetic contract; no game or human review claimed."}
        path = self.root / (identity + ".json")
        raw = json.dumps(payload).encode()
        path.write_bytes(raw)
        self.ledger["receipts"][identity] = {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest()}
        return identity

    def result(self):
        return evaluate(self.inventory, self.ledger, self.root)

    def test_complete_synthetic_contract_has_all_denominators_but_no_release_approval(self):
        result = self.result()
        self.assertTrue(result["coverage_complete"])
        self.assertFalse(result["release_approved"])
        self.assertEqual(result["denominators_by_domain"], {"dialogue": 1})
        self.assertEqual(result["occurrences_total"], 1)
        self.assertEqual(result["counts"]["verified_occurrences"], 1)

    def test_new_resource_or_occurrence_reopens_the_gate(self):
        added = copy.deepcopy(self.item)
        added["id"] = "fixture/new-line"
        added["occurrences"] = []
        added["occurrences_closed"] = False
        self.inventory["items"].append(added)
        result = self.result()
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["items_total"], 2)
        self.assertIn("inventory_changed", result["blocker_counts"])
        self.assertIn("item_review_missing_or_stale", result["blocker_counts"])
        self.inventory["items"].pop()
        self.item["occurrences"].append({"id": "fixture/new-scene", "surface": "riku"})
        self.assertIn("visual_review_missing", self.result()["blocker_counts"])

    def test_unknown_surface_or_open_discovery_blocks_all_dialogues_complete(self):
        self.inventory["unknowns"] = ["Unclassified graphic menu"]
        self.assertIn("discovery_open", self.result()["blocker_counts"])
        self.inventory["unknowns"] = []
        del self.ledger["surfaces"]["graphics"]
        self.assertIn("surface_review_missing", self.result()["blocker_counts"])

    def test_missing_corrupt_or_wrong_target_receipt_is_not_review(self):
        key = self.review["binary_evidence"]
        descriptor = self.ledger["receipts"][key]
        path = self.root / descriptor["path"]
        path.write_text("tampered")
        self.assertIn("binary_review_missing", self.result()["blocker_counts"])
        self.review["binary_evidence"] = self.receipt("binary", self.item["id"])
        self.ledger["target_sha256"] = "f" * 64
        self.assertFalse(self.result()["coverage_complete"])

    def test_translation_change_invalidates_linguistic_binary_and_visual_receipts(self):
        self.review["translation_sha256"] = "e" * 64
        codes = self.result()["blocker_counts"]
        self.assertIn("linguistic_review_missing", codes)
        self.assertIn("binary_review_missing", codes)
        self.assertIn("visual_review_missing", codes)

    def test_unchanged_text_needs_specific_bound_exception(self):
        self.review["unchanged"] = True
        self.assertIn("unchanged_without_specific_exception", self.result()["blocker_counts"])
        self.review["exception"] = {"category": "proper_name", "reason": "Specific fixture person name.",
                                    "evidence": self.receipt("name_exception", self.item["id"])}
        self.assertTrue(self.result()["coverage_complete"])

    def test_empty_inventory_and_duplicate_or_removed_owner_cannot_pass(self):
        actual = copy.deepcopy(self.inventory)
        self.inventory["items"] = []
        self.assertIn("empty_inventory", self.result()["blocker_counts"])
        with self.assertRaises(KhcomError) as caught:
            bind_inventory(self.inventory, actual, self.source)
        self.assertEqual(caught.exception.code, "coverage_membership")
        actual["items"].append(copy.deepcopy(actual["items"][0]))
        with self.assertRaises(KhcomError):
            evaluate(actual, self.ledger, self.root)

    def test_provenance_and_new_discovery_spans_bind_to_source_bytes(self):
        actual = copy.deepcopy(self.inventory)
        bind_inventory(self.inventory, actual, self.source)
        self.item["span"][1] -= 1
        with self.assertRaises(KhcomError):
            bind_inventory(self.inventory, actual, self.source)
        self.item["span"][1] += 1
        new = {**self.item, "id": "new", "span": [0, 4],
               "source_sha256": hashlib.sha256(self.source[:4]).hexdigest()}
        self.inventory["items"].append(new)
        bind_inventory(self.inventory, actual, self.source)
        new["source_sha256"] = "f" * 64
        with self.assertRaises(KhcomError):
            bind_inventory(self.inventory, actual, self.source)

    def test_receipt_paths_cannot_escape_evidence_root(self):
        self.ledger["receipts"][self.review["binary_evidence"]]["path"] = "../outside.json"
        self.assertIn("binary_review_missing", self.result()["blocker_counts"])


if __name__ == "__main__":
    unittest.main()
