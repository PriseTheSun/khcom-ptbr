"""Admission tests use only an original synthetic header/payload."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.io import write_new
from khcom.rom import identify_bytes, read_manifest, read_rom


def fixture():
    data = bytearray(512)
    data[0xA0:0xAC] = b"OWN FIXTURE "
    data[0xAC:0xB0] = b"TEST"
    data[0xB0:0xB2] = b"00"
    data[0xB2] = 0x96
    data[0xBD] = (-sum(data[0xA0:0xBD]) - 0x19) & 255
    data[192:] = bytes((i % 251 for i in range(320)))
    expected = {"id": "synthetic-only", "game_code": "TEST", "revision": 0,
                "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return bytes(data), expected


def archive_bytes(entries, compression=zipfile.ZIP_STORED):
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w", compression=compression) as archive:
            for name, data in entries:
                archive.writestr(name, data)
    return stream.getvalue()


class RomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data, self.expected = fixture()

    def tearDown(self):
        self.temp.cleanup()

    def read(self, data, name="input.zip", **kwargs):
        path = self.root / name
        path.write_bytes(data)
        before = path.read_bytes()
        try:
            return read_rom(path, expected=self.expected, **kwargs)
        finally:
            self.assertEqual(before, path.read_bytes(), "input must be immutable")

    def rejects(self, code, data, name="input.zip", **kwargs):
        with self.assertRaises(KhcomError) as caught:
            self.read(data, name, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def test_raw_is_identified_by_bytes_under_renamed_path(self):
        result = self.read(self.data, "cópia com espaços.bin")
        self.assertEqual(self.data, result.data)
        self.assertEqual("synthetic-only", result.identity["rom_id"])
        self.assertIsNone(result.member)

    def test_wrong_revision_and_digest_keep_observed_identity(self):
        altered = bytearray(self.data)
        altered[0xBC] = 1
        altered[0xBD] = (-sum(altered[0xA0:0xBD]) - 0x19) & 255
        with self.assertRaises(KhcomError) as caught:
            identify_bytes(bytes(altered), self.expected)
        self.assertEqual(["sha256", "revision"], caught.exception.details["mismatches"])
        self.assertIsNone(caught.exception.details["observed"]["rom_id"])

    def test_wrong_size_and_truncation(self):
        self.rejects("rom_size", self.data[:-1], "short.gba")
        self.rejects("rom_size", self.data + b"x", "long.gba")
        self.rejects("invalid_zip", archive_bytes([("a.gba", self.data)])[:-4])

    def test_stored_and_deflated_zip_are_identical(self):
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method):
                result = self.read(archive_bytes([("pasta/Jogo.GBA", self.data)], method))
                self.assertEqual(self.data, result.data)
                self.assertEqual("pasta/Jogo.GBA", result.member)

    def test_multiple_candidates_require_explicit_selection(self):
        payload = archive_bytes([("a.gba", self.data), ("b.gba", self.data)])
        self.rejects("rom_selection", payload)
        self.assertEqual("b.gba", self.read(payload, member="b.gba").member)
        self.rejects("rom_selection", payload, member="missing.gba")

    def test_no_candidate_and_raw_member_are_rejected(self):
        self.rejects("rom_selection", archive_bytes([("readme.txt", b"owned")]))
        self.rejects("rom_selection", self.data, "raw.gba", member="a.gba")

    def test_traversal_and_absolute_paths(self):
        for name in ("../a.gba", "/a.gba", "C:/a.gba", "a\\b.gba", "a//b.gba", "./a.gba"):
            with self.subTest(name=name):
                self.rejects("unsafe_zip_path", archive_bytes([(name, self.data)]))

    def test_duplicate_names(self):
        self.rejects("duplicate_zip_member", archive_bytes([("a.gba", self.data)] * 2))

    def test_links_and_special_members(self):
        for kind in (stat.S_IFLNK, stat.S_IFIFO):
            entry = zipfile.ZipInfo("a.gba")
            entry.create_system = 3
            entry.external_attr = (kind | 0o600) << 16
            self.rejects("zip_member_type", archive_bytes([(entry, self.data)]))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX only")
    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        path = self.root / "pipe.gba"
        os.mkfifo(path)
        with self.assertRaises(KhcomError) as caught:
            read_rom(path, expected=self.expected)
        self.assertEqual("input_type", caught.exception.code)

    def test_encrypted_and_unsupported_compression(self):
        payload = bytearray(archive_bytes([("a.gba", self.data)]))
        central = payload.index(b"PK\x01\x02")
        struct.pack_into("<H", payload, central + 8, 1)
        self.rejects("encrypted_zip", payload)
        struct.pack_into("<H", payload, central + 8, 0)
        struct.pack_into("<H", payload, central + 10, 99)
        self.rejects("zip_compression", payload)

    def test_crc_is_checked_when_reading(self):
        payload = bytearray(archive_bytes([("a.gba", self.data)]))
        name_len, extra_len = struct.unpack_from("<HH", payload, 26)
        payload[30 + name_len + extra_len + 300] ^= 1
        self.rejects("input_read", payload)

    def test_invalid_utf8_member_is_a_tagged_failure(self):
        payload = bytearray(archive_bytes([("a.gba", self.data)]))
        central = payload.index(b"PK\x01\x02")
        struct.pack_into("<H", payload, central + 8, 0x800)
        payload[central + 46] = 0xFF
        self.rejects("input_read", payload)

    def test_metadata_budgets_precede_zipfile_allocation(self):
        payload = archive_bytes([(f"{i}.txt", b"") for i in range(129)])
        with patch("khcom.rom.zipfile.ZipFile", side_effect=AssertionError("allocated too soon")):
            self.rejects("zip_budget", payload)

    def test_declared_entry_count_is_not_trusted(self):
        payload = bytearray(archive_bytes([("a.gba", self.data), ("b.gba", self.data)]))
        end = payload.rindex(b"PK\x05\x06")
        struct.pack_into("<HH", payload, end + 8, 1, 1)
        self.rejects("invalid_zip", payload)

    def test_expansion_budget_before_decompression(self):
        payload = bytearray(archive_bytes([("a.gba", self.data)]))
        central = payload.index(b"PK\x01\x02")
        struct.pack_into("<I", payload, central + 24, 33 * 1024 * 1024)
        self.rejects("zip_budget", payload)
        payload = bytearray(archive_bytes([(f"{i}.gba", b"") for i in range(5)]))
        pos = 0
        for _ in range(5):
            pos = payload.index(b"PK\x01\x02", pos)
            struct.pack_into("<I", payload, pos + 24, 32 * 1024 * 1024)
            pos += 4
        self.rejects("zip_budget", payload)

    def test_small_rom_member_rejected(self):
        self.rejects("rom_size", archive_bytes([("a.gba", b"short")]))

    def test_manifest_shape_errors_are_tagged(self):
        path = self.root / "manifest.json"
        for field, value in (("revision", True), ("game_code", "bad"), ("id", None),
                             ("size", 0), ("sha256", "not-a-digest")):
            with self.subTest(field=field):
                path.write_text(json.dumps(self.expected | {field: value}), encoding="utf-8")
                with self.assertRaises(KhcomError) as caught:
                    read_manifest(path)
                self.assertEqual("invalid_manifest", caught.exception.code)

    def test_output_publication_is_exclusive(self):
        path = self.root / "nested" / "owned.bin"
        write_new(path, b"first")
        with self.assertRaises(KhcomError):
            write_new(path, b"second")
        self.assertEqual(b"first", path.read_bytes())
        self.assertEqual([path], list(path.parent.iterdir()))


if __name__ == "__main__":
    unittest.main()
