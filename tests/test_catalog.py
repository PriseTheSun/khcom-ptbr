"""UTF-8 editorial interchange tests with authored strings only."""

import copy
import csv
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.text import CSV_FIELDS, export_csv, import_csv, read_catalog, write_private


def sample():
    return {"format_version": 1, "origin": {"sha256": "synthetic"}, "items": [
        {"id": "synthetic/first", "source_text": 'Teste "com aspas", ação; café\r\nLinha {END}', "translation": None, "translation_input": None, "status": "untranslated", "tokens": [{"kind": "control", "name": "END"}], "reviewer": None, "evidence_refs": [], "pixel_budget": None},
        {"id": "synthetic/second", "source_text": "Ímpar{END}", "translation": "", "translation_input": "", "status": "draft", "reviewer": None, "evidence_refs": [], "pixel_budget": None},
    ]}


def rows(content):
    return list(csv.DictReader(io.StringIO(content, newline="")))


def csv_of(values):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(values)
    return output.getvalue()


class CatalogTests(unittest.TestCase):
    def test_csv_oversized_or_unclosed_header_is_tagged_failure(self):
        for content in ('"' + 'a' * 131073, '"unterminated'):
            with self.subTest(size=len(content)):
                with self.assertRaises(KhcomError) as caught:
                    import_csv(sample(), content)
                self.assertEqual(caught.exception.code, "csv_parse")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO boundary")
    def test_catalog_fifo_is_rejected_without_waiting_for_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.pipe"
            os.mkfifo(path)
            with self.assertRaises(KhcomError) as caught:
                read_catalog(path)
            self.assertEqual(caught.exception.code, "input_type")

    def test_csv_roundtrip_preserves_quotes_multiline_tokens_and_null_empty(self):
        catalog = sample()
        self.assertEqual(import_csv(catalog, export_csv(catalog)), catalog)

    def test_row_order_does_not_change_identity(self):
        catalog = sample()
        self.assertEqual(import_csv(catalog, csv_of(list(reversed(rows(export_csv(catalog)))))), catalog)

    def test_nfc_is_editorial_only_raw_input_preserved_and_review_invalidated(self):
        catalog = sample()
        catalog["items"][0].update(reviewer="test-reviewer", evidence_refs=["old-test"], status="reviewed")
        edits = rows(export_csv(catalog))
        edits[0]["translation"] = "Ac\u0327a\u0303o {END}"
        edits[0]["has_translation"] = "1"
        result = import_csv(catalog, csv_of(edits))
        item = result["items"][0]
        self.assertEqual(item["translation"], "Ação {END}")
        self.assertEqual(item["translation_input"], "Ac\u0327a\u0303o {END}")
        self.assertEqual(item["source_text"], catalog["items"][0]["source_text"])
        self.assertEqual(item["status"], "draft")
        self.assertIsNone(item["reviewer"])
        self.assertEqual(item["evidence_refs"], [])

    def test_source_metadata_membership_and_identity_tampering_rejected(self):
        catalog = sample()
        original = rows(export_csv(catalog))
        cases = []
        for column, value in [("source_text", "Changed"), ("id", "synthetic/unknown"), ("metadata_json", "{}"), ("has_translation", "maybe")]:
            modified = copy.deepcopy(original)
            modified[0][column] = value
            cases.append(modified)
        cases += [original[:1], original + [original[0]]]
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(KhcomError):
                    import_csv(catalog, csv_of(values))

    def test_unexpected_csv_columns_and_broken_json_rejected(self):
        with self.assertRaises(KhcomError):
            import_csv(sample(), "id,translation\nsynthetic/first,abc\n")
        values = rows(export_csv(sample()))
        values[0]["metadata_json"] = "{broken"
        with self.assertRaises(KhcomError):
            import_csv(sample(), csv_of(values))

    def test_private_output_policy_and_exclusive_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch("khcom.text.PROJECT_ROOT", root):
                with self.assertRaises(KhcomError) as caught:
                    write_private(root / "public.json", b"synthetic")
                self.assertEqual(caught.exception.code, "private_output_required")
                destination = root / "private" / "catalog.json"
                write_private(destination, b"first")
                with self.assertRaises(KhcomError):
                    write_private(destination, b"second")
                self.assertEqual(destination.read_bytes(), b"first")
                outside = root / "outside"
                outside.mkdir()
                (root / "private" / "link").symlink_to(outside, target_is_directory=True)
                with self.assertRaises(KhcomError):
                    write_private(root / "private" / "link" / "catalog.json", b"private")


if __name__ == "__main__":
    unittest.main()
