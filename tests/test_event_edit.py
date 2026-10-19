import copy
import struct
import unittest

from tools.khcom.event_edit import EventEditContext, validate_event_edit


def encoded(text):
    return text.encode("utf-16le") + b"\0\0"


def context(source="IIII", occurrences=1):
    widths = [6] * 256
    widths[ord("I")], widths[ord("W")] = 3, 8
    bounds = [[0, 2, min(width, 6), 12] for width in widths]
    rows = [{"event_id": index, "entry_index": 0, "entry_offset": 24 * index,
             "origin": [16 if index == 0 else 72, 108], "alternate_palette": None,
             "catalog_ids": ["text"], "unknowns": [],
             "references": {"text": {"source_offset": 16 + index * 24}}} for index in range(occurrences)]
    refs = [{"source_offset": 16 + index * 24, "interior": False, "known_script_reference": True}
            for index in range(occurrences)]
    return EventEditContext({"text": rows}, {"text": refs}, widths, bounds,
                            {"text": encoded(source)}, {})


class EventEditTests(unittest.TestCase):
    def test_all_occurrences_are_measured_without_global_runtime_approval(self):
        result = validate_event_edit({"id": "text"}, encoded("II"), context(occurrences=2))
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(len(result["occurrences"]), 2)
        self.assertEqual([r["source_page_envelopes"][0]["right_exclusive"] for r in result["occurrences"]], [28, 84])
        self.assertFalse(result["candidate_runtime_verified"])

    def test_same_bytes_can_overflow_pixels(self):
        self.assertEqual(len(encoded("IIII")), len(encoded("WWWW")))
        result = validate_event_edit({"id": "text"}, encoded("WWWW"), context())
        self.assertIn("event_pixel_overflow", [d["code"] for d in result["diagnostics"]])

    def test_unknown_extra_and_interior_consumers_block(self):
        for extra in ({"source_offset": 999, "interior": False, "known_script_reference": False},
                      {"source_offset": 999, "interior": True, "known_script_reference": False}):
            ctx = context();ctx.references["text"].append(extra)
            result = validate_event_edit({"id": "text"}, encoded("II"), ctx)
            self.assertIn("event_extra_or_unknown_consumers", [d["code"] for d in result["diagnostics"]])
        ctx = context();ctx.occurrences["text"].clear()
        result = validate_event_edit({"id": "text"}, encoded("II"), ctx)
        self.assertIn("event_occurrences_unknown", [d["code"] for d in result["diagnostics"]])

    def test_unknown_alias_palette_and_empty_glyph_do_not_pass(self):
        ctx = context();ctx.occurrences["text"][0]["catalog_ids"].append("alias")
        result = validate_event_edit({"id": "text"}, encoded("II"), ctx)
        self.assertEqual(result["diagnostics"][0]["code"], "event_occurrence_unknown")
        result = validate_event_edit({"id": "text"}, struct.pack("<HHH", 0x4079, 73, 0), context())
        self.assertEqual(result["diagnostics"][0]["code"], "event_alternate_palette")
        ctx = context();ctx.bounds[ord("a")] = None
        result = validate_event_edit({"id": "text"}, encoded("a"), ctx)
        self.assertIn("event_empty_glyph", [d["code"] for d in result["diagnostics"]])

    def test_vertical_and_new_pages_are_bounded_by_source(self):
        result = validate_event_edit({"id": "text"}, encoded("I\nI"), context())
        self.assertIn("event_pixel_overflow", [d["code"] for d in result["diagnostics"]])
        result = validate_event_edit({"id": "text"}, encoded("I\n\n\nI"), context())
        self.assertIn("event_page_overflow", [d["code"] for d in result["diagnostics"]])


if __name__ == "__main__":
    unittest.main()
