"""Independent synthetic renderer tables; contains no original game assets."""

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.credits import CreditTables, parse_line, script_symbols
from khcom.errors import KhcomError


class CreditsTests(unittest.TestCase):
    def setUp(self):
        pages = bytearray(b"\xff" * 512)
        struct.pack_into("<HH", pages, 4, 512, 0)
        self.tables = CreditTables(bytes(pages) + bytes(range(128)) + b"\xff" * 64,
                                   tuple(0x8140 + n for n in range(256)),
                                   (bytes([4] * 128), bytes([3] * 128)))

    def error(self, code, callback):
        with self.assertRaises(KhcomError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_single_byte_remapping_and_big_endian_pair_share_glyph(self):
        result = self.tables.measure(b"A\x81\x81", 0)
        self.assertEqual(result["codes"], [0x8181, 0x8181])
        self.assertEqual(result["glyph_indices"], [65, 65])
        self.assertEqual(result["advance_pixels"], 8)

    def test_missing_pages_cells_and_truncated_codes_fail_explicitly(self):
        self.error("credits_unmapped", lambda: self.tables.measure(b"\x82\x40", 0))
        self.error("credits_unmapped", lambda: self.tables.measure(b"\x81\xc0", 0))
        self.error("credits_truncated", lambda: self.tables.measure(b"\xa1", 0))
        self.error("credits_truncated", lambda: self.tables.measure(b"\x81\x00", 0))
        self.error("credits_nul", lambda: self.tables.measure(b"A\0B", 0))

    def test_font_and_color_prefixes_are_not_drawn_and_font_persists(self):
        line = parse_line(b"#1@=AB\0", 0, self.tables)
        self.assertEqual(line["font_after"], 1)
        self.assertEqual([c["command"] for c in line["commands"]], ["font", "color", "alignment"])
        self.assertEqual(line["runs"][0]["glyph_indices"], [65, 66])
        self.assertEqual(line["runs"][0]["source_span_in_line"], [4, 6])
        self.assertEqual(line["runs"][0]["x"], 117)
        self.assertEqual(line["runs"][0]["color"], "highlight")
        second = parse_line(b"AB\0", line["font_after"], self.tables)
        self.assertEqual(second["runs"][0]["advance_pixels"], 6)
        self.assertEqual(second["runs"][0]["color"], "normal")

    def test_columns_use_generated_spaces_and_separate_color(self):
        line = parse_line(b"~AB~C\0", 0, self.tables)
        left, right = line["runs"]
        self.assertEqual((left["x"], left["right"], right["right"]), (108, 128, 132))
        self.assertEqual(left["generated_suffix_hex"], "202020")
        self.assertEqual(left["glyph_indices"], [65, 66, 32, 32, 32])
        self.assertEqual((left["color"], right["color"]), ("highlight", "normal"))
        self.assertEqual(right["source_span_in_line"], [4, 5])
        self.error("credits_separator", lambda: parse_line(b"~ABC\0", 0, self.tables))

    def test_real_buffer_and_queue_boundaries(self):
        parse_line(b"~" + b"A" * 76 + b"~" + b"B" * 79 + b"\0", 0, self.tables)
        self.error("credits_buffer", lambda: parse_line(b"~" + b"A" * 77 + b"~B\0", 0, self.tables))
        self.error("credits_buffer", lambda: parse_line(b"~A~" + b"B" * 80 + b"\0", 0, self.tables))
        self.assertEqual(len(self.tables.measure(b"A" * 255, 0)["glyph_indices"]), 255)
        self.error("credits_queue", lambda: self.tables.measure(b"A" * 256, 0))

    def test_byte_fit_does_not_imply_visible_width_fit(self):
        visible = parse_line(b"A" * 52 + b"\0", 0, self.tables)["runs"][0]
        clipped = parse_line(b"A" * 53 + b"\0", 0, self.tables)["runs"][0]
        self.assertTrue(visible["within_visible_advance_window"])
        self.assertFalse(clipped["within_visible_advance_window"])
        self.assertTrue(clipped["within_tilemap_advance"])
        for prefix in (b"-", b"+"):
            self.assertFalse(parse_line(prefix + b"AB\0", 0, self.tables)["runs"][0]["within_visible_advance_window"])

    def test_no_draw_commands_and_malformed_controls(self):
        for raw, kind in ((b"!\0", "skip"), (b"*D\0", "logo"), (b"<\0", "section_graphic"), (b"[\0", "section_end")):
            line = parse_line(raw, 0, self.tables)
            self.assertEqual(line["kind"], kind)
            self.assertEqual(line["runs"], [])
        self.error("credits_logo", lambda: parse_line(b"*?\0", 0, self.tables))
        self.error("credits_font", lambda: parse_line(b"#2A\0", 0, self.tables))
        for raw in (b"", b"A", b"A\0B\0"):
            self.error("credits_line", lambda: parse_line(raw, 0, self.tables))

    def test_only_literal_us_script_is_accepted_with_final_sentinel(self):
        source = "#ifdef VERSION_US\nstatic u8* sStaffRollLines[3] = {gStaffRollOne, gStaffRollTwo, NULL,};"
        self.assertEqual(script_symbols(source), ["gStaffRollOne", "gStaffRollTwo", None])
        for changed in (source.replace("[3]", "[4]"), source.replace("gStaffRollOne", "arbitrary()"), source.replace("VERSION_US", "VERSION_JP"), source.replace("gStaffRollOne", "NULL")):
            self.error("credits_script", lambda: script_symbols(changed))


if __name__ == "__main__":
    unittest.main()
