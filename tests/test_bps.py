"""BPS fixtures below were hand-encoded from the public-domain format grammar.

Their action stream does not use our encoder. Interoperability additionally
runs against the separately built Flips CLI when KHCOM_FLIPS is provided.
"""
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.bps import apply, create, digest
from khcom.errors import KhcomError


def footer(body, source, target):
    body += struct.pack("<II", zlib.crc32(source), zlib.crc32(target))
    return body + struct.pack("<I", zlib.crc32(body))


def recompute_patch_crc(data):
    return data[:-4] + struct.pack("<I", zlib.crc32(data[:-4]))


class BpsTests(unittest.TestCase):
    def test_independent_all_actions_and_signed_offsets(self):
        source = b"ABCDEabcde"
        target = b"ABxyabcabcabcAB"
        # sizes10/15, no metadata; SourceRead2, TargetRead2 xy,
        # SourceCopy3 delta+5, TargetCopy6 delta+4 (overlap),
        # SourceCopy2 delta-8. Varints and commands explicitly encoded.
        body = b"BPS1\x8a\x8f\x80\x84\x85xy\x8a\x8a\x97\x88\x86\x91"
        self.assertEqual(target, apply(source, footer(body, source, target)))

    def test_target_copy_can_seek_backwards(self):
        target = b"xyxyxy"
        # Literal xy, copy2 at0 -> relative2; copy2 delta-2 -> at0.
        body = b"BPS1\x80\x86\x80\x85xy\x87\x80\x87\x85"
        self.assertEqual(target, apply(b"", footer(body, b"", target)))

    def test_deterministic_generation_and_manifest(self):
        source = b"original" * 90
        target = b"original" * 30 + b"a\xc3\xa7\xc3\xa3o" + b"original" * 60
        first, report = create(source, target)
        second, report2 = create(source, target)
        self.assertEqual(first, second)
        self.assertEqual(report, report2)
        self.assertFalse(report["distribution_approved"])
        self.assertEqual(target, apply(source, first, expected_target_sha256=digest(target)))

    def test_empty_identity_extension_and_truncation(self):
        for source, target in ((b"", b""), (b"same", b"same"), (b"a", b"abc"), (b"abc", b"a")):
            with self.subTest(source=source, target=target):
                encoded, _ = create(source, target)
                self.assertEqual(target, apply(source, encoded))

    def test_randomized_roundtrips(self):
        rng = random.Random(1984)
        for _ in range(120):
            source = rng.randbytes(rng.randrange(0, 2048))
            target = bytearray(source)
            for _ in range(12):
                if target:
                    target[rng.randrange(len(target))] = rng.randrange(256)
            if rng.choice((False, True)):
                target.extend(rng.randbytes(50))
            encoded, _ = create(source, bytes(target))
            self.assertEqual(target, apply(source, encoded))

    def test_integrity_layers(self):
        source, target = b"abc", b"axc"
        encoded, _ = create(source, target)
        cases = [("bps_patch_crc", source, encoded[:-1] + bytes([encoded[-1] ^ 1])),
                 ("bps_source_crc", b"wrong", encoded)]
        damaged = bytearray(encoded)
        damaged[-8] ^= 1
        cases.append(("bps_target_crc", source, recompute_patch_crc(damaged)))
        for code, original, payload in cases:
            with self.subTest(code=code), self.assertRaises(KhcomError) as caught:
                apply(original, payload)
            self.assertEqual(code, caught.exception.code)
        with self.assertRaises(KhcomError) as caught:
            apply(source, encoded, expected_target_sha256="0" * 64)
        self.assertEqual("bps_target_digest", caught.exception.code)

    def test_copy_bounds_and_missing_bytes(self):
        fixtures = [
            ("bps_source_bounds", b"BPS1\x81\x82\x80\x84", b"a", b"aa"),
            ("bps_source_bounds", b"BPS1\x81\x81\x80\x82\x83", b"a", b"x"),
            ("bps_copy_bounds", b"BPS1\x80\x81\x80\x83\x80", b"", b"x"),
            ("bps_truncated", b"BPS1\x80\x82\x80\x85x", b"", b"xy"),
            ("bps_target_bounds", b"BPS1\x81\x80\x80\x80", b"a", b""),
            ("bps_target_size", b"BPS1\x80\x81\x80", b"", b"x"),
            ("bps_integer", b"BPS1" + b"\x7f" * 11, b"", b""),
        ]
        for code, body, source, target in fixtures:
            with self.subTest(code=code), self.assertRaises(KhcomError) as caught:
                apply(source, footer(body, source, target))
            self.assertEqual(code, caught.exception.code)

    def test_work_and_metadata_budgets(self):
        with patch("khcom.bps.MAX_ACTIONS", 1), self.assertRaises(KhcomError) as caught:
            create(b"abc", b"aXc")
        self.assertEqual("bps_budget", caught.exception.code)
        with patch("khcom.bps.MAX_LITERAL_RECORDS", 0), self.assertRaises(KhcomError):
            create(b"a", b"b")
        with self.assertRaises(KhcomError):
            create(b"", b"", b"x" * 65537)

    def test_fragmented_recompression_keeps_original_bytes_in_literal_provenance(self):
        source=b'head'+b'00ab11cd22'+b'preserved suffix'
        target=b'head'+b'XXabYYcdZZ'+b'preserved suffix'
        with patch('khcom.bps.MAX_LITERAL_RECORDS',1):
            encoded,report=create(source,target)
        self.assertEqual(apply(source,encoded),target)
        self.assertEqual(len(report['literals']),1)
        literal=report['literals'][0]
        self.assertEqual(literal['target_start'],4)
        self.assertEqual(literal['length'],10)
        self.assertEqual(literal['coalesced_source_ranges'],[
            {'source_start':6,'length':2,'source_sha256':digest(b'ab')},
            {'source_start':10,'length':2,'source_sha256':digest(b'cd')}])
        self.assertFalse(report['distribution_approved'])
        self.assertEqual(literal['provenance'],'unreviewed')

    def test_coalesced_source_provenance_has_bounded_record_count(self):
        with patch('khcom.bps.MAX_ACTIONS',2),self.assertRaises(KhcomError) as caught:
            create(b'00ab11cd22',b'XXabYYcdZZ')
        self.assertEqual(caught.exception.code,'bps_budget')

    @unittest.skipUnless(os.environ.get("KHCOM_FLIPS"), "set KHCOM_FLIPS for independent interoperability")
    def test_flips_independent_encoder_and_decoder(self):
        cli = str(Path(os.environ["KHCOM_FLIPS"]).resolve())
        source = bytes(range(256)) * 20
        target = source[:301] + b"NOVO TEXTO" * 25 + source[201:700] * 3 + source[1300:]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, modified = root / "original.bin", root / "modified.bin"
            original.write_bytes(source)
            modified.write_bytes(target)
            ours, theirs, output = root / "ours.bps", root / "theirs.bps", root / "applied.bin"
            ours.write_bytes(create(source, target)[0])
            subprocess.run([cli, "--apply", str(ours), str(original), str(output)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(target, output.read_bytes())
            subprocess.run([cli, "--create", "--bps", str(original), str(modified), str(theirs)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(target, apply(source, theirs.read_bytes()))


if __name__ == "__main__":
    unittest.main()
