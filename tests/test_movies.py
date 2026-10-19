import sys
from pathlib import Path
import struct
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from khcom.movies import parse_movie
from khcom.errors import KhcomError


def fixture():
    header = struct.pack('<IIfIIIII', 8, 8, 15.0, 1, 0, 0, 0, 0)
    return header + struct.pack('<I', 4) + bytes(4) + struct.pack('<IIHH', 4, 4, 4, 4) + b'abcd' + b'opaque'


class MovieTests(unittest.TestCase):
    def test_packet_framing_retains_opaque_tail_without_decoding_claim(self):
        result = parse_movie(fixture())
        self.assertEqual(result['frames'], 1)
        self.assertEqual(result['video']['blocks'][0]['span'], [52, 56])
        self.assertEqual(result['video']['decode_buffer_maximum'], 4)
        self.assertEqual(result['opaque_tail']['span'], [56, 62])
        self.assertFalse(result['opaque_tail']['reusable'])
        self.assertIsNone(result['audio'])

    def test_truncation_table_counts_and_unknown_types_fail_closed(self):
        cases = [fixture()[:12], fixture()[:50]]
        bad_count = bytearray(fixture());struct.pack_into('<I',bad_count,12,3);cases.append(bad_count)
        bad_type = bytearray(fixture());bad_type[36]=3;cases.append(bad_type)
        bad_size = bytearray(fixture());struct.pack_into('<H',bad_size,50,8);cases.append(bad_size)
        bad_max = bytearray(fixture());struct.pack_into('<H',bad_max,48,2);cases.append(bad_max)
        for value in cases:
            with self.subTest(value=bytes(value[:16])):
                with self.assertRaises(KhcomError):
                    parse_movie(bytes(value))

    def test_nonfinite_frame_rate_and_invalid_dimensions_rejected(self):
        for fps in (float('nan'), float('inf'), 0.0):
            value=bytearray(fixture());struct.pack_into('<f',value,8,fps)
            with self.assertRaises(KhcomError):parse_movie(bytes(value))
        value=bytearray(fixture());struct.pack_into('<I',value,0,289)
        with self.assertRaises(KhcomError):parse_movie(bytes(value))


if __name__ == '__main__':unittest.main()
