"""Conservative in-place edits for matching US EventMessage occurrences."""
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .errors import KhcomError
from .event_contract import event_occurrences, SOURCE_FILES
from .event_layout import measure_event_pages
from .upstream import sha256

PROFILE_ID = "event-message-us-v1"


@dataclass(frozen=True)
class EventEditContext:
    occurrences: dict
    references: dict
    widths: list
    bounds: list
    source_bytes: dict
    evidence: dict


def prepare_event_context(data: bytes, catalog: dict, *, matching_tree: Path | None,
                          rom_identity: dict | None) -> EventEditContext:
    from .matching import audit_matching_bytes
    from .graphics import extract_fonts
    from .upstream import verify_upstream
    if matching_tree is None:
        raise KhcomError("event_matching_required", "O perfil de eventos exige uma árvore matching revalidada.")
    manifest = verify_upstream()
    sources = [item for item in manifest["files"] if item["path"] in SOURCE_FILES]
    if len(sources) != len(SOURCE_FILES):
        raise KhcomError("event_sources", "Faltam consumidores fixados no manifesto de origem.")
    tree = Path(matching_tree).resolve()
    facts = audit_matching_bytes(data, rom_identity=rom_identity or catalog["origin"],
        rebuild_path=tree / "build/us/com_us.gba", elf_path=tree / "build/us/com_us.elf",
        map_path=tree / "build/us/com_us.map", source_root=tree)
    ledger = event_occurrences(data, catalog, facts)
    fonts, _files = extract_fonts(data)
    font = next(font for font in fonts["fonts"] if font["id"] == "message_latin")
    occurrences = defaultdict(list)
    for row in ledger["occurrences"]:
        for item_id in row["catalog_ids"]:
            occurrences[item_id].append(row)
    return EventEditContext(dict(occurrences), ledger["references_by_id"], fonts["latin_metrics"]["values"],
        [glyph["bounds"] for glyph in font["glyphs"]],
        {item["id"]: data[item["source_span"]["start"]:item["source_span"]["end"]] for item in catalog["items"]},
        {"profile_id": PROFILE_ID, "matching": {key: facts[key] for key in ("rom", "rebuild", "elf", "map")},
         "sources": sources, "font_sha256": font["sha256"], "metrics_sha256": fonts["latin_metrics"]["sha256"],
         "glyph_runtime": "docs/font-runtime-coverage.md", "occurrence_contract": "docs/event-text.md",
         "limits": ["Only matching script references are admitted; calculated references are not formally disproved.",
                    "Original per-page glyph extents are a conservative budget, not a universal window measurement.",
                    "Every new candidate still requires visual execution and linguistic review."]})


def _page_envelope(page: dict, origin: list[int]) -> dict:
    glyphs = page["glyphs"]
    return {"left": origin[0], "top": origin[1],
            "right_exclusive": max([origin[0]] + [max(g["x"] + g["advance"],
                g["ink_bounds"][2] if g["ink_bounds"] else g["x"]) for g in glyphs]),
            "bottom_exclusive": max([origin[1]] + [g["y"] + 16 for g in glyphs])}


def validate_event_edit(original: dict, encoded: bytes, context: EventEditContext) -> dict:
    """Measure every occurrence against the source's actual page envelope.

    Encoding/controls/byte budgets are owned by the common validator. This
    consumer adds reference, font and occurrence constraints without relaxing
    any common diagnostic or trusting editable catalog annotations.
    """
    diagnostics, outputs = [], []
    item_id = original["id"]
    occurrences = context.occurrences.get(item_id, [])
    references = context.references.get(item_id, [])
    if not occurrences:
        diagnostics.append({"code": "event_occurrences_unknown"})
    expected = {row["references"]["text"]["source_offset"] for row in occurrences}
    if (not references or {ref["source_offset"] for ref in references} != expected
            or any(ref["interior"] or not ref["known_script_reference"] for ref in references)):
        diagnostics.append({"code": "event_extra_or_unknown_consumers", "references": references})
    source = context.source_bytes[item_id]
    for row in occurrences:
        issues = []
        result = {"event_id": row["event_id"], "entry_index": row["entry_index"],
                  "entry_offset": row["entry_offset"], "origin": row["origin"],
                  "alternate_palette": row["alternate_palette"], "diagnostics": issues,
                  "candidate_runtime_verified": False,
                  "dynamic_values": {"kind": "none", "scope": "Literal MessageScriptEntry consumed directly by MsgwinLoadEntry."}}
        outputs.append(result)
        if row["unknowns"] or len(row["catalog_ids"]) != 1:
            issues.append({"code": "event_occurrence_unknown", "unknowns": row["unknowns"],
                           "catalog_ids": row["catalog_ids"]})
        else:
            try:
                args = {"origin": row["origin"], "alternate_palette": row["alternate_palette"],
                        "glyph_bounds": context.bounds}
                before = measure_event_pages(source, context.widths, **args)
                after = measure_event_pages(encoded, context.widths, **args)
                budgets = [_page_envelope(page, row["origin"]) for page in before["pages"]]
                result.update(source_page_envelopes=budgets, source_page_count=before["page_count"],
                              candidate_page_count=after["page_count"], candidate_glyph_count=after["total_glyphs"])
                if after["page_count"] > before["page_count"]:
                    issues.append({"code": "event_page_overflow", "maximum": before["page_count"], "actual": after["page_count"]})
                source_icons = {g["code"] for p in before["pages"] for g in p["glyphs"] if g["kind"] == "icon"}
                for page_index, page in enumerate(after["pages"]):
                    if page_index >= len(budgets):
                        break
                    budget = budgets[page_index]
                    for glyph in page["glyphs"]:
                        bounds = glyph["ink_bounds"]
                        if glyph["kind"] == "icon" and glyph["code"] not in source_icons:
                            issues.append({"code": "event_icon_changed", "code_unit": glyph["code_unit"]})
                        if glyph["kind"] != "space" and bounds is None:
                            issues.append({"code": "event_empty_glyph", "glyph_index": glyph["glyph_index"]})
                        advance_ok = (budget["left"] <= glyph["x"] <= glyph["x"] + glyph["advance"] <= budget["right_exclusive"]
                                      and budget["top"] <= glyph["y"] <= glyph["y"] + 16 <= budget["bottom_exclusive"])
                        ink_ok = bounds is None or (max(0, budget["left"]) <= bounds[0] < bounds[2] <= min(240, budget["right_exclusive"])
                                      and max(0, budget["top"]) <= bounds[1] < bounds[3] <= min(160, budget["bottom_exclusive"]))
                        if not advance_ok or not ink_ok:
                            issues.append({"code": "event_pixel_overflow", "page": page_index, "code_unit": glyph["code_unit"],
                                           "advance_origin": [glyph["x"], glyph["y"]], "ink_bounds": bounds, "budget": budget})
            except KhcomError as error:
                issues.append(error.as_dict())
        diagnostics.extend({**issue, "event_id": row["event_id"], "entry_index": row["entry_index"]} for issue in issues)
    return {"profile_id": PROFILE_ID, "occurrences": outputs, "references": references,
            "candidate_sha256": sha256(encoded), "diagnostics": diagnostics,
            "candidate_runtime_verified": False, "linguistic_review_approved": False}
