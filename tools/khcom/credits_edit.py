"""Occurrence-owned contracts for fixed-position US credit candidates.

The source catalog remains CP932. This boundary selects the explicit PT-BR
profile, preserves script state and treats unresolved references as unknown.
Passing here permits a private candidate, never translation/release approval.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
import struct

from .credits import CreditTables, audit_credits, parse_line, read_credit_tables
from .credits_profile import DOMAIN, END_INDEX, FIRST_INDEX, PROFILE_ID, build_profile, decode_line, encode_line
from .errors import KhcomError
from .text import ROM_BASE
from .upstream import load_assetgen, sha256


def build_credit_probe(data: bytes, *, rom_identity: dict | None = None,
                       fetch: bool = False) -> tuple[bytes, dict]:
    """Build the one translated heading proven in both diagnostic endings.

    The font producer stays font-only. This recipe goes through the same
    occurrence validator and write plan as user-edited catalogs, rather than
    introducing another string patcher or a permission to edit all credits.
    """
    from .text import extract_catalog
    from .upstream import load_textgen
    from .validation import plan_translations, apply_translation_plan
    parser = load_textgen(fetch=fetch)
    catalog = extract_catalog(data, parser=parser)
    item_id = "us/staff_roll_script_text/gStaffRollVpGlobalProductionText"
    matches = [item for item in catalog["items"] if item["id"] == item_id]
    if (len(matches) != 1 or matches[0]["source_sha256"] !=
            "bb889c9f7467a26d25e5a35873fb54a57649c04168746dc44c6c4966bdca218d"):
        raise KhcomError("credits_probe_identity", "Cabeçalho piloto diverge da origem verificada.")
    matches[0]["translation"] = "@VP, produção global{END}"
    plan = plan_translations(data, catalog, profile_id=PROFILE_ID,
                             rom_identity=rom_identity, parser=parser)
    candidate, report = apply_translation_plan(data, plan)
    report.update(operation="experimental_translated_credit_probe", recipe_id="credits-heading-ptbr-v1",
                  edited_ids=[item_id], historical_runtime_evidence="docs/vertical-credit.md")
    # The historical run is linked, never attributed to this new invocation.
    report["candidate_runtime_verified"] = False
    return candidate, report


@dataclass(frozen=True)
class CreditEditContext:
    occurrences: dict[str, list[dict]]
    references: dict[str, dict]
    tables: CreditTables
    glyphs: tuple[dict, dict]
    profile_writes: tuple[dict, ...]
    evidence: dict


def scan_credit_references(data: bytes, items: list[dict], rows: list[dict]) -> dict[str, dict]:
    """Compare aligned pointer-shaped words with the source-owned script.

    This is not a search for all ARM address constructions or a free-space
    proof. Unexpected/interior values remain candidates for investigation.
    """
    ordered = sorted(items, key=lambda item: item["allocation_span"]["start"])
    starts = [ROM_BASE + item["allocation_span"]["start"] for item in ordered]
    result = {item["id"]: {"script_references": [], "unexpected_pointer_candidates": [],
                          "interior_pointer_candidates": [], "aliases": item["aliases"]}
              for item in ordered}
    if not ordered:
        raise KhcomError("credits_contract", "Inventário de créditos vazio.")
    high = max(item["allocation_span"]["end"] for item in ordered) + ROM_BASE
    known = {}
    by_id = {item["id"]: item for item in ordered}
    for row in rows:
        item = by_id[row["id"]]
        address = int(row["pointer_address"], 16)
        offset = address - ROM_BASE
        target = item["source_span"]["start"] + ROM_BASE
        if offset < 0 or offset % 4 or offset + 4 > len(data):
            raise KhcomError("credits_pointer_alignment", "Referência do roteiro não é um u32 alinhado válido.", row=row["row"])
        if offset in known or struct.unpack_from("<I", data, offset)[0] != target:
            raise KhcomError("credits_pointer", "Referência do roteiro diverge do texto de origem.", row=row["row"])
        known[offset] = row["id"]
        result[row["id"]]["script_references"].append({"row": row["row"], "address": address, "target": target})
    for index, (value,) in enumerate(struct.iter_unpack("<I", memoryview(data)[:len(data) // 4 * 4])):
        if not starts[0] <= value < high:
            continue
        item = ordered[bisect_right(starts, value) - 1]
        if value >= ROM_BASE + item["allocation_span"]["end"]:
            continue
        offset = index * 4
        record = {"address": ROM_BASE + offset, "target": value,
                  "relative_to_text": value - ROM_BASE - item["source_span"]["start"]}
        if record["relative_to_text"]:
            result[item["id"]]["interior_pointer_candidates"].append(record)
        elif known.get(offset) != item["id"]:
            result[item["id"]]["unexpected_pointer_candidates"].append(record)
    return result


def classify_matching_references(data: bytes, references: dict, facts: dict) -> dict:
    """Consume fresh matching-owner facts without interpreting ELF or assets."""
    if (facts.get("schema") != "khcom-matching-facts-v1" or not facts.get("baseline_byte_identical")
            or facts.get("rom", {}).get("sha256") != sha256(data)):
        raise KhcomError("credits_matching_identity", "Fatos do linker não pertencem à origem validada.")
    by_offset = {item["source_offset"]: item for item in facts["candidate_words"]}
    for record in references.values():
        record["encoded_asset_coincidences"] = []
        record["linker_references"] = []
        for key in ("unexpected_pointer_candidates", "interior_pointer_candidates"):
            unresolved = []
            for candidate in record[key]:
                fact = by_offset.get(candidate["address"] - ROM_BASE)
                if fact is None or fact["value"] != candidate["target"]:
                    raise KhcomError("credits_matching_word", "Fato de palavra ausente/divergente da varredura.")
                if fact["classification"] == "encoded_asset_data_verified":
                    record["encoded_asset_coincidences"].append({**candidate, "evidence": fact})
                else:
                    unresolved.append({**candidate, "matching_evidence": fact})
                    if fact["classification"] == "linker_abs32_reference":
                        record["linker_references"].append(fact["relocation"])
            record[key] = unresolved
    return {key: facts[key] for key in ("schema", "rom", "rebuild", "elf", "map", "objects",
                                       "candidate_words", "limitations")}


def prepare_credit_context(data: bytes, catalog: dict, *, matching_tree: Path | None = None,
                           rom_identity: dict | None = None) -> CreditEditContext:
    prepared, profile, files = build_profile(data)
    owner = load_assetgen()
    original_tables, _, addresses = read_credit_tables(data, owner)
    widths = tuple(prepared[addresses[f"gStaffRollFont{font}Widths"] - ROM_BASE:
                            addresses[f"gStaffRollFont{font}Widths"] - ROM_BASE + len(original_tables.widths[font])]
                   for font in (0, 1))
    tables = CreditTables(original_tables.pages_and_codes, original_tables.single_byte_map, widths)
    audit = audit_credits(data)
    occurrences: dict[str, list[dict]] = {}
    font = 0
    for row in audit["rows"]:
        occurrences.setdefault(row["id"], []).append({**row, "font_before": font})
        font = row["font_after"]
    glyphs = []
    for font, height in ((0, 16), (1, 8)):
        w, _h, pixels = owner.sprite_sheet.read_png(files[f"font{font}.png"])
        observed = set(audit["glyph_usage"][font]["indices_observed_in_this_script"])
        observed.update(range(FIRST_INDEX, END_INDEX))
        # The V2 runtime pixel proof also retained these authored ASCII
        # labels. In particular font0's digit 0 was absent from the original
        # scroll; admitting all ASCII here would overstate that evidence.
        observed.update(tables.measure(f"TESTE {font} ".encode("ascii"), font)["glyph_indices"])
        records = {}
        for index in observed:
            x, y = index % 16 * 8, index // 16 * height
            nonzero = [(column, line) for line in range(height) for column in range(8)
                       if pixels[(y + line) * w + x + column]]
            records[index] = {"advance": widths[font][index] or 8, "cell_height": height,
                              "nonzero_bounds": [min(a for a, b in nonzero), min(b for a, b in nonzero),
                                                 max(a for a, b in nonzero) + 1, max(b for a, b in nonzero) + 1] if nonzero else None,
                              "evidence_scope": "original_US_scroll_and_PTBR_pilot_v2"}
        glyphs.append(records)
    writes = tuple({"owner": "font_profile/" + span["resource"], "start": span["start"], "end": span["end"],
                    "source_sha256": span["source_sha256"], "payload": prepared[span["start"]:span["end"]]}
                   for span in profile["allowed_spans"])
    items = [item for item in catalog["items"] if item["domain"] == DOMAIN]
    references = scan_credit_references(data, items, audit["rows"])
    matching_evidence = None
    if matching_tree is not None:
        from .matching import audit_matching_bytes
        tree = matching_tree.resolve()
        output = tree / "build/us"
        offsets = [candidate["address"] - ROM_BASE for record in references.values()
                   for key in ("unexpected_pointer_candidates", "interior_pointer_candidates")
                   for candidate in record[key]]
        facts = audit_matching_bytes(data, rom_identity=rom_identity or catalog["origin"],
                                     rebuild_path=output / "com_us.gba", elf_path=output / "com_us.elf",
                                     map_path=output / "com_us.map", source_root=tree, candidate_offsets=offsets)
        matching_evidence = classify_matching_references(data, references, facts)
    return CreditEditContext(occurrences, references, tables,
                             tuple(glyphs), writes,
                             {"profile_id": PROFILE_ID, "profile_target_sha256": profile["target_sha256"],
                              "original_script_sha256": audit["script_table"]["sha256"],
                              "consumer_investigation": "docs/credits-consumers.md",
                              "original_runtime": "docs/credits-mode-entry.md",
                              "accent_runtime": "docs/credits-pilot.md",
                              "matching": matching_evidence,
                              "observed_rows": [0, 626], "unobserved_rows": [627, 630],
                              "reference_scope": "pinned_US_source_and_aligned_pointer_candidates; not_formal_whole_ROM_reachability"})


def encode_catalog_credit(candidate: str) -> bytes:
    # The public catalog retains its {END} representation. The explicit
    # profile API itself owns plain lines and one appended NUL.
    if not candidate.endswith("{END}") or candidate.count("{END}") != 1:
        raise KhcomError("credits_terminator", "Créditos do catálogo exigem um único {END} final.")
    body = candidate[:-5]
    if "{" in body or "}" in body:
        raise KhcomError("credits_control", "Token de catálogo não admitido no corpo de créditos.")
    encoded = encode_line(body)
    if decode_line(encoded) != body:
        raise KhcomError("credits_roundtrip", "Texto não reconstrói a representação editorial do perfil.")
    return encoded


def validate_credit_edit(original: dict, candidate: str, context: CreditEditContext) -> tuple[bytes | None, dict]:
    diagnostics = []
    result = {"profile_id": PROFILE_ID, "occurrences": [], "references": context.references.get(original["id"]),
              "diagnostics": diagnostics, "candidate_bytes": None,
              "candidate_runtime_verified": False, "linguistic_review_approved": False}
    raw = None
    try:
        raw = encode_catalog_credit(candidate)
        result.update(candidate_bytes=len(raw), candidate_sha256=sha256(raw))
        if len(raw) > original["byte_budget"]:
            diagnostics.append({"code": "byte_overflow", "actual": len(raw), "maximum": original["byte_budget"]})
    except KhcomError as error:
        diagnostics.append(error.as_dict())
    refs = result["references"]
    if not refs or not refs["script_references"]:
        diagnostics.append({"code": "references_unknown", "message": "Item sem referências comprovadas no roteiro."})
    elif refs["unexpected_pointer_candidates"] or refs["interior_pointer_candidates"]:
        diagnostics.append({"code": "credits_reference_candidates", "message": "Valores de referência adicionais/interiores exigem classificação antes da edição."})
    occurrences = context.occurrences.get(original["id"], [])
    if not occurrences:
        diagnostics.append({"code": "layout_unknown", "message": "Item sem ocorrência no renderer de créditos."})
    for source in occurrences:
        issues = []
        row = {"row": source["row"], "pointer_address": source["pointer_address"],
               "font_before": source["font_before"], "font_after": source["font_after"],
               "box": {"left": 16, "right_exclusive": 224, "line_limit": 1,
                       "scope": "conservative_original_visible_window"},
               "dynamic_values": {"kind": "none", "reason": "This literal staff-roll path has no runtime variable substitution."},
               "diagnostics": issues, "candidate_runtime_verified": False}
        result["occurrences"].append(row)
        if source["row"] > 626:
            issues.append({"code": "credits_occurrence_unobserved", "message": "Ocorrência posterior ao término original da rolagem."})
        if source["kind"] != "text" or not any(run["codes"] for run in source["runs"]):
            issues.append({"code": "credits_structural_line", "message": "Linha estrutural/vazia ou caminho sem prova de texto editável."})
        if raw is not None:
            try:
                parsed = parse_line(raw, source["font_before"], context.tables)
                row["candidate"] = parsed
                if (parsed["commands"] != source["commands"] or parsed["kind"] != source["kind"]
                        or parsed["font_after"] != source["font_after"]
                        or parsed.get("alignment") != source.get("alignment")):
                    issues.append({"code": "controls_changed", "message": "Prefixos, alinhamento, tipo ou estado de fonte divergente da ocorrência original."})
                if len(parsed["runs"]) != 1:
                    issues.append({"code": "credits_layout_path_unverified", "message": "Somente desenho literal de uma coluna foi observado."})
                for run in parsed["runs"]:
                    if not run["within_visible_advance_window"] or not run["within_tilemap_advance"]:
                        issues.append({"code": "pixel_overflow", "actual": run["advance_pixels"], "x": run["x"],
                                       "right": run["right"], "maximum": 208})
                    for index in sorted(set(run["glyph_indices"])):
                        glyph = context.glyphs[run["font"]].get(index)
                        if glyph is None:
                            issues.append({"code": "glyph_context_unknown", "font": run["font"], "index": index})
                        elif glyph["nonzero_bounds"] and (glyph["nonzero_bounds"][2] > glyph["advance"]
                                                          or glyph["nonzero_bounds"][3] > glyph["cell_height"]):
                            issues.append({"code": "glyph_clipped", "font": run["font"], "index": index,
                                           "bounds": glyph["nonzero_bounds"], "advance": glyph["advance"]})
            except KhcomError as error:
                issues.append(error.as_dict())
        diagnostics.extend({**issue, "occurrence_row": source["row"]} for issue in issues)
    return raw, result
