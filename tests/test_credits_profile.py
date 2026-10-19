"""Profile boundaries using authored cells, never original game bitmaps."""

import copy
from pathlib import Path
import sys
import unittest
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.credits_font import REQUIRED, generate_accent
from khcom.credits_profile import decode_line, encode_line, export_table
from khcom.errors import KhcomError


class CreditsProfileTests(unittest.TestCase):
    def error(self, code, callback):
        with self.assertRaises(KhcomError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_all_accents_use_big_endian_profile_codes_and_roundtrip(self):
        expected = bytes.fromhex(
            "82A0 82A1 82A2 82A3 82A4 82A5 82A6 82A7 82A8 82A9 82AA 82AB "
            "82AC 82AD 82AE 82AF 82B0 82B1 82B2 82B3 82B4 82B5 82B6 82B7 00")
        self.assertEqual(encode_line(REQUIRED), expected)
        self.assertEqual(decode_line(expected), REQUIRED)
        # A profile byte pair must not silently return its original SJIS glyph.
        self.assertNotEqual(decode_line(b"\x82\xa0\0"), "あ")
        self.error("credits_profile_code", lambda: decode_line(b"\xa0\x82\0"))
        self.error("credits_profile_character", lambda: encode_line("あ"))

    def test_original_punctuation_ascii_and_commands_keep_bytes(self):
        value = "#1@=Nome ”Exemplo” ~＠1988"
        expected = b"#1@=Nome \x81\x68Exemplo\x81\x68 ~\x81\x971988\0"
        self.assertEqual(encode_line(value), expected)
        self.assertEqual(decode_line(expected), value)
        all_ascii = "".join(chr(code) for code in range(32, 127))
        self.assertEqual(encode_line(all_ascii), bytes(range(32, 127)) + b"\0")
        self.assertEqual(decode_line(b"\0"), "")

    def test_invalid_unicode_and_termination_never_truncate(self):
        self.error("credits_profile_nfc", lambda: encode_line(unicodedata.normalize("NFD", "ã")))
        for value in ("A\0B", "A\nB", "A\u200bB", "é🙂", "\t"):
            self.error("credits_profile_character", lambda: encode_line(value))
        for value in (b"", b"A", b"A\0B\0", b"A\0\0"):
            self.error("credits_profile_line", lambda: decode_line(value))
        for value in (b"\x82\0", b"\x01\0", b"\x82\xb8\0"):
            self.error("credits_profile_code", lambda: decode_line(value))

    def test_resource_limits_apply_after_multibyte_expansion(self):
        self.assertEqual(len(encode_line("á" * 65535)), 131071)
        self.error("credits_profile_text", lambda: encode_line("á" * 65536))
        self.error("credits_profile_text", lambda: encode_line("A" * 131072))
        self.error("credits_profile_line", lambda: decode_line(b"A" * 131072 + b"\0"))

    def test_exported_table_matches_the_profile_without_duplicate_keys(self):
        entries = [line.split("=", 1) for line in export_table().splitlines()
                   if line and not line.startswith(";")]
        self.assertEqual(len(entries), len(dict(entries)))
        self.assertEqual(dict(entries)["00"], "{END}")
        for payload, character in entries:
            if payload != "00":
                self.assertEqual(encode_line(character)[:-1].hex().upper(), payload)
        self.assertEqual(len(entries), 122)

    @staticmethod
    def base(height):
        rows = [[0] * 8 for _ in range(height)]
        # An authored rectangular body and one shadow column, not game art.
        for y in range(2 if height == 8 else 6, 7 if height == 8 else 12):
            rows[y][1:4] = [1, 1, 2]
        return rows

    def test_tall_tilde_has_two_slopes_preserves_base_and_is_immutable(self):
        original = self.base(16)
        before = copy.deepcopy(original)
        result = generate_accent("ã", original, 4)
        self.assertEqual(original, before)
        rows = result["rows"]
        self.assertEqual([i for i, pixel in enumerate(rows[3]) if pixel == 1], [1, 3])
        self.assertEqual([i for i, pixel in enumerate(rows[4]) if pixel == 1], [0, 2])
        self.assertEqual(rows[6:], [bytes(row) for row in original[6:]])
        self.assertEqual(result["advance"], 5)

    def test_compact_tilde_and_cedilla_stay_inside_cell_and_advance(self):
        original = self.base(8)
        before = copy.deepcopy(original)
        tilde = generate_accent("õ", original, 4)
        self.assertEqual(tilde["advance"], 5)
        self.assertEqual(tilde["rows"][2:], [bytes(row) for row in original[2:]])
        cedilla = generate_accent("ç", original, 4)
        self.assertEqual((cedilla["rows"][6][2], cedilla["rows"][7][1]), (1, 1))
        for result in (tilde, cedilla):
            self.assertEqual(len(result["rows"]), 8)
            self.assertFalse(any(pixel for row in result["rows"] for pixel in row[result["advance"]:]))
            self.assertFalse(result["metadata"]["typography_approved"])
        self.assertEqual(original, before)

    def test_recipe_rejects_bad_cells_and_overlap_instead_of_overwriting(self):
        for character, rows, advance in (
                ("a", self.base(8), 4), ("a\u0301", self.base(8), 4),
                ("á", [[0] * 8] * 8, 4), ("á", self.base(8), True),
                ("á", None, 4), ("á", [[4] * 8] * 8, 8),
                ("á", self.base(8), 3), ("á", [[0] * 7] * 8, 4)):
            self.error("credits_recipe", lambda: generate_accent(character, rows, advance))
        occupied = self.base(16)
        occupied[3][3] = 1
        self.error("credits_recipe", lambda: generate_accent("á", occupied, 4))


if __name__ == "__main__":
    unittest.main()
