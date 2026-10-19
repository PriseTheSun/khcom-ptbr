"""Synthetic format-boundary tests; no copyrighted text or ROM fixture."""

import copy
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.text import ROM_BASE, build_dialogue_probe, extract_catalog, export_tables, reinsert_unedited, tokenize
from khcom.upstream import load_textgen
from khcom.validation import validate_translations


class TextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = load_textgen()
        cls.codecs = cls.owner.load_charmap("us")

    def fixture(self, *, source="Teste áé{HIGHLIGHT}í{PLAIN}\nãç{END}", domains=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        encoded = self.codecs["game"].encode(source, "synthetic")
        data = b"\xA5" * 32 + encoded + b"\xA5" * 64
        spec = {"pool": "synthetic", "objects": {"us": {"name": "synthetic.s", "start": ROM_BASE + 32, "end": ROM_BASE + 32 + len(encoded), "encoding": "game", "align": 2, "ctype": "u16"}}, "entries": ["test_string"]}
        path = directory / "synthetic.yaml"
        path.write_text(yaml.safe_dump(spec), encoding="utf-8")
        pools = [self.owner.Pool(path)]
        parser = SimpleNamespace(load_charmap=lambda version: self.codecs, load_pools=lambda: pools, decode_unit=self.owner.decode_unit, TextError=self.owner.TextError)
        return data, parser, spec, directory

    def test_codec_bytes_controls_and_unknown_characters(self):
        codec = self.codecs["game"]
        self.assertEqual(codec.encode("á\n{END}", "test"), b"\xe1\0\x0a\0\0\0")
        self.assertEqual(codec.encode("{HIGHLIGHT}", "test"), b"\x79\x40")
        self.assertEqual(codec.decode(b"\xe1\0\x0a\0\0\0"), "á\n{END}")
        with self.assertRaises(self.owner.TextError):
            codec.encode("🧪", "test")
        with self.assertRaises(self.owner.TextError):
            codec.encode("{NOT_A_CONTROL}", "test")

    def test_experimental_probe_rejects_an_unrecognized_rom(self):
        with self.assertRaises(KhcomError) as caught:
            build_dialogue_probe(b"not a recognized ROM")
        self.assertEqual(caught.exception.code, "upstream_rom_mismatch")

    def test_cp932_uses_variable_length_and_cannot_reuse_latin_codec(self):
        codec = self.codecs["sjis"]
        text = "検証{END}"
        encoded = codec.encode(text, "test")
        self.assertEqual(encoded, "検証".encode("cp932") + b"\0")
        self.assertEqual(codec.decode(encoded), text)
        with self.assertRaises(self.owner.TextError):
            codec.encode("ã", "test")

    def test_inventory_and_unedited_roundtrip_preserve_opaque_bytes(self):
        data, parser, _, _ = self.fixture()
        catalog = extract_catalog(data, parser=parser, check_identity=False)
        item = catalog["items"][0]
        self.assertEqual(item["source_span"]["start"], 32)
        self.assertIsNone(item["pointer_refs"])
        self.assertIsNone(item["pixel_budget"])
        self.assertIsNone(item["font_id"])
        self.assertFalse(catalog["coverage"]["complete_game_coverage"])
        rebuilt, report = reinsert_unedited(data, catalog, parser=parser, check_identity=False)
        self.assertEqual(rebuilt, data)
        self.assertEqual(report["opaque_bytes_preserved_not_interpreted"], 96)
        self.assertEqual(report["target_sha256"], hashlib.sha256(data).hexdigest())

    def test_missing_terminator_is_format_failure(self):
        data, parser, _, _ = self.fixture()
        corrupted = data.replace(b"\0\0", b"\xff\xff")
        with self.assertRaises(KhcomError) as caught:
            extract_catalog(corrupted, parser=parser, check_identity=False)
        self.assertEqual(caught.exception.code, "upstream_format_mismatch")

    def test_overlapping_manifest_ownership_rejected(self):
        data, parser, spec, directory = self.fixture()
        other = copy.deepcopy(spec)
        other["pool"] = "other"
        path = directory / "other.yaml"
        path.write_text(yaml.safe_dump(other), encoding="utf-8")
        pools = parser.load_pools() + [self.owner.Pool(path)]
        parser.load_pools = lambda: pools
        with self.assertRaises(KhcomError) as caught:
            extract_catalog(data, parser=parser, check_identity=False)
        self.assertEqual(caught.exception.code, "text_overlap")

    def test_tampered_origin_or_span_and_missing_items_are_rejected(self):
        data, parser, _, _ = self.fixture()
        pristine = extract_catalog(data, parser=parser, check_identity=False)
        for field in ("source_span", "origin", "membership"):
            with self.subTest(field=field):
                catalog = copy.deepcopy(pristine)
                if field == "source_span":
                    catalog["items"][0]["source_span"]["start"] += 2
                elif field == "origin":
                    catalog["origin"]["sha256"] = "0" * 64
                else:
                    catalog["items"] = []
                with self.assertRaises(KhcomError):
                    reinsert_unedited(data, catalog, parser=parser, check_identity=False)

    def test_edited_text_is_not_allowed_without_glyph_and_layout_evidence(self):
        data, parser, _, _ = self.fixture()
        catalog = extract_catalog(data, parser=parser, check_identity=False)
        catalog["items"][0]["translation"] = "Outro texto{END}"
        with self.assertRaises(KhcomError) as caught:
            reinsert_unedited(data, catalog, parser=parser, check_identity=False)
        self.assertEqual(caught.exception.code, "localization_unverified")

    def test_unknown_code_remains_opaque(self):
        data, parser, _, _ = self.fixture(source="A{0xFFFF}{END}")
        catalog = extract_catalog(data, parser=parser, check_identity=False)
        self.assertEqual(catalog["items"][0]["opaque_codes"], ["0xFFFF"])
        rebuilt, _ = reinsert_unedited(data, catalog, parser=parser, check_identity=False)
        self.assertEqual(rebuilt, data)

    def test_tbl_keys_are_file_bytes_and_no_fictitious_small_font(self):
        tables = export_tables(self.owner)
        self.assertEqual(set(tables), {"game-us.tbl", "sjis-us.tbl", "jp-us.tbl"})
        self.assertIn("0A00={NL}\n", tables["game-us.tbl"])
        self.assertIn("E100=á\n", tables["game-us.tbl"])
        self.assertIn("7940={HIGHLIGHT}\n", tables["game-us.tbl"])
        self.assertIn("6E6E={NL}\n", tables["jp-us.tbl"])
        keys = [line.split("=", 1)[0] for line in tables["game-us.tbl"].splitlines() if not line.startswith(";")]
        self.assertEqual(len(keys), len(set(keys)))

    def test_candidate_reports_overflow_controls_and_unmapped_character_by_id(self):
        data, parser, _, _ = self.fixture(source="Teste{END}")
        original = extract_catalog(data, parser=parser, check_identity=False)
        for text, wanted in (("Mais longo que a reserva{END}", "byte_overflow"), ("Teste", "controls_changed"), ("🧪{END}", "encoding_error"), ("{END}X", "terminator_position")):
            candidate = copy.deepcopy(original); candidate["items"][0]["translation"] = text
            report = validate_translations(data, candidate, parser=parser, check_identity=False)
            self.assertEqual(report["items"][0]["id"], original["items"][0]["id"])
            self.assertIn(wanted, report["diagnostic_counts"])
            self.assertEqual(report["blocked_items"], 1)
            self.assertFalse(report["release_approved"])

    def test_fitting_candidate_does_not_turn_unknown_layout_into_approval(self):
        data, parser, _, _ = self.fixture(source="Teste{END}")
        candidate = extract_catalog(data, parser=parser, check_identity=False)
        candidate["items"][0].update(translation="Olá{END}", status="approved", reviewer="claimed")
        report = validate_translations(data, candidate, parser=parser, check_identity=False)
        self.assertEqual(report["items"][0]["candidate_bytes"], 8)
        self.assertEqual(report["diagnostic_counts"], {"references_unknown": 1, "layout_unknown": 1})
        self.assertFalse(report["complete_game_coverage"])

    def test_candidate_cannot_override_source_owned_aliases_or_bounds(self):
        data, parser, _, _ = self.fixture(source="Teste{END}")
        original = extract_catalog(data, parser=parser, check_identity=False)
        for field, value in (("aliases", ["invented"]), ("byte_budget", 10000), ("pointer_refs", []), ("font_id", "invented")):
            candidate = copy.deepcopy(original); candidate["items"][0][field] = value
            with self.assertRaises(KhcomError) as caught:
                validate_translations(data, candidate, parser=parser, check_identity=False)
            self.assertEqual(caught.exception.code, "catalog_provenance")

    def test_no_edit_is_not_claimed_as_translation_and_nfc_is_explicit(self):
        data, parser, _, _ = self.fixture(source="Teste{END}")
        candidate = extract_catalog(data, parser=parser, check_identity=False)
        report = validate_translations(data, candidate, parser=parser, check_identity=False)
        self.assertEqual(report["changed_items"], 0)
        self.assertEqual(report["items"][0]["status"], "no_edit_to_validate")
        candidate["items"][0]["translation"] = "a\u0301{END}"
        report = validate_translations(data, candidate, parser=parser, check_identity=False)
        self.assertIn("editorial_nfc", report["diagnostic_counts"])

    def test_literal_nul_is_validated_as_encoded_terminator(self):
        data, parser, _, _ = self.fixture(source="Teste{END}")
        candidate = extract_catalog(data, parser=parser, check_identity=False)
        candidate["items"][0]["translation"] = "A\0B{END}"
        report = validate_translations(data, candidate, parser=parser, check_identity=False)
        self.assertIn("invisible_editorial_characters", report["diagnostic_counts"])
        issue = next(d for d in report["items"][0]["diagnostics"] if d["code"] == "controls_changed")
        self.assertEqual(issue["actual"], ["END", "END"])


if __name__ == "__main__":
    unittest.main()
