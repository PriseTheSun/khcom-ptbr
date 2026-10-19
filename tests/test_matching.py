import sys
from pathlib import Path
import struct
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from khcom.errors import KhcomError
from khcom.matching import parse_sections, branch_displacement
from khcom.matching_assets import audio_payload_at
from khcom.relocation_probe import validate_cartridge_size


class MatchingTests(unittest.TestCase):
    def test_gnu_210_wrapped_and_empty_input_sections(self):
        records = parse_sections(''' .text          0x08000000       0xc0 build/us/asm/header.o
 .ewram_common.31
                0x0203d9ac        0x4 build/us/src/work.o
 .rodata        0x080000c0        0x0 build/us/asm/header.o
''')
        self.assertEqual([(r['section'], r['address'], r['size']) for r in records],
                         [('.text', 0x08000000, 192), ('.ewram_common.31', 0x0203d9ac, 4), ('.rodata', 0x080000c0, 0)])

    def test_ambiguous_or_unrecognized_map_rejected(self):
        for text in ('not a linker map', ' .text 0x08000000 0x4 a.o\n .text 0x08000004 0x4 a.o'):
            with self.assertRaises(KhcomError):
                parse_sections(text)

    def test_growth_beyond_gba_cartridge_is_rejected(self):
        validate_cartridge_size(32 * 1024 * 1024)
        for size in (32 * 1024 * 1024 + 1, 0, -1, True):
            with self.assertRaises(KhcomError) as error:
                validate_cartridge_size(size)
            self.assertEqual(error.exception.code, 'relocation_cartridge_capacity')

    def test_armv4t_call_addends_and_rejected_instruction_kinds(self):
        self.assertEqual(branch_displacement(struct.pack('<HH', 0xf7ff, 0xfffe), 10), -4)
        self.assertEqual(branch_displacement(struct.pack('<HH', 0xf000, 0xf801), 10), 2)
        self.assertEqual(branch_displacement(struct.pack('<I', 0xebfffffe), 1), -8)
        self.assertEqual(branch_displacement(struct.pack('<I', 0xea000001), 1), 4)
        for instruction, kind in ((b'\0' * 4, 10), (struct.pack('<HH', 0xf000, 0xe800), 10), (b'\0' * 4, 1), (b'\0', 1)):
            with self.assertRaises(KhcomError):
                branch_displacement(instruction, kind)

    def test_audio_words_must_be_inside_framed_payload(self):
        # 3 words -> 12 byte block, followed by a separate 8 byte block.
        data = struct.pack('<I', 0x03000053) + bytes(8) + struct.pack('<I', 0x02000053) + bytes(4)
        self.assertEqual(audio_payload_at(data, 4)['block_index'], 0)
        self.assertEqual(audio_payload_at(data, 16)['block_index'], 1)
        self.assertIsNone(audio_payload_at(data, 0))
        self.assertIsNone(audio_payload_at(data, 10))
        with self.assertRaises(KhcomError):
            audio_payload_at(struct.pack('<I', 0x10000053) + bytes(4), 4)


if __name__ == '__main__':
    unittest.main()
