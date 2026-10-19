import struct
import unittest

from tools.khcom.errors import KhcomError
from tools.khcom.event_layout import measure_event_pages, HIGHLIGHT, PLAIN


class EventLayoutTests(unittest.TestCase):
    def layout(self, codes, widths=None, **kwargs):
        return measure_event_pages(struct.pack(f"<{len(codes)}H", *codes), widths or [6] * 256,
                                   origin=kwargs.pop("origin", (16, 108)),
                                   alternate_palette=kwargs.pop("alternate_palette", 5), **kwargs)

    def test_wrap_is_after_glyph_and_end_can_start_empty_page(self):
        widths = [0] * 256
        widths[65], widths[66] = 155, 1
        result = self.layout([65, 66, 65, 66, 65, 66, 0], widths)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual([(g["x"], g["y"]) for g in result["pages"][0]["glyphs"]],
                         [(16, 108), (171, 108), (16, 120), (171, 120), (16, 132), (171, 132)])
        self.assertEqual(result["pages"][0]["next_code_unit"], 6)
        self.assertEqual(result["pages"][1]["glyph_count"], 0)
        self.assertIsNone(result["pages"][1]["next_code_unit"])

    def test_newline_no_slot_palette_resets_and_space_has_no_ink(self):
        bounds = [[1, 2, 5, 10] for _ in range(256)]
        result = self.layout([HIGHLIGHT, 65, 10, 10, 10, 32, 66, 0], glyph_bounds=bounds)
        first, second = result["pages"]
        self.assertEqual(first["glyph_count"], 1)
        self.assertEqual(first["glyphs"][0]["palette"], 5)
        self.assertEqual(first["glyphs"][0]["ink_bounds"], [17, 110, 21, 118])
        self.assertEqual(second["glyphs"][0]["kind"], "space")
        self.assertIsNone(second["glyphs"][0]["ink_bounds"])
        self.assertEqual(second["glyphs"][1]["palette"], 0)

    def test_control_order_is_the_actual_two_if_sequence(self):
        result = self.layout([HIGHLIGHT, PLAIN, 65, 0])
        self.assertEqual(result["pages"][0]["glyphs"][0]["palette"], 0)
        for codes, code in [([PLAIN, HIGHLIGHT, 65, 0], "event_palette_sequence"),
                            ([HIGHLIGHT, HIGHLIGHT, 65, 0], "event_palette_sequence"),
                            ([65, PLAIN, 0], "terminal_palette_control"),
                            ([HIGHLIGHT, PLAIN, 0], "terminal_palette_control")]:
            with self.subTest(codes=codes), self.assertRaises(KhcomError) as caught:
                self.layout(codes)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(KhcomError) as caught:
            self.layout([HIGHLIGHT, 65, 0], alternate_palette=None)
        self.assertEqual(caught.exception.code, "event_alternate_palette")

    def test_icon_mapping_and_undefined_fallback(self):
        result = self.layout([0x2191, 0xE000, 0])
        self.assertEqual([g["glyph_index"] for g in result["pages"][0]["glyphs"]], [10, 25])
        with self.assertRaises(KhcomError) as caught:
            self.layout([0x1234, 0])
        self.assertEqual(caught.exception.code, "event_unmapped_glyph")

    def test_capacity_counts_spaces_and_newline_writes_current_slot(self):
        widths = [0] * 256
        self.assertEqual(self.layout([32] * 128 + [0], widths)["total_glyphs"], 128)
        for suffix in ([32, 0], [10, 0]):
            with self.assertRaises(KhcomError) as caught:
                self.layout([32] * 128 + suffix, widths)
            self.assertEqual(caught.exception.code, "event_glyph_capacity")

    def test_format_guards_never_treat_nul_or_negative_advance_as_text(self):
        for codes in ([65], [0, 65, 0]):
            with self.assertRaises(KhcomError):
                self.layout(codes)
        for widths in ([1] * 255, [65535] * 256, [True] * 256):
            with self.assertRaises(KhcomError):
                self.layout([65, 0], widths)
        for bounds in ([None] * 255, [[0, 0, 17, 8]] * 256, [[0, 1, 0, 4]] * 256):
            with self.assertRaises(KhcomError):
                self.layout([65, 0], glyph_bounds=bounds)


if __name__ == "__main__":
    unittest.main()
