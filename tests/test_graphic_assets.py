"""Lossless resource boundaries, with authored pixels and metadata."""
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.graphic_assets import atlas_tiles, decode_graphic, tile_atlas
from khcom.text import ROM_BASE
from khcom.upstream import load_assetgen


class GraphicAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = load_assetgen()

    def manifest(self, entries):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "own.yaml"
        path.write_text(yaml.safe_dump({"group": "own", "types": {}, "objects": {}, "entries": entries}))
        return self.owner.Manifest(path)

    def resource(self, kind, raw, **kwargs):
        e = {"name": "own", "format": kind, "us": {"address": ROM_BASE, "size": len(raw)}, **kwargs}
        m = self.manifest([e])
        return decode_graphic(raw, m, e, self.owner, {"own": m})

    def test_tile_nibbles_and_two_dimensional_order(self):
        raw = bytes([0x21] * 32 + [0x43] * 32 + [0x65] * 32 + [0x87] * 32)
        png = tile_atlas(raw, 4, 2, self.owner.sprite_sheet, b"")
        w, h, pixels = self.owner.sprite_sheet.read_png(png)
        self.assertEqual((w, h), (16, 16))
        self.assertEqual(pixels[:16], bytes([1, 2] * 4 + [3, 4] * 4))
        self.assertEqual(pixels[8 * 16:9 * 16], bytes([5, 6] * 4 + [7, 8] * 4))
        self.assertEqual(atlas_tiles(png, 4, self.owner.sprite_sheet), raw)

    def test_8bit_tiles_preserve_high_palette_indices(self):
        raw = bytes(range(256))
        png = tile_atlas(raw, 8, 2, self.owner.sprite_sheet, b"")
        w, h, pixels = self.owner.sprite_sheet.read_png(png)
        self.assertEqual(pixels[:16], bytes(list(range(8)) + list(range(64, 72))))
        self.assertEqual(pixels[8 * 16:8 * 16 + 8], bytes(range(128, 136)))
        self.assertEqual(atlas_tiles(png, 8, self.owner.sprite_sheet), raw)

    def test_palette_and_map_keep_all_16_bits_without_screen_mode_guess(self):
        raw = struct.pack("<4H", 0xFFFF, 0x8000, 0x0401, 0xF802)
        for kind in ("palette", "tilemap"):
            report, files = self.resource(kind, raw)
            self.assertEqual(json.loads(files["words.json"])["words_u16"], [0xFFFF, 0x8000, 0x0401, 0xF802])
            self.assertTrue(report["roundtrip_equal"])
            self.assertFalse(report["screen_composition_verified"])
        report, files = self.resource("palette", raw)
        self.assertEqual(json.loads(files["palette-preview.json"])["rgb"][1], [0, 0, 0])

    def test_compressed_blocks_are_retained_without_false_decode_claim(self):
        e = {"name": "own", "format": "tiles4", "us": {"address": ROM_BASE, "size": 4, "compress": "unimplemented"}}
        m = self.manifest([e])
        report, files = decode_graphic(b"ours", m, e, self.owner, {"own": m})
        self.assertFalse(report["roundtrip_equal"])
        self.assertEqual(files, {"original.bin": b"ours"})

    def test_raw_palette_is_interpreted_only_from_explicit_manifest_role(self):
        e = {"name": "raw_pal", "format": "raw", "us": {"address": ROM_BASE, "size": 4}}
        m = self.manifest([e]); raw = b"\xff\xff\x00\x80"
        with self.assertRaises(KhcomError):
            decode_graphic(raw, m, e, self.owner, {"raw_pal": m})
        report, files = decode_graphic(raw, m, e, self.owner, {"raw_pal": m}, frozenset({"raw_pal"}))
        self.assertEqual(report["format"], "raw")
        self.assertEqual(report["interpreted_as"], "palette")
        self.assertEqual(json.loads(files["words.json"])["words_u16"], [0xFFFF, 0x8000])

    def test_invalid_geometry_palette_and_range_fail(self):
        for raw, depth, columns in ((bytes(31), 4, 1), (bytes(32), 4, 2), (bytes(32), 2, 1), (b"", 4, 1)):
            with self.assertRaises(KhcomError):
                tile_atlas(raw, depth, columns, self.owner.sprite_sheet, b"")
        with self.assertRaises(KhcomError):
            self.resource("tiles4", bytes(32), palette="missing")
        with self.assertRaises(KhcomError):
            self.resource("tilemap", b"odd")

    def test_borrowed_tiles_flip_and_animation_roundtrip(self):
        frames = [[[0, 0x3000, 0]]]
        anim = {"fields": {"originX": 0, "originY": 0}, "frames": [[0, 7]]}
        records = self.owner.sprite_sheet.record_bytes(frames, [anim])
        tiles = bytes(range(32))
        e = {"name": "view", "format": "sprite_sheet", "tiles": "lender", "cell": [8, 8], "anchor": [0, 0], "columns": 1,
             "frames": [{"symbol": "frame", "pieces": [["8x8", 0, 0, {"hflip": True, "vflip": True, "tile": 0}]]}],
             "animations": [{"symbol": "anim", **anim}], "us": {"address": ROM_BASE, "size": len(records)}}
        lender = {"name": "lender", "format": "tiles4", "us": {"address": ROM_BASE + len(records), "size": 32}}
        m = self.manifest([e, lender])
        report, files = decode_graphic(records + tiles, m, e, self.owner, {"view": m, "lender": m})
        self.assertTrue(report["roundtrip_equal"])
        self.assertEqual(report["frames"], frames)
        self.assertEqual(report["animations"], [anim])
        _, _, pixels = self.owner.sprite_sheet.read_png(files["main.png"])
        self.assertEqual(pixels[:8], bytes([1, 15, 1, 14, 1, 13, 1, 12]))
        with self.assertRaises(KhcomError):
            decode_graphic(records + tiles[:-1], m, e, self.owner, {"view": m, "lender": m})

    def test_extra_png_preserves_the_stack_of_multiple_layers(self):
        raw = self.owner.sprite_sheet.record_bytes([[[0, 0, 0], [0, 0, 1], [0, 0, 2]]], [])
        raw += bytes([0x11] * 32 + [0x22] * 32 + [0x33] * 32)
        e = {"name": "layers", "format": "sprite_sheet", "cell": [8, 8], "anchor": [0, 0], "columns": 1,
             "frames": [{"symbol": "frame", "pieces": [["8x8", 0, 0], ["8x8", 0, 0, {"layer": 1}], ["8x8", 0, 0, {"layer": 2}]]}],
             "animations": [], "us": {"address": ROM_BASE, "size": len(raw)}}
        m = self.manifest([e])
        report, files = decode_graphic(raw, m, e, self.owner, {"layers": m})
        self.assertEqual(report["layer_count"], 3)
        self.assertEqual(report["png_layers"][1], {"file": "extra-layers.png", "first_layer": 1, "stacked_layers": 2,
                                                 "width": 8, "height_per_layer": 8, "stacking": "vertical"})
        w, h, pixels = self.owner.sprite_sheet.read_png(files["extra-layers.png"])
        self.assertEqual((w, h), (8, 16))
        self.assertEqual(pixels, bytes([2] * 64 + [3] * 64))


if __name__ == "__main__":
    unittest.main()
