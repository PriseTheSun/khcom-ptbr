"""Synthetic graphics through the actual pinned format owners; no game assets."""

from pathlib import Path
import struct
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.graphics import ROM_BASE, inspect_font, latin_widths, match_metrics, rom_slice
from khcom.upstream import load_assetgen


class GraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = load_assetgen()

    def fixture(self, kind="sprite_sheet"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "font.yaml"
        if kind == "sprite_sheet":
            raw = self.owner.sprite_sheet.record_bytes([[[0, 0, 0]]], []) + bytes(range(32))
            entry = {"name": "font", "format": kind, "cell": [8, 8], "anchor": [0, 0], "columns": 1, "frames": [{"symbol": "frame0", "pieces": [["8x8", 0, 0]]}], "animations": [], "us": {"address": ROM_BASE + 16, "size": len(raw)}}
            table = {"name": "pointers", "record": "PointerTable", "items": ["frame0"], "us": {"address": ROM_BASE + 96}}
            types = {"PointerTable": {"kind": "table", "type": "void*"}}
            tail = struct.pack("<I", ROM_BASE + 16)
            spec = {"id": "synthetic", "symbol": "font", "pointer_table": "pointers"}
        else:
            raw = bytes(range(32))
            entry = {"name": "font", "format": kind, "glyph": [8, 8], "bpp": 2, "columns": 2, "us": {"address": ROM_BASE + 16, "size": len(raw)}}
            table = {"name": "widths", "record": "Widths", "values": [5, 6], "us": {"address": ROM_BASE + 96}}
            types = {"Widths": {"kind": "array", "type": "u8"}}
            tail = b"\x05\x06"
            spec = {"id": "synthetic", "symbol": "font", "widths": "widths"}
        path.write_text(yaml.safe_dump({"group": "synthetic", "types": types, "objects": {}, "entries": [entry, table]}))
        data = b"\xA5" * 16 + raw
        data += b"\xA5" * (96 - len(data)) + tail
        return data, spec, self.owner.Manifest(path)

    def test_sprite_png_rebuild_and_observed_pointer_table(self):
        data, spec, manifest = self.fixture()
        report, png = inspect_font(data, spec, self.owner, manifest)
        self.assertTrue(report["roundtrip_equal"])
        self.assertTrue(report["frame_pointer_table"]["verified"])
        self.assertFalse(report["runtime_verified"])
        self.assertEqual(report["glyph_count"], 1)
        self.assertEqual(report["manifest_resource_address"], "0x08000010")
        self.assertEqual(report["tile_payload_address"], "0x0800001A")
        self.assertEqual(report["tile_payload_size"], 32)
        width, height, pixels = self.owner.sprite_sheet.read_png(png)
        self.assertEqual((width, height), (8, 8))
        self.assertEqual(pixels[:8], bytes([0, 0, 1, 0, 2, 0, 3, 0]))

    def test_sprite_pointer_into_wrong_record_is_rejected(self):
        data, spec, manifest = self.fixture()
        with self.assertRaises(KhcomError) as caught:
            inspect_font(data[:96] + struct.pack("<I", ROM_BASE + 18), spec, self.owner, manifest)
        self.assertEqual(caught.exception.code, "font_pointer_mismatch")

    def test_unsupported_oam_mode_is_not_silently_flattened(self):
        data, spec, manifest = self.fixture()
        changed = bytearray(data)
        changed[19] |= 1  # affine flag in OAM attr0
        with self.assertRaises(KhcomError) as caught:
            inspect_font(bytes(changed), spec, self.owner, manifest)
        self.assertEqual(caught.exception.code, "font_format_mismatch")

    def test_2bpp_glyph_png_rebuild_and_metrics(self):
        data, spec, manifest = self.fixture("glyphs")
        report, png = inspect_font(data, spec, self.owner, manifest)
        self.assertTrue(report["roundtrip_equal"])
        self.assertEqual(report["metrics"]["values"], [5, 6])
        width, height, pixels = self.owner.sprite_sheet.read_png(png)
        self.assertEqual((width, height), (16, 8))
        self.assertEqual(pixels[:8], bytes([0, 0, 0, 0, 0, 0, 0, 1]))

    def test_metrics_mismatch_and_truncated_asset_rejected(self):
        data, spec, manifest = self.fixture("glyphs")
        for changed in (data[:96] + b"\x05\x07", data[:20]):
            with self.assertRaises(KhcomError):
                inspect_font(changed, spec, self.owner, manifest)

    def test_u16_metrics_require_unique_exact_rom_match(self):
        values = list(range(256))
        raw = struct.pack("<256H", *values)
        report = match_metrics(b"test" + raw + b"end", values)
        self.assertEqual(report["address"], "0x08000004")
        self.assertEqual(report["size"], 512)
        for data in (bytes(values), raw + raw):
            with self.assertRaises(KhcomError):
                match_metrics(data, values)

    def test_literal_width_table_rejects_unreviewed_expressions(self):
        numbers = ",".join(str(n) for n in range(256))
        source = "static const GlyphWidthTable sLatinGlyphWidths = {{" + numbers + "}};"
        self.assertEqual(latin_widths(source), list(range(256)))
        with self.assertRaises(KhcomError):
            latin_widths(source.replace("255", "128+127"))

    def test_negative_or_outside_rom_ranges_rejected(self):
        for address, size in ((ROM_BASE - 1, 1), (ROM_BASE, -1), (ROM_BASE + 3, 2)):
            with self.assertRaises(KhcomError):
                rom_slice(b"test", address, size)


if __name__ == "__main__":
    unittest.main()
