import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.batches import plan, verify_partition, editable_batches, assemble
from khcom.errors import KhcomError


class BatchTests(unittest.TestCase):
    def fixture(self):
        texts = [{"id": f"text/{i}", "domain": "event_text", "unit": "event_01",
                  "source_sha256": str(i) * 64, "source_text": "Texto próprio. {END}", "translation": None}
                 for i in range(5)]
        catalog = {"format_version": 1, "origin": {"sha256": "a" * 64}, "upstream": {},
                   "items": texts, "intervals": [], "pools": []}
        inventory = {"source_sha256": "a" * 64, "discovery_closed": False, "items": [
            {"id": t["id"], "kind": "text", "domain": t["domain"], "source_sha256": t["source_sha256"], "span": [i, i+1]}
            for i, t in enumerate(texts)] + [{"id": "resource/own/atlas", "kind": "resource", "domain": "tiles4",
                                            "source_sha256": "b" * 64, "span": [20, 30]}]}
        return catalog, inventory

    def test_partition_and_utf8_assembly_preserve_all_source_fields(self):
        c, i = self.fixture(); p = plan(c, i, max_items=2)
        self.assertEqual(len(p["batches"]), 4)
        self.assertFalse(p["full_translation"])
        self.assertFalse(p["discovery_closed"])
        sessions = editable_batches(p, c)
        self.assertEqual(assemble(p, sessions, c), c)
        sessions[0]["items"][0]["translation"] = "Ação, memória e coração.{END}"
        merged = assemble(p, sessions, c)
        self.assertIn("Ação", merged["items"][0]["translation"])
        self.assertIsNone(c["items"][0]["translation"])

    def test_missing_duplicate_new_items_and_changed_origins_reopen_partition(self):
        c, i = self.fixture(); p = plan(c, i, max_items=2)
        for mutation in [lambda x: x["batches"].pop(),
                         lambda x: x["batches"][0]["items"].append(x["batches"][0]["items"][0]),
                         lambda x: x.update(inventory_sha256="0" * 64)]:
            bad = copy.deepcopy(p); mutation(bad)
            with self.assertRaises(KhcomError): verify_partition(bad, i)
        other = copy.deepcopy(i); other["items"][0]["source_sha256"] = "f" * 64
        with self.assertRaises(KhcomError): verify_partition(p, other)

    def test_swapped_session_or_source_edit_never_becomes_translation(self):
        c, i = self.fixture(); p = plan(c, i, max_items=2)
        sessions = editable_batches(p, c)
        for mutate in [lambda s: s.pop(), lambda s: s.append(s[0]),
                       lambda s: s[0]["items"][0].update(source_text="changed origin"),
                       lambda s: s[0].update(plan_sha256="0" * 64)]:
            bad = copy.deepcopy(sessions); mutate(bad)
            with self.assertRaises(KhcomError): assemble(p, bad, c)

    def test_foreign_or_unknown_context_is_not_assigned_to_a_scene(self):
        c, i = self.fixture()
        with self.assertRaises(KhcomError):
            plan(c, i, {"schema": "khcom-event-occurrences-v1", "source_sha256": "f" * 64})
        p = plan(c, i)
        self.assertTrue(all(b["campaign"] is None and b["qa_route"] is None for b in p["batches"]))


if __name__ == "__main__": unittest.main()
