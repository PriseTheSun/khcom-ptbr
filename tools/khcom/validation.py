"""Conservative edit diagnostics, bound to freshly decoded ROM provenance.

Valid encoding and byte capacity never stand in for renderer/reference proof.
This module diagnoses candidates; it does not authorize general reinsertion.
"""
from collections import Counter
import unicodedata

from .text import bind_catalog, extract_catalog, tokenize
from .upstream import load_textgen, sha256


def validate_translations(data: bytes, catalog: dict, *, parser=None, check_identity: bool = True) -> dict:
    parser = parser or load_textgen()
    actual = extract_catalog(data, parser=parser, check_identity=check_identity)
    pairs = bind_catalog(catalog, actual)
    codecs = parser.load_charmap("us")
    rows = []
    for original, edited in pairs:
        candidate = edited.get("translation")
        row = {"id": original["id"], "source_sha256": original["source_sha256"],
               "source_bytes": original["source_span"]["end"] - original["source_span"]["start"],
               "byte_budget": original["byte_budget"], "candidate_bytes": None,
               "changed": candidate is not None and candidate != original["source_text"],
               "diagnostics": []}
        rows.append(row)
        if not row["changed"]:
            row["status"] = "no_edit_to_validate"
            continue
        diagnostics = row["diagnostics"]
        if unicodedata.normalize("NFC", candidate) != candidate:
            diagnostics.append({"code": "editorial_nfc", "message": "Normalize a edição para NFC pelo importador CSV/JSON."})
        invisible = sorted({f"U+{ord(char):04X}" for char in candidate
                            if char not in (" ", "\n", "\u3000") and unicodedata.category(char) in
                            {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp", "Zs"}})
        if invisible:
            diagnostics.append({"code": "invisible_editorial_characters", "codepoints": invisible})
        codec = codecs[original["codec_id"]]
        source_tokens = tokenize(original["source_text"], codec)
        source_controls = [token["name"] for token in source_tokens if token["kind"] != "text"]
        if original["opaque_codes"]:
            diagnostics.append({"code": "opaque_codes", "codes": original["opaque_codes"]})
        try:
            encoded = codec.encode(candidate, original["id"])
        except parser.TextError as error:
            diagnostics.append({"code": "encoding_error", "message": str(error)})
        else:
            row.update(candidate_bytes=len(encoded), candidate_sha256=sha256(encoded))
            # Interpret the actual bytes through their owner. A literal NUL
            # in editorial text is an END in the game, not an ordinary letter.
            candidate_tokens = tokenize(codec.decode(encoded), codec)
            candidate_controls = [token["name"] for token in candidate_tokens if token["kind"] != "text"]
            if candidate_controls != source_controls:
                diagnostics.append({"code": "controls_changed", "expected": source_controls, "actual": candidate_controls,
                                    "message": "Comandos, quebras e terminadores codificados divergem da origem."})
            if "END" in source_controls and (not candidate_tokens or candidate_tokens[-1].get("name") != "END"):
                diagnostics.append({"code": "terminator_position", "message": "Há texto após o terminador ou falta um terminador final."})
            if len(encoded) > original["byte_budget"]:
                diagnostics.append({"code": "byte_overflow", "actual": len(encoded), "maximum": original["byte_budget"]})
            if len(encoded) % codec.width:
                diagnostics.append({"code": "code_unit_alignment", "width": codec.width, "actual": len(encoded)})
        # Editable review/status annotations cannot fill these source-owned
        # unknowns. A future verified consumer registry will own that evidence.
        if original["pointer_refs"] is None:
            diagnostics.append({"code": "references_unknown", "message": original["pointer_refs_reason"]})
        missing = [field for field in ("context", "font_id", "box_id", "pixel_budget", "line_limit")
                   if original[field] is None]
        if missing:
            diagnostics.append({"code": "layout_unknown", "fields": missing, "message": original["layout_unknown_reason"]})
        row["status"] = "blocked" if diagnostics else "static_checks_passed_runtime_review_required"
    return {"schema_version": 1, "operation": "candidate_text_validation", "source_sha256": actual["origin"]["sha256"],
            "items": rows, "changed_items": sum(row["changed"] for row in rows),
            "blocked_items": sum(row["status"] == "blocked" for row in rows),
            "diagnostic_counts": dict(Counter(d["code"] for row in rows for d in row["diagnostics"])),
            "release_approved": False, "complete_game_coverage": False,
            "limitations": ["No-edit records are not marked translated or reviewed.",
                            "Bytes and control checks do not establish pixel bounds, glyph rendering or reference completeness.",
                            "General edited reinsertion remains unavailable until verified consumer contracts exist."]}
