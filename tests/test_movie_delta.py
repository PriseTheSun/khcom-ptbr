import struct
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from khcom.errors import KhcomError
from khcom.movie_delta import (Node,compact_node,decode_delta,decode_keyframe,encode_delta,
                               encode_pixels,parse_delta,replace_delta_pixels,paint_keyframe_selectors)


class DeltaTests(unittest.TestCase):
    def test_fixture_little_endian_words_msb_bits_and_three_streams(self):
        # A single 8×8 fill uses bits 111 then zero padding, one padded u16 color.
        packet=bytes.fromhex('04000400000000e01f000000')
        parsed=parse_delta(packet,8,8)
        self.assertEqual(parsed['nodes'],(Node('fill',(31,)),))
        self.assertEqual(encode_delta(parsed['nodes'],8,8),packet)
        self.assertEqual(decode_delta(parsed,[0]*64),[31]*64)

    def test_arm_pair_carry_is_preserved_and_not_folded_across_columns(self):
        previous=[65535,2]*32
        add=Node('add',(136,1))
        result=decode_delta(parse_delta(encode_delta((add,),8,8),8,8),previous)
        self.assertEqual(result,[0,4]*32)
        split=Node('vertical',children=(add,add))
        self.assertEqual(compact_node(split),split)

    def test_lossless_pixel_edit_reuses_unaffected_motion_leaves(self):
        left=Node('motion',(137,));right=Node('copy')
        original=Node('vertical',children=(left,right))
        previous=list(range(64));parsed=parse_delta(encode_delta((original,),8,8),8,8)
        desired=decode_delta(parsed,previous);desired[7]=300
        nodes,count=replace_delta_pixels(parsed,previous,desired)
        self.assertEqual(count,1)
        self.assertEqual(decode_delta(parse_delta(encode_delta(nodes,8,8),8,8),previous),desired)
        self.assertEqual(nodes[0].children[0],left)

    def test_nested_literals_and_copy_compact_without_changing_pixels(self):
        pixels=[(x*97+y*63)&32767 for y in range(8) for x in range(8)]
        node=encode_pixels(pixels)
        self.assertEqual(decode_delta(parse_delta(encode_delta((node,),8,8),8,8),[0]*64),pixels)
        copy=Node('vertical',children=(Node('copy'),Node('horizontal',children=(Node('copy'),Node('copy')))))
        self.assertEqual(compact_node(copy),Node('copy'))

    def test_keyframe_two_endpoints_selectors_and_constant_interpolation(self):
        packet=struct.pack('<HHI',0x4210,0x4210,0xE4E4E4E4)
        self.assertEqual([x&32767 for x in decode_keyframe(packet,16,16)],[0x4210]*256)
        modified=paint_keyframe_selectors(packet,[0]*256,(4,4,12,12),16,16)
        self.assertEqual(modified[:4],packet[:4])
        self.assertEqual(len(modified),len(packet))

    def test_truncated_streams_unknown_geometry_and_outside_motion_fail_closed(self):
        valid=encode_delta((Node('fill',(31,)),),8,8)
        for bad in (valid[:4],valid[:8],b'\xff\xff'+valid[2:]):
            with self.subTest(bad=bad):
                with self.assertRaises(KhcomError):parse_delta(bad,8,8)
        with self.assertRaises(KhcomError):parse_delta(valid,241,160)
        outside=parse_delta(encode_delta((Node('motion',(0,)),),8,8),8,8)
        with self.assertRaises(KhcomError):decode_delta(outside,[0]*64)
        with self.assertRaises(KhcomError):decode_keyframe(bytes(7),16,16)


if __name__=='__main__':unittest.main()
