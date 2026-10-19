"""Authored contracts, never a commercial ROM or extracted text fixture."""
import copy
from dataclasses import replace
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.credits import CreditTables, parse_line
from khcom.credits_edit import CreditEditContext, classify_matching_references, encode_catalog_credit, scan_credit_references, validate_credit_edit
from khcom.errors import KhcomError
from khcom.text import ROM_BASE
from khcom.upstream import sha256
from khcom.validation import TranslationPlan, apply_translation_plan, plan_translations


class CreditsEditTests(unittest.TestCase):
    def setUp(self):
        pages = bytearray(b"\xff" * 512)
        struct.pack_into("<HH", pages, 4, 512, 0)
        self.tables = CreditTables(bytes(pages) + bytes(range(128)) + b"\xff" * 64,
                                   tuple(0x8140 + n for n in range(256)),
                                   (bytes([4] * 128), bytes([5] * 128)))
        self.item = {"id": "authored", "byte_budget": 100}
        self.refs = {"script_references": [{"row": 4, "address": ROM_BASE, "target": ROM_BASE + 40}],
                     "unexpected_pointer_candidates": [], "interior_pointer_candidates": [], "aliases": []}
        glyphs = tuple({index: {"advance": width, "cell_height": height,
                                "nonzero_bounds": [0, 0, width, height]}
                        for index in range(128)} for width, height in ((4, 16), (5, 8)))
        self.context = CreditEditContext({"authored": [self.occurrence(4, 0)]}, {"authored": self.refs},
                                         self.tables, glyphs, (), {"scope": "synthetic"})

    def occurrence(self, row, font, raw=b"ABC\0"):
        return {**parse_line(raw, font, self.tables), "row": row, "font_before": font,
                "pointer_address": f"0x{ROM_BASE + row * 4:08X}"}

    def error(self, code, callback):
        with self.assertRaises(KhcomError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def validate(self, text, context=None):
        return validate_credit_edit(self.item, text, context or self.context)[1]

    def test_every_occurrence_uses_its_font_even_when_bytes_fit(self):
        context = replace(self.context, occurrences={"authored": [self.occurrence(4, 0), self.occurrence(24, 1)]})
        report = self.validate("A" * 43 + "{END}", context)
        self.assertEqual(report["candidate_bytes"], 44)
        self.assertEqual([o["candidate"]["runs"][0]["advance_pixels"] for o in report["occurrences"]], [172, 215])
        self.assertEqual([(d["code"], d["occurrence_row"]) for d in report["diagnostics"]], [("pixel_overflow", 24)])
        self.assertFalse(report["candidate_runtime_verified"])

    def test_preserves_prefix_state_color_and_alignment(self):
        context = replace(self.context, occurrences={"authored": [self.occurrence(4, 0, b"#1@=ABC\0")]})
        self.assertEqual(self.validate("#1@=DEF{END}", context)["diagnostics"], [])
        for text in ("#0@=DEF{END}", "#1=DEF{END}", "#1@-DEF{END}", "#1@+DEF{END}"):
            self.assertIn("controls_changed", [d["code"] for d in self.validate(text, context)["diagnostics"]])

    def test_structural_unobserved_and_two_column_paths_are_not_authorized(self):
        for raw, row, wanted in ((b"!\0", 4, "credits_structural_line"),
                                  (b"ABC\0", 627, "credits_occurrence_unobserved"),
                                  (b"~AB~C\0", 4, "credits_layout_path_unverified")):
            context = replace(self.context, occurrences={"authored": [self.occurrence(row, 0, raw)]})
            text = raw[:-1].decode("ascii") + "{END}"
            self.assertIn(wanted, [d["code"] for d in self.validate(text, context)["diagnostics"]])

    def test_reference_uncertainty_cannot_be_overridden_by_byte_fit(self):
        for key in ("unexpected_pointer_candidates", "interior_pointer_candidates"):
            refs = copy.deepcopy(self.refs); refs[key] = [{"address": ROM_BASE + 4}]
            context = replace(self.context, references={"authored": refs})
            self.assertEqual(self.validate("DEF{END}", context)["diagnostics"][0]["code"], "credits_reference_candidates")
        context = replace(self.context, references={})
        self.assertEqual(self.validate("DEF{END}", context)["diagnostics"][0]["code"], "references_unknown")

    def test_unknown_or_cropped_glyph_is_not_a_pixel_pass(self):
        glyphs = copy.deepcopy(self.context.glyphs)
        del glyphs[0][ord("D")]
        glyphs[0][ord("E")]["nonzero_bounds"][2] = 5
        report = self.validate("DE{END}", replace(self.context, glyphs=glyphs))
        self.assertEqual({d["code"] for d in report["diagnostics"]}, {"glyph_context_unknown", "glyph_clipped"})

    def test_editorial_terminators_and_unicode_never_hide_bytes(self):
        self.assertEqual(encode_catalog_credit("á{END}"), b"\x82\xa0\0")
        for text, error in (("ABC", "credits_terminator"), ("{END}A", "credits_terminator"),
                            ("A{END}{END}", "credits_terminator"), ("A{NL}{END}", "credits_control"),
                            ("A\0{END}", "credits_profile_character"),
                            ("a\u0301{END}", "credits_profile_nfc"), ("🧪{END}", "credits_profile_character")):
            self.error(error, lambda text=text: encode_catalog_credit(text))
        item = {**self.item, "byte_budget": 2}
        self.assertEqual(validate_credit_edit(item, "á{END}", self.context)[1]["diagnostics"][0]["code"], "byte_overflow")

    def test_reference_scan_keeps_known_extra_and_interior_values_distinct(self):
        data = bytearray(64)
        for offset, target in ((0, 40), (4, 40), (8, 41)):
            struct.pack_into("<I", data, offset, ROM_BASE + target)
        item = {"id": "authored", "allocation_span": {"start": 40, "end": 48},
                "source_span": {"start": 40, "end": 44}, "aliases": ["alias"]}
        row = {"id": "authored", "row": 0, "pointer_address": hex(ROM_BASE)}
        result = scan_credit_references(bytes(data), [item], [row])["authored"]
        self.assertEqual(len(result["script_references"]), 1)
        self.assertEqual(result["unexpected_pointer_candidates"][0]["address"], ROM_BASE + 4)
        self.assertEqual(result["interior_pointer_candidates"][0]["relative_to_text"], 1)
        self.assertEqual(result["aliases"], ["alias"])
        self.error("credits_pointer_alignment", lambda: scan_credit_references(bytes(data), [item], [{**row, "pointer_address": hex(ROM_BASE + 1)}]))
        self.error("credits_pointer", lambda: scan_credit_references(bytes(data), [item], [{**row, "pointer_address": hex(ROM_BASE + 8)}]))

    def test_plan_applies_exact_validated_bytes_and_preserves_unused_reserve(self):
        data = b"0123456789abcdef"
        write = {"owner": "authored", "start": 4, "end": 7, "source_sha256": sha256(b"456"), "payload": b"X\0Z"}
        plan = TranslationPlan({"source_sha256": sha256(data), "blocked_items": 0, "release_approved": False}, (write,))
        output, report = apply_translation_plan(data, plan)
        self.assertEqual(output, b"0123X\0Z789abcdef")
        self.assertTrue(report["outside_writes_unchanged"])
        self.assertFalse(report["candidate_runtime_verified"])
        self.error("text_plan_identity", lambda: apply_translation_plan(data + b"!", plan))
        self.error("text_write_source", lambda: apply_translation_plan(data, replace(plan, writes=({**write, "source_sha256": "0" * 64},))))
        self.error("text_write_overlap", lambda: apply_translation_plan(data, replace(plan, writes=(write, write))))
        blocked = replace(plan, report={**plan.report, "blocked_items": 1, "diagnostic_counts": {"test": 1}})
        self.error("localization_blocked", lambda: apply_translation_plan(data, blocked))

    def test_matching_owner_can_classify_encoded_data_but_keeps_real_extra_reference(self):
        data = b"authored fixture"
        refs = {"authored": {**copy.deepcopy(self.refs),
                           "interior_pointer_candidates": [{"address": ROM_BASE + 4, "target": ROM_BASE + 41}],
                           "unexpected_pointer_candidates": [{"address": ROM_BASE + 8, "target": ROM_BASE + 40}]}}
        facts = {"schema": "khcom-matching-facts-v1", "baseline_byte_identical": True,
                 "rom": {"sha256": sha256(data)}, "rebuild": {}, "elf": {}, "map": {}, "objects": [], "limitations": [],
                 "candidate_words": [{"source_offset": 4, "value": ROM_BASE + 41, "classification": "encoded_asset_data_verified"},
                                     {"source_offset": 8, "value": ROM_BASE + 40, "classification": "linker_abs32_reference", "relocation": {"symbol": "authored"}}]}
        evidence = classify_matching_references(data, refs, facts)
        self.assertEqual(refs["authored"]["interior_pointer_candidates"], [])
        self.assertEqual(len(refs["authored"]["encoded_asset_coincidences"]), 1)
        self.assertEqual(len(refs["authored"]["unexpected_pointer_candidates"]), 1)
        self.assertEqual(refs["authored"]["linker_references"], [{"symbol": "authored"}])
        self.assertEqual(evidence["rom"]["sha256"], sha256(data))
        self.error("credits_matching_identity", lambda: classify_matching_references(data + b"!", refs, facts))
        changed = copy.deepcopy(facts); changed["candidate_words"][1]["value"] += 1
        self.error("credits_matching_word", lambda: classify_matching_references(data, refs, changed))

    def test_profile_cannot_skip_rom_identity_or_select_unrecognized_contract(self):
        self.error("text_profile", lambda: plan_translations(b"", {}, profile_id="invented"))
        self.error("text_profile_identity", lambda: plan_translations(b"", {}, profile_id="staff-roll-ptbr-v1", check_identity=False))
        self.error("text_matching_profile", lambda: plan_translations(b"", {}, matching_tree=Path("fake")))


if __name__ == "__main__":
    unittest.main()
