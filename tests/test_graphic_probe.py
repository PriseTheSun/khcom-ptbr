"""Authored sprites exercise fixed allocation, sharing and composition."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.graphic_probe import replace_fixed_tiles
from khcom.upstream import load_assetgen


class FixedGraphicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = load_assetgen().sprite_sheet

    def example(self, *, shared=False, gap=False):
        s = self.sheet
        p = s.piece_from_yaml(["8x8", 0, 0])
        second = {**p, "hflip": 1}
        layout = {"cell": [16 if gap else 8, 8], "anchor": [0, 0], "columns": 2, "frames": [[p], [second]]}
        frames = [[s.oam_from_piece(p, 0)], [s.oam_from_piece(second, 0 if shared else 1)]]
        anims = [{"fields": {"originX": 1, "originY": 2}, "frames": [[0, 3], [1, 5]]}]
        tiles = bytes([0x21] * 32) + (b"" if shared else bytes([0x43] * 32))
        raw = s.record_bytes(frames, anims) + tiles
        _, layers = s.decode(frames, tiles, layout)
        return raw, layout, layers

    def test_rewrite_preserves_frame_animation_flips_and_allocation(self):
        raw, layout, layers = self.example()
        layers[0][0] = 7
        layers[0][8] = 9  # rendered left edge of flipped second tile
        result, report = replace_fixed_tiles(raw, layout, 1, layers, self.sheet)
        self.assertEqual(result[:-64], raw[:-64])
        self.assertEqual(result[-64] & 15, 7)
        self.assertEqual(result[-32 + 3] >> 4, 9)
        self.assertEqual(report["tiles_changed"], 2)
        self.assertTrue(report["all_layers_redecoded_exactly"])

    def test_shared_tile_conflict_fails_instead_of_overwriting_other_frame(self):
        raw, layout, layers = self.example(shared=True)
        layers[0][0] = 7
        with self.assertRaises(KhcomError) as error:
            replace_fixed_tiles(raw, layout, 1, layers, self.sheet)
        self.assertEqual(error.exception.code, "graphic_shared_conflict")
        layers[0][15] = 7  # mirrored occurrence requests the same stored nibble
        result, report = replace_fixed_tiles(raw, layout, 1, layers, self.sheet)
        self.assertEqual(len(result), len(raw))
        self.assertEqual(report["tiles_changed"], 1)

    def test_pixels_outside_pieces_are_not_silently_discarded(self):
        raw, layout, layers = self.example(gap=True)
        layers[0][8] = 1
        with self.assertRaises(KhcomError) as error:
            replace_fixed_tiles(raw, layout, 1, layers, self.sheet)
        self.assertEqual(error.exception.code, "graphic_composition")

    def test_wrong_palette_bank_and_layer_size_fail(self):
        raw, layout, layers = self.example()
        layers[0][0] = 17
        with self.assertRaises(KhcomError) as error:
            replace_fixed_tiles(raw, layout, 1, layers, self.sheet)
        self.assertEqual(error.exception.code, "graphic_palette")
        with self.assertRaises(KhcomError) as error:
            replace_fixed_tiles(raw, layout, 1, [layers[0][:-1]], self.sheet)
        self.assertEqual(error.exception.code, "graphic_geometry")


if __name__ == "__main__":
    unittest.main()
