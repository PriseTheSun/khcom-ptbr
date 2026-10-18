#!/usr/bin/env python3
"""Map known text ownership and explicitly unverified pointer candidates."""
import argparse
from collections import defaultdict
import json
import struct
import sys
from pathlib import Path

from khcom.errors import KhcomError
from khcom.rom import read_rom
from khcom.text import extract_catalog, json_bytes, write_private

ROM_BASE = 0x08000000
MAX_CANDIDATES = 100000


def map_regions(data: bytes, catalog: dict) -> dict:
    known = [
        {"start": 0, "end": 4, "kind": "arm_entry_instruction", "provenance": "GBA header; decoded below"},
        {"start": 4, "end": 192, "kind": "cartridge_header", "provenance": "validated supported ROM header"},
    ]
    targets = defaultdict(list)
    for interval in catalog["intervals"]:
        span = interval["span"]
        known.append({"start": span["start"], "end": span["end"],
                      "kind": interval["kind"], "id": interval["id"],
                      "provenance": {"kind": "upstream_manifest_verified_against_rom",
                                     "commit": catalog["upstream"]["commit"]}})
        if interval["kind"] == "text":
            targets[ROM_BASE + span["start"]].append(interval["id"])
    regions, cursor = [], 0
    for region in sorted(known, key=lambda item: item["start"]):
        if region["start"] < cursor or region["end"] > len(data):
            raise KhcomError("map_ownership", "Intervalos conhecidos se sobrepõem ou excedem a ROM.")
        if cursor < region["start"]:
            regions.append({"start": cursor, "end": region["start"], "kind": "unknown", "provenance": None})
        regions.append(region)
        cursor = region["end"]
    if cursor < len(data):
        regions.append({"start": cursor, "end": len(data), "kind": "unknown", "provenance": None})
    word = struct.unpack_from("<I", data)[0]
    entry = {"word": f"0x{word:08X}", "target": None, "status": "unknown"}
    if word >> 24 == 0xEA:
        displacement = word & 0xFFFFFF
        if displacement & 0x800000:
            displacement -= 1 << 24
        entry.update(target=ROM_BASE + 8 + 4 * displacement,
                     status="derived_from_unconditional_ARM_B; target code not disassembled")
    candidates, examined = [], 0
    for index, (value,) in enumerate(struct.iter_unpack("<I", memoryview(data)[:len(data) // 4 * 4])):
        examined = (index + 1) * 4
        if value in targets:
            candidates.append({"offset": index * 4, "value": f"0x{value:08X}",
                               "target_ids": targets[value], "status": "candidate_not_confirmed_reference"})
            if len(candidates) >= MAX_CANDIDATES:
                break
    unknown = sum(r["end"] - r["start"] for r in regions if r["kind"] == "unknown")
    return {"schema_version": 1, "origin": catalog["origin"], "regions": regions,
            "unknown_bytes": unknown, "entry_branch": entry,
            "pointer_scan": {"alignment": 4, "byte_order": "little", "examined_bytes": examined,
                             "complete_for_aligned_exact_words": examined == len(data),
                             "confirmed_references": 0, "candidates": candidates},
            "limitations": ["Aligned equal words are candidates, not confirmed code/data references.",
                            "Unaligned, computed and indirect references have not been inventoried.",
                            "Unknown regions may contain code, graphics, audio, video or unused bytes; they are not free space.",
                            "REA generic ARM:LE:32:v7 route is not a validated GBA ARMv4T/Thumb loader."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True)
    parser.add_argument("--member")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fetch-upstream", action="store_true")
    args = parser.parse_args()
    try:
        rom = read_rom(args.rom, member=args.member)
        catalog = extract_catalog(rom.data, fetch=args.fetch_upstream)
        result = map_regions(rom.data, catalog)
        write_private(args.out, json_bytes(result))
        print(json.dumps({"ok": True, "regions": len(result["regions"]),
                          "unknown_bytes": result["unknown_bytes"], "entry": result["entry_branch"],
                          "candidate_words": len(result["pointer_scan"]["candidates"]),
                          "confirmed_references": 0}))
        return 0
    except KhcomError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
