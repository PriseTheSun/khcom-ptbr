"""Conservative edit diagnostics, bound to freshly decoded ROM provenance.

Valid encoding and byte capacity never stand in for renderer/reference proof.
This owner produces one bounded write plan shared by validation/reinsertion.
"""
from collections import Counter
from dataclasses import dataclass
import unicodedata

from .errors import KhcomError
from .text import bind_catalog, extract_catalog, tokenize
from .upstream import load_textgen, sha256


@dataclass(frozen=True)
class TranslationPlan:
    report: dict
    writes: tuple[dict, ...]


def plan_translations(data: bytes, catalog: dict, *, profile_id: str | None = None,
                      matching_tree=None, rom_identity=None, parser=None,
                      check_identity: bool = True) -> TranslationPlan:
    from .credits_edit import prepare_credit_context, validate_credit_edit
    from .credits_profile import DOMAIN, PROFILE_ID

    if profile_id not in (None, PROFILE_ID):
        raise KhcomError("text_profile", "Perfil de reinserção não reconhecido.", profile_id=profile_id)
    if profile_id is not None and not check_identity:
        raise KhcomError("text_profile_identity", "Um perfil de jogo exige a identidade real da ROM.")
    if matching_tree is not None and profile_id is None:
        raise KhcomError("text_matching_profile", "Selecione o perfil consumidor do mapa matching.")
    parser = parser or load_textgen()
    actual = extract_catalog(data, parser=parser, check_identity=check_identity)
    pairs = bind_catalog(catalog, actual)
    codecs = parser.load_charmap("us")
    credit_context = None
    if profile_id == PROFILE_ID and any(o["domain"] == DOMAIN and e.get("translation") is not None
                                         and e["translation"] != o["source_text"] for o, e in pairs):
        credit_context = prepare_credit_context(data, actual, matching_tree=matching_tree, rom_identity=rom_identity)
    rows = []
    writes = []
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
        if original["domain"] == DOMAIN and credit_context is not None:
            encoded, contract = validate_credit_edit(original, candidate, credit_context)
            row.update({key: value for key, value in contract.items() if key != "diagnostics"})
            diagnostics.extend(contract["diagnostics"])
            row["status"] = "blocked" if diagnostics else "candidate_buildable_runtime_review_required"
            if not diagnostics:
                start = original["source_span"]["start"]
                writes.append({"owner": original["id"], "start": start, "end": start + len(encoded),
                               "source_sha256": sha256(data[start:start + len(encoded)]), "payload": encoded})
            continue
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
    if writes:
        writes.extend(credit_context.profile_writes)
    report = {"schema_version": 2, "operation": "candidate_text_validation", "source_sha256": actual["origin"]["sha256"],
            "selected_profile": profile_id, "profile_evidence": credit_context.evidence if credit_context else None,
            "items": rows, "changed_items": sum(row["changed"] for row in rows),
            "blocked_items": sum(row["status"] == "blocked" for row in rows),
            "diagnostic_counts": dict(Counter(d["code"] for row in rows for d in row["diagnostics"])),
            "release_approved": False, "complete_game_coverage": False,
            "limitations": ["No-edit records are not marked translated or reviewed.",
                            "Bytes and control checks do not establish pixel bounds, glyph rendering or reference completeness.",
                            "Only the explicitly selected occurrence contracts can produce a private candidate.",
                            "Unresolved reference candidates, renderers, styles and dynamic paths remain separate from release approval."]}
    report["planned_writes"] = [{key: value for key, value in write.items() if key != "payload"}
                                | {"target_sha256": sha256(write["payload"])} for write in writes]
    return TranslationPlan(report, tuple(writes))


def validate_translations(data: bytes, catalog: dict, *, profile_id: str | None = None,
                          matching_tree=None, rom_identity=None, parser=None, check_identity: bool = True) -> dict:
    return plan_translations(data, catalog, profile_id=profile_id, parser=parser,
                             matching_tree=matching_tree, rom_identity=rom_identity,
                             check_identity=check_identity).report


def apply_translation_plan(data: bytes, plan: TranslationPlan) -> tuple[bytes, dict]:
    """Apply the same encoded bytes that passed the owner; no second codec."""
    if sha256(data) != plan.report["source_sha256"]:
        raise KhcomError("text_plan_identity", "Origem mudou após a validação.")
    if plan.report["blocked_items"]:
        raise KhcomError("localization_blocked", "Há candidatos bloqueados; nenhuma ROM foi gerada.",
                         blocked_items=plan.report["blocked_items"], diagnostic_counts=plan.report["diagnostic_counts"])
    ordered = sorted(plan.writes, key=lambda write: write["start"])
    cursor = 0
    result = bytearray(data)
    for write in ordered:
        start, end = write["start"], write["end"]
        if not cursor <= start <= end <= len(data) or end - start != len(write["payload"]):
            raise KhcomError("text_write_overlap", "Plano contém sobreposição ou intervalo inválido.", owner=write["owner"])
        if sha256(data[start:end]) != write["source_sha256"]:
            raise KhcomError("text_write_source", "Reserva de origem mudou após a validação.", owner=write["owner"])
        result[start:end] = write["payload"]
        cursor = end
    cursor = 0
    for write in ordered:
        if result[cursor:write["start"]] != data[cursor:write["start"]]:
            raise KhcomError("text_write_extent", "Bytes fora do plano foram alterados.")
        cursor = write["end"]
    if len(result) != len(data) or result[cursor:] != data[cursor:]:
        raise KhcomError("text_write_extent", "Plano mudou o tamanho ou a cauda da ROM.")
    output = bytes(result)
    return output, {**plan.report, "operation": "fixed_text_reinsertion", "target_sha256": sha256(output),
                    "rom_size_unchanged": True, "outside_writes_unchanged": True, "relocated": False,
                    "equal": output == data, "bytes_changed": sum(a != b for a, b in zip(data, output)),
                    "candidate_runtime_verified": False}
