import copy
import struct
import unittest

from tools.khcom.errors import KhcomError
from tools.khcom.event_contract import event_occurrences, BASE
from tools.khcom.upstream import sha256


def fixture():
    data = bytearray(1024)
    symbols, refs = [], []
    def obj(name, offset, size):
        symbols.append({"name": name, "address": BASE + offset, "size": size, "type": "STT_OBJECT"})
    def pointer(source, target, name):
        struct.pack_into("<I", data, source, BASE + target)
        refs.append({"source_offset": source, "target_address": BASE + target,
                     "symbol": name, "addend": 0, "owner": "fixture.o", "kind": "R_ARM_ABS32"})
    obj("gEventSequenceDefs", 0, 8)
    obj("gMsgwinTextX", 8, 16)
    obj("gMsgwinTextY", 24, 16)
    struct.pack_into("<4i", data, 8, 4096, 4096, 18432, 18432)
    struct.pack_into("<4i", data, 24, 3584, 28160, 3584, 28160)
    for event, definition, script in ((0, 64, 160), (1, 112, 208)):
        obj(f"definition{event}", definition, 48)
        obj(f"script{event}", script, 48)
        pointer(event * 4, definition, f"definition{event}")
        pointer(definition + 12, script, f"script{event}")
        for entry in range(2):
            offset = script + entry * 24
            struct.pack_into("<IIIB3xIHH", data, offset,
                             62 if event else 0, 1, (3 if event else 1) if not entry else 4,
                             1, 0, 0 if not entry else 0x8000, entry * 20)
            pointer(offset + 16, 600 + entry * 4, f"text{entry}")
    data[600:608] = b"A\x00\x00\x00B\x00\x00\x00"
    pointer(500, 602, "text0")  # An extra reference to the middle of text0.
    catalog = {"origin": {"sha256": sha256(data)}, "items": [
        {"id": f"text{i}", "domain": "event_text", "codec_id": "game",
         "source_span": {"start": 600 + i * 4, "end": 604 + i * 4}} for i in range(2)]}
    facts = {"schema": "khcom-matching-facts-v1", "rom": {"sha256": sha256(data)},
             "baseline_byte_identical": True, "elf_rom_agreement": {"compared": True},
             "symbols": symbols, "relocations": refs}
    return bytes(data), catalog, facts


class EventContractTests(unittest.TestCase):
    def test_occurrences_keep_position_portrait_and_interior_edges(self):
        data, catalog, facts = fixture()
        result = event_occurrences(data, catalog, facts)
        self.assertEqual(result["event_count"], 2)
        self.assertEqual(result["occurrence_count"], 4)
        self.assertEqual([row["origin"] for row in result["occurrences"]],
                         [[16, 108], [16, 108], [46, 108], [46, 108]])
        self.assertEqual(result["unknown_counts"], {})
        extra = result["references_by_id"]["text0"][-1]
        self.assertTrue(extra["interior"])
        self.assertFalse(extra["known_script_reference"])
        self.assertFalse(result["edit_authorized"])

    def test_aliases_retain_both_ids_and_refs(self):
        data, catalog, facts = fixture()
        alias = copy.deepcopy(catalog["items"][0]); alias["id"] = "alias0"
        catalog["items"].append(alias)
        result = event_occurrences(data, catalog, facts)
        self.assertEqual(result["occurrences"][0]["catalog_ids"], ["text0", "alias0"])
        self.assertEqual(result["references_by_id"]["text0"], result["references_by_id"]["alias0"])

    def test_shared_pool_same_codec_is_measured_but_jp_stays_unknown(self):
        data, catalog, facts = fixture()
        catalog["items"][0]["domain"] = "card_message_text"
        catalog["items"][1]["codec_id"] = "jp"
        result = event_occurrences(data, catalog, facts)
        self.assertEqual(result["occurrences"][0]["unknowns"], [])
        self.assertEqual(result["unknown_counts"], {"text_consumer_codec_mismatch": 2})

    def test_first_keep_is_unknown_and_early_end_is_not_silently_truncated(self):
        data, catalog, facts = fixture()
        data = bytearray(data)
        struct.pack_into("<I", data, 168, 4)
        struct.pack_into("<H", data, 180, 0x8000)
        catalog["origin"]["sha256"] = facts["rom"]["sha256"] = sha256(data)
        result = event_occurrences(bytes(data), catalog, facts)
        self.assertIsNone(result["occurrences"][0]["origin"])
        self.assertEqual(result["unknown_counts"]["position_state_unknown"], 2)
        self.assertIn("script_end_not_at_symbol_boundary", result["occurrences"][0]["unknowns"])

    def test_unverified_pointer_and_ambiguous_symbol_fail(self):
        for mutate, expected in ((lambda f: f["relocations"].pop(0), "event_reference"),
                                  (lambda f: f["symbols"].append(copy.deepcopy(f["symbols"][0])), "event_symbol")):
            data, catalog, facts = fixture(); mutate(facts)
            with self.assertRaises(KhcomError) as caught:
                event_occurrences(data, catalog, facts)
            self.assertEqual(caught.exception.code, expected)

    def test_identity_and_partial_overlap_fail(self):
        data, catalog, facts = fixture()
        with self.assertRaises(KhcomError) as caught:
            event_occurrences(data + b"x", catalog, facts)
        self.assertEqual(caught.exception.code, "event_identity")
        catalog["items"][0]["source_span"]["end"] += 1
        with self.assertRaises(KhcomError) as caught:
            event_occurrences(data, catalog, facts)
        self.assertEqual(caught.exception.code, "event_catalog_overlap")


if __name__ == "__main__":
    unittest.main()
