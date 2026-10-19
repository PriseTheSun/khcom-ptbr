"""Source-owned US event occurrences, bound to matching linker facts.

The script, position inheritance and palette selection belong here. The layout
owner measures bytes; neither module turns a ledger into runtime approval.
"""
from collections import Counter, defaultdict
import bisect
from pathlib import Path
import struct

from .errors import KhcomError
from .event_layout import measure_event_pages
from .upstream import COMMIT, sha256

BASE = 0x08000000
SOURCE_FILES = ("src/msg/msg.c", "src/evt/event_message.c", "src/evt/event_index_data.c",
                "include/evt/msg_types.h")


def event_occurrences(data: bytes, catalog: dict, facts: dict) -> dict:
    """Consume fresh matching facts; never select a symbol by first-name match."""
    digest = sha256(data)
    if (facts.get("schema") != "khcom-matching-facts-v1" or facts.get("rom", {}).get("sha256") != digest
            or not facts.get("baseline_byte_identical") or not facts.get("elf_rom_agreement")
            or catalog.get("origin", {}).get("sha256") != digest):
        raise KhcomError("event_identity", "Catálogo e fatos matching precisam corresponder à origem.")
    by_name, by_address, refs = defaultdict(list), defaultdict(list), defaultdict(list)
    for symbol in facts["symbols"]:
        if symbol["type"] == "STT_OBJECT":
            by_name[symbol["name"]].append(symbol)
            by_address[symbol["address"]].append(symbol)
    for ref in facts["relocations"]:
        refs[ref["source_offset"]].append(ref)

    def symbol(name=None, address=None):
        found = by_name[name] if name is not None else by_address[address]
        if len(found) != 1:
            raise KhcomError("event_symbol", "Objeto necessário ausente ou ambíguo.", name=name, address=address)
        result = found[0]
        if not BASE <= result["address"] <= result["address"] + result["size"] <= BASE + len(data):
            raise KhcomError("event_range", "Objeto fora dos bytes da ROM.", symbol=result["name"])
        return result

    def edge(offset, target):
        found = refs[offset]
        if (len(found) != 1 or found[0]["kind"] != "R_ARM_ABS32"
                or found[0]["target_address"] != target
                or struct.unpack_from("<I", data, offset)[0] != target):
            raise KhcomError("event_reference", "Ligação de evento sem relocação ABS32 exata.", source_offset=offset)
        return {key: found[0][key] for key in ("source_offset", "target_address", "symbol", "addend", "owner")}

    table = symbol(name="gEventSequenceDefs")
    if not 4 <= table["size"] <= 256 * 4 or table["size"] % 4:
        raise KhcomError("event_index", "Índice incompatível com eventId u8 do consumidor.")
    axes = []
    for name in ("gMsgwinTextX", "gMsgwinTextY"):
        axis = symbol(name=name)
        if axis["size"] != 16:
            raise KhcomError("event_positions", "Tabela de quatro posições s32 não reconhecida.")
        axes.append(struct.unpack_from("<4i", data, axis["address"] - BASE))
    by_text = defaultdict(list)
    for item in catalog["items"]:
        by_text[BASE + item["source_span"]["start"]].append(item)
    rows, expected_refs = [], defaultdict(set)
    for event_id in range(table["size"] // 4):
        table_offset = table["address"] - BASE + event_id * 4
        definition_address = struct.unpack_from("<I", data, table_offset)[0]
        definition = symbol(address=definition_address)
        if definition["size"] != 48:
            raise KhcomError("event_definition", "EventSequenceDef não tem a estrutura US de 48 bytes.")
        definition_ref = edge(table_offset, definition_address)
        script_pointer = definition_address - BASE + 12
        script_address = struct.unpack_from("<I", data, script_pointer)[0]
        script = symbol(address=script_address)
        if not script["size"] or script["size"] % 24:
            raise KhcomError("event_script", "Script exige registros completos MessageScriptEntry de 24 bytes.")
        script_ref = edge(script_pointer, script_address)
        position = None
        for entry_index in range(script["size"] // 24):
            offset = script_address - BASE + entry_index * 24
            portrait, expression, specified_position = struct.unpack_from("<III", data, offset)
            char_delay, text_address, flags, frame = struct.unpack_from("<B3xIHH", data, offset + 12)
            issues = []
            if specified_position != 4:
                position = specified_position if specified_position < 4 else None
            if position is None:
                issues.append("position_state_unknown")
            if portrait > 62:
                issues.append("portrait_unknown")
            text_ref = edge(offset + 16, text_address)
            matched = by_text[text_address]
            if not matched:
                issues.append("text_outside_catalog")
            elif any(item["codec_id"] != "game" for item in matched):
                issues.append("text_consumer_codec_mismatch")
            origin = None if position is None else [46 if portrait == 62 else axes[0][position] // 256,
                                                   (axes[1][position] - 512) // 256]
            if position is not None and ((axes[0][position] % 256) or (axes[1][position] % 256)):
                issues.append("fractional_origin_unmodeled")
            last = entry_index + 1 == script["size"] // 24
            if bool(flags & 0x8000) != last:
                issues.append("script_end_not_at_symbol_boundary")
            row = {"event_id": event_id, "entry_index": entry_index, "entry_offset": offset,
                   "definition": definition["name"], "script": script["name"],
                   "source_sha256": sha256(data[offset:offset + 24]),
                   "text_address": text_address, "catalog_ids": [item["id"] for item in matched],
                   "portrait": portrait, "expression": expression, "position_index": specified_position,
                   "effective_position": position, "origin": origin,
                   "char_delay": char_delay, "flags": flags, "frame": frame,
                   "alternate_palette": 3 if event_id == 11 else 5 if event_id in (3, 134, 156) else None,
                   "references": {"definition": definition_ref, "script": script_ref, "text": text_ref},
                   "unknowns": issues, "runtime_observed": False}
            rows.append(row)
            for item in matched:
                expected_refs[item["id"]].add(offset + 16)
    text_refs = defaultdict(list)
    # Linker references to any byte of a string remain distinct from script refs.
    grouped_intervals = defaultdict(list)
    for item in catalog["items"]:
        if item["domain"] == "event_text" or item["id"] in expected_refs:
            grouped_intervals[(item["source_span"]["start"], item["source_span"]["end"])].append(item["id"])
    intervals = sorted((start, end, ids) for (start, end), ids in grouped_intervals.items())
    if any(previous[1] > following[0] for previous, following in zip(intervals, intervals[1:])):
        raise KhcomError("event_catalog_overlap", "Intervalos textuais sobrepostos têm limites diferentes.")
    starts = [interval[0] for interval in intervals]
    for ref in facts["relocations"]:
        target = ref["target_address"] - BASE
        index = bisect.bisect_right(starts, target) - 1
        if index >= 0 and target < intervals[index][1]:
            start, _end, item_ids = intervals[index]
            for item_id in item_ids:
                text_refs[item_id].append({"source_offset": ref["source_offset"], "target_offset": target,
                                      "interior": target != start, "owner": ref["owner"],
                                      "known_script_reference": ref["source_offset"] in expected_refs[item_id]})
    return {"schema": "khcom-event-occurrences-v1", "source_sha256": digest, "commit": COMMIT,
            "event_count": table["size"] // 4, "occurrence_count": len(rows), "occurrences": rows,
            "references_by_id": dict(text_refs), "catalog_ids_with_occurrences": len(expected_refs),
            "catalog_ids_without_occurrences": [item["id"] for item in catalog["items"]
                if item["domain"] == "event_text" and item["id"] not in expected_refs],
            "unknown_counts": dict(Counter(issue for row in rows for issue in row["unknowns"])),
            "runtime_verified": False, "edit_authorized": False,
            "limitations": ["Matching ABS32 references are enumerated; calculated references are not disproved.",
                            "A script occurrence is not proof that normal campaign progression reaches it.",
                            "Other consumers, substitutions and box clipping are separate contracts."]}


def audit_event_text(data: bytes, *, matching_tree: Path, rom_identity: dict) -> dict:
    from .matching import audit_matching_bytes
    from .graphics import extract_fonts
    from .text import extract_catalog
    from .upstream import verify_upstream
    manifest = verify_upstream()
    sources = [item for item in manifest["files"] if item["path"] in SOURCE_FILES]
    if len(sources) != len(SOURCE_FILES):
        raise KhcomError("event_sources", "Fontes consumidoras precisam estar no manifesto fixado.")
    tree = Path(matching_tree).resolve()
    facts = audit_matching_bytes(data, rom_identity=rom_identity, rebuild_path=tree / "build/us/com_us.gba",
                                elf_path=tree / "build/us/com_us.elf", map_path=tree / "build/us/com_us.map", source_root=tree)
    catalog = extract_catalog(data)
    report = event_occurrences(data, catalog, facts)
    fonts, _files = extract_fonts(data)
    font = next(font for font in fonts["fonts"] if font["id"] == "message_latin")
    widths = fonts["latin_metrics"]["values"]
    bounds = [glyph["bounds"] for glyph in font["glyphs"]]
    items = {item["id"]: item for item in catalog["items"]}
    for row in report["occurrences"]:
        if row["unknowns"] or len(row["catalog_ids"]) != 1:
            row["layout"] = {"status": "unknown"}
            continue
        item = items[row["catalog_ids"][0]]
        try:
            layout = measure_event_pages(data[item["source_span"]["start"]:item["source_span"]["end"]], widths,
                                         origin=row["origin"], alternate_palette=row["alternate_palette"], glyph_bounds=bounds)
            row["layout"] = {"status": "source_model_measured", "page_count": layout["page_count"],
                             "glyph_counts": [page["glyph_count"] for page in layout["pages"]],
                             "next_code_units": [page["next_code_unit"] for page in layout["pages"]],
                             "box_clipping_verified": False}
        except KhcomError as error:
            row["layout"] = {"status": "unmodeled", "error": error.as_dict()}
    report["layout_counts"] = dict(Counter(row["layout"]["status"] for row in report["occurrences"]))
    report["evidence"] = {"matching": {key: facts[key] for key in ("rom", "rebuild", "elf", "map")},
                          "object_count": len(facts["objects"]), "sources": sources,
                          "font_sha256": font["sha256"], "metrics": fonts["latin_metrics"]}
    return report
