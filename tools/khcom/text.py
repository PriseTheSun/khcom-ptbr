"""Text inventory on top of verified khcom formats, with explicit unknowns.

This phase proves extraction and an unedited binary round-trip. It does not
approve translated text, glyph coverage, pixel budgets or pointer relocation.
"""

from __future__ import annotations

from collections import Counter
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from .errors import KhcomError
from .io import read_file, write_new
from .upstream import COMMIT, PROJECT_ROOT, load_textgen, sha256, upstream_rom_identity

ROM_BASE = 0x08000000
CATALOG_VERSION = 1
TOKEN_RE = re.compile(r"\{([^{}]+)\}|\n")
CSV_FIELDS = ["id", "source_text", "translation", "has_translation", "metadata_json"]
# Resource budgets, not discovered game-format limits. The current inventory
# is 6,736 records / 14.3 MB JSON; leave room for translations and annotations.
CATALOG_MAX_BYTES = 64 * 1024 * 1024
CATALOG_MAX_ITEMS = 16384
CSV_MAX_FIELD_CHARS = 128 * 1024


def tokenize(text: str, encoding: Any) -> list[dict]:
    """Keep upstream decoded control spelling; unknown escapes stay unknown."""
    tokens: list[dict] = []
    cursor = 0
    for match in TOKEN_RE.finditer(text):
        if match.start() > cursor:
            tokens.append({"kind": "text", "value": text[cursor:match.start()]})
        name = "NL" if match.group() == "\n" else match.group(1)
        kind = "control" if name in encoding.controls else "opaque_code"
        tokens.append({"kind": kind, "name": name, "spelling": match.group()})
        cursor = match.end()
    if cursor < len(text):
        tokens.append({"kind": "text", "value": text[cursor:]})
    return tokens


def _span(start: int, end: int) -> dict:
    return {"start": start - ROM_BASE, "end": end - ROM_BASE, "address": f"0x{start:08X}"}


def extract_catalog(data: bytes, *, fetch: bool = False, parser: Any = None, check_identity: bool = True) -> dict:
    parser = parser or load_textgen(fetch=fetch)
    origin = {"sha256": sha256(data), "sha1": hashlib.sha1(data).hexdigest(), "size": len(data)}
    declared = upstream_rom_identity() if check_identity else None
    if declared and origin["sha1"] != declared["sha1"]:
        raise KhcomError("upstream_rom_mismatch", "A ROM não corresponde ao alvo declarado pelo upstream.", expected=declared["sha1"], actual=origin["sha1"])
    items: list[dict] = []
    intervals: list[dict] = []
    pool_reports: list[dict] = []
    seen_ids: set[str] = set()
    try:
        encodings = parser.load_charmap("us")
        pools = parser.load_pools()
        for pool in pools:
            aliases = pool.aliases("us")
            count = 0
            record_count = 0
            units = pool.units("us")
            for unit in units:
                encoding = unit.encoding(encodings)
                if not ROM_BASE <= unit.start <= unit.end <= ROM_BASE + len(data):
                    raise KhcomError("text_range", "Intervalo textual fora da ROM.", pool=pool.name, unit=unit.name)
                # The upstream owner verifies records, padding, terminators,
                # exact pool ends and decode/encode equality before we retain facts.
                decoded = dict(parser.decode_unit(unit, encoding, data))

                def content_of(entry: dict, address: int) -> bytes:
                    if "record" in entry:
                        return b""
                    return encoding.encode(decoded[entry["name"]], entry["name"])

                placed, _ = unit.layout(content_of)
                for entry, address, allocation in placed:
                    name = entry["name"]
                    span = _span(address, address + allocation)
                    payload = data[span["start"]:span["end"]]
                    identity = f"us/{pool.name}/{name}"
                    if identity in seen_ids:
                        raise KhcomError("text_duplicate_id", "ID textual duplicado.", id=identity)
                    seen_ids.add(identity)
                    is_record = "record" in entry
                    intervals.append({"id": identity, "kind": "record" if is_record else "text", "span": span, "sha256": sha256(payload)})
                    if is_record:
                        record_count += 1
                        continue
                    source_text = decoded[name]
                    encoded = encoding.encode(source_text, identity)
                    if payload[:len(encoded)] != encoded:
                        raise KhcomError("text_roundtrip", "Texto recodificado difere da ROM.", id=identity)
                    tokens = tokenize(source_text, encoding)
                    items.append({
                        "id": identity, "symbol": name, "domain": pool.name,
                        "unit": unit.name, "codec_id": unit.spec["encoding"],
                        "source_span": _span(address, address + len(encoded)),
                        "allocation_span": span, "source_sha256": sha256(encoded),
                        "source_text": source_text, "tokens": tokens,
                        "aliases": sorted(alias for alias, target in aliases.items() if target == name),
                        "pointer_refs": None, "pointer_refs_reason": "Manifestos textuais não inventariam todos os consumidores/referências.",
                        "context": None, "campaign": None, "font_id": None, "box_id": None,
                        "byte_budget": allocation, "byte_budget_scope": "Reserva original verificada; não autoriza expansão ou realocação.",
                        "pixel_budget": None, "line_limit": None,
                        "layout_unknown_reason": "Métricas, caixa e glifos ainda não verificados no renderer e em runtime.",
                        "translation": None, "translation_input": None,
                        "status": "untranslated", "reviewer": None, "evidence_refs": [],
                        "opaque_codes": [token["name"] for token in tokens if token["kind"] == "opaque_code"],
                        "provenance": {"commit": COMMIT, "manifest": f"config/text/{pool.name}.yaml", "kind": "upstream_manifest_verified_against_rom"},
                    })
                    count += 1
            pool_reports.append({"pool": pool.name, "present_in_us": bool(units), "units": len(units), "texts": count, "records": record_count, "verified": True})
    except parser.TextError as error:
        raise KhcomError("upstream_format_mismatch", "O parser fixado não confirmou os bytes da ROM.", reason=str(error)) from error
    # Reject overlapping ownership instead of making write order select bytes.
    ordered = sorted(intervals, key=lambda item: item["span"]["start"])
    for previous, current in zip(ordered, ordered[1:]):
        if current["span"]["start"] < previous["span"]["end"]:
            raise KhcomError("text_overlap", "Manifestos atribuem intervalos sobrepostos.", first=previous["id"], second=current["id"])
    return {
        "format_version": CATALOG_VERSION, "origin": origin,
        "upstream": {"commit": COMMIT, "declared_target": declared},
        "coverage": {"status": "partial_inventory", "complete_game_coverage": False,
            "pool_files_examined": len(pool_reports), "text_items": len(items),
            "records_verified": sum(p["records"] for p in pool_reports),
            "interpreted_interval_bytes": sum(i["span"]["end"] - i["span"]["start"] for i in intervals),
            "limitations": ["Somente os pools dos manifestos fixados; não é extração certificada de todo o jogo.", "Texto gráfico/vídeos, referências de consumidores e contexto ainda não inventariados.", "Nenhuma tradução, fonte, largura em pixels ou execução do jogo foi validada."]},
        "pools": pool_reports, "intervals": intervals, "items": items,
    }


def validate_catalog(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("format_version") != CATALOG_VERSION or not isinstance(value.get("items"), list):
        raise KhcomError("catalog_schema", "Catálogo inválido ou versão não suportada.")
    if len(value["items"]) > CATALOG_MAX_ITEMS:
        raise KhcomError("catalog_budget", "Catálogo excede o orçamento de itens.", maximum=CATALOG_MAX_ITEMS)
    identities: set[str] = set()
    for item in value["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("source_text"), str):
            raise KhcomError("catalog_schema", "Item do catálogo sem ID/texto de origem válido.")
        if item["id"] in identities:
            raise KhcomError("catalog_duplicate", "ID duplicado no catálogo.", id=item["id"])
        identities.add(item["id"])
        if item.get("translation") is not None and not isinstance(item["translation"], str):
            raise KhcomError("catalog_schema", "Tradução deve ser texto ou null.", id=item["id"])
        if any(len(item.get(key) or "") > CSV_MAX_FIELD_CHARS for key in ("id", "source_text", "translation")):
            raise KhcomError("catalog_budget", "Campo textual excede o orçamento de edição.", id=item["id"], maximum=CSV_MAX_FIELD_CHARS)
    return value


def read_catalog(path: Path) -> dict:
    try:
        value = json.loads(read_file(path, CATALOG_MAX_BYTES).decode("utf-8"))
    except (OSError, ValueError, RecursionError) as error:
        raise KhcomError("catalog_read", "Não foi possível ler o catálogo JSON UTF-8.", path=str(path), reason=str(error)) from error
    return validate_catalog(value)


def bind_catalog(catalog: dict, actual: dict) -> list[tuple[dict, dict]]:
    """Bind editable fields to freshly observed identity, spans and aliases."""
    validate_catalog(catalog)
    if catalog.get("origin") != actual["origin"] or catalog.get("upstream") != actual["upstream"]:
        raise KhcomError("catalog_origin", "Catálogo não corresponde à ROM/revisão upstream.")
    expected = {item["id"]: item for item in actual["items"]}
    submitted = {item["id"]: item for item in catalog["items"]}
    if set(submitted) != set(expected):
        raise KhcomError("catalog_membership", "Itens ausentes ou extras no catálogo.", missing=sorted(set(expected) - set(submitted)), extra=sorted(set(submitted) - set(expected)))
    if catalog.get("intervals") != actual["intervals"] or catalog.get("pools") != actual["pools"]:
        raise KhcomError("catalog_provenance", "Intervalos ou inventário de pools foram alterados.")
    mutable = {"translation", "translation_input", "status", "reviewer", "evidence_refs"}
    pairs = []
    for identity, original in expected.items():
        item = submitted[identity]
        if {k: v for k, v in item.items() if k not in mutable} != {k: v for k, v in original.items() if k not in mutable}:
            raise KhcomError("catalog_provenance", "Metadados de origem alterados.", id=identity)
        pairs.append((original, item))
    return pairs


def reinsert_unedited(data: bytes, catalog: dict, *, parser: Any = None, check_identity: bool = True) -> tuple[bytes, dict]:
    """Re-encode every parsed text; preserve records, padding and opaque bytes.

    Do not offer an unsafe bypass for edits before glyphs/layout/refs are known.
    """
    parser = parser or load_textgen()
    actual = extract_catalog(data, parser=parser, check_identity=check_identity)
    pairs = bind_catalog(catalog, actual)
    out = bytearray(data)
    encodings = parser.load_charmap("us")
    log = []
    for original, item in pairs:
        identity = original["id"]
        translation = item.get("translation")
        if translation is not None and translation != original["source_text"]:
            raise KhcomError("localization_unverified", "Reinserção editada bloqueada: glifos, pixels e referências ainda não foram validados. Esta fase verifica apenas o round-trip sem edição.", id=identity)
        encoded = encodings[original["codec_id"]].encode(original["source_text"], identity)
        span = original["source_span"]
        if len(encoded) != span["end"] - span["start"] or sha256(encoded) != original["source_sha256"]:
            raise KhcomError("text_roundtrip", "O texto não reconstitui os bytes de origem.", id=identity)
        out[span["start"]:span["end"]] = encoded
        log.append({"id": identity, "span": span, "sha256": sha256(encoded), "unchanged": True})
    result = bytes(out)
    if result != data:
        raise KhcomError("rom_roundtrip", "Round-trip integral divergente.")
    return result, {"format_version": 1, "operation": "unedited_roundtrip", "source_sha256": sha256(data), "target_sha256": sha256(result), "equal": True, "text_intervals_reencoded": len(log), "opaque_bytes_preserved_not_interpreted": len(data) - sum(item["source_span"]["end"] - item["source_span"]["start"] for item in actual["items"]), "intervals": log, "limitations": actual["coverage"]["limitations"]}


DIALOGUE_PROBES = {
    "sora-opening": {"id": "us/event_text/gEvent000Text00",
                     "source_sha256": "73d4a10e436e6793e613cc772d945f80aa9c70307177eab8d48c6b3d5bb23da5",
                     "translation": "Não há ninguém aqui.{END}"},
    "riku-opening": {"id": "us/event_text/gEvent149Text01",
                     "source_sha256": "98f5336a777eccc7635a3386a356292003f25671c80103512a0cfd095029407e",
                     "translation": "Onde…onde estou…{END}"},
}


def build_dialogue_probe(data: bytes, *, fetch: bool = False, scene: str = "sora-opening") -> tuple[bytes, dict]:
    """One selected fixed experimental dialogue; never accepts arbitrary edits.

    The original dialogue was reached by the runtime harness. This candidate
    exists to verify its replacement in that same runtime, not to authorize
    bulk localization or certify every consumer of the string.
    """
    from .graphics import extract_fonts

    spec = DIALOGUE_PROBES.get(scene)
    if spec is None:
        raise KhcomError("probe_scene", "Cena piloto não reconhecida.", scene=scene)
    identity = spec["id"]
    candidate_text = spec["translation"]
    parser = load_textgen(fetch=fetch)
    catalog = extract_catalog(data, parser=parser)
    item = next((item for item in catalog["items"] if item["id"] == identity), None)
    if item is None or item["source_sha256"] != spec["source_sha256"] or item["codec_id"] != "game":
        raise KhcomError("probe_identity", "A cena piloto não corresponde à origem fixada.")
    original_text = item["source_text"]
    font_report, _files = extract_fonts(data)
    latin = next(font for font in font_report["fonts"] if font["id"] == "message_latin")
    codec = parser.load_charmap("us")["game"]
    original = codec.encode(original_text, identity)
    candidate = codec.encode(candidate_text, identity)
    if len(candidate) > item["byte_budget"]:
        raise KhcomError("probe_capacity", "Piloto excederia a reserva original.")
    controls = lambda text: [token for token in tokenize(text, codec) if token["kind"] != "text"]
    if controls(candidate_text) != controls(original_text):
        raise KhcomError("probe_controls", "Controles do piloto devem permanecer idênticos.")
    widths = font_report["latin_metrics"]["values"]

    def advance(encoded: bytes) -> tuple[int, list[int]]:
        codes = [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded) - 2, 2)]
        if any(not 32 <= code <= 255 for code in codes):
            raise KhcomError("probe_glyph", "Piloto aceita somente os índices latinos diretos verificados.")
        if any(code != 32 and not latin["glyphs"][code]["nonzero_pixels"] for code in codes):
            raise KhcomError("probe_glyph", "Piloto contém glifo vazio.")
        return sum(widths[code] for code in codes), codes

    source_width, _ = advance(original)
    candidate_width, codes = advance(candidate)
    if candidate_width > source_width:
        raise KhcomError("probe_width", "Piloto excederia o avanço horizontal da origem.")
    span = item["source_span"]
    output = bytearray(data)
    output[span["start"]:span["start"] + len(candidate)] = candidate
    result = bytes(output)
    if len(result) != len(data) or result[:span["start"]] != data[:span["start"]] or result[span["start"] + len(candidate):] != data[span["start"] + len(candidate):]:
        raise KhcomError("probe_boundary", "Piloto modificaria bytes fora da substituição fixa.")
    report = {"format_version": 1, "operation": "experimental_fixed_dialogue_probe", "id": identity, "source_sha256": sha256(data), "target_sha256": sha256(result), "rom_size": len(result), "span": span, "candidate_translation": candidate_text, "source_bytes": len(original), "candidate_bytes": len(candidate), "tail_bytes_preserved": len(original) - len(candidate), "source_advance_pixels": source_width, "candidate_advance_pixels": candidate_width, "glyph_indices": codes, "controls_unchanged": True, "relocated": False, "outside_candidate_unchanged": True, "latin_metrics": {key: value for key, value in font_report["latin_metrics"].items() if key != "values"}, "latin_asset_sha256": latin["sha256"], "frame_pointer_table": latin["frame_pointer_table"], "status": "awaiting_matching_runtime_capture", "release_approved": False, "limitations": ["One explicit dialogue only; general reinsertion remains blocked.", "Original runtime scene was observed separately; candidate screenshot and runtime trace are still required.", "All consumers and substring references are not proven; no relocation or expansion is authorized.", "Advance comparison is from the verified Latin table, not a universal box-width budget."]}
    report["scene"] = scene
    report["limitations"][0] = "One explicit dialogue only; arbitrary dialogue reinsertion remains blocked."
    return result, report


def _csv_metadata(item: dict) -> dict:
    return {key: value for key, value in item.items() if key not in {"id", "source_text", "translation"}}


def export_csv(catalog: dict) -> str:
    validate_catalog(catalog)
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in catalog["items"]:
        writer.writerow({"id": item["id"], "source_text": item["source_text"], "translation": item.get("translation") or "", "has_translation": "0" if item.get("translation") is None else "1", "metadata_json": json.dumps(_csv_metadata(item), ensure_ascii=False, sort_keys=True, separators=(",", ":"))})
    return out.getvalue()


def import_csv(catalog: dict, content: str) -> dict:
    validate_catalog(catalog)
    if len(content.encode("utf-8")) > CATALOG_MAX_BYTES:
        raise KhcomError("catalog_budget", "CSV excede o orçamento de edição.", maximum=CATALOG_MAX_BYTES)
    reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
    expected = {item["id"]: item for item in catalog["items"]}
    rows: dict[str, dict] = {}
    try:
        if reader.fieldnames != CSV_FIELDS:
            raise KhcomError("csv_columns", "Colunas CSV diferentes do contrato.", expected=CSV_FIELDS, actual=reader.fieldnames)
        for row in reader:
            identity = row.get("id")
            if None in row or any(value is None for value in row.values()):
                raise KhcomError("csv_row", "Linha CSV com campos ausentes ou extras.", row=reader.line_num)
            if identity not in expected or identity in rows:
                raise KhcomError("csv_identity", "ID CSV desconhecido ou duplicado.", id=identity)
            original = expected[identity]
            if row["source_text"] != original["source_text"] or json.loads(row["metadata_json"]) != _csv_metadata(original):
                raise KhcomError("csv_provenance", "Texto/metadados de origem não podem ser alterados no CSV.", id=identity)
            if row["has_translation"] not in {"0", "1"} or (row["has_translation"] == "0" and row["translation"]):
                raise KhcomError("csv_translation_flag", "Use has_translation=1 ao preencher uma tradução.", id=identity)
            item = copy.deepcopy(original)
            entered = row["translation"] if row["has_translation"] == "1" else None
            normalized = unicodedata.normalize("NFC", entered) if entered is not None else None
            if normalized != original.get("translation") or entered != normalized:
                item.update(translation=normalized, translation_input=entered, status="draft" if entered is not None else "untranslated", reviewer=None, evidence_refs=[])
            rows[identity] = item
    except (ValueError, csv.Error, RecursionError) as error:
        raise KhcomError("csv_parse", "CSV ou metadados JSON inválidos.", reason=str(error)) from error
    if set(rows) != set(expected):
        raise KhcomError("csv_membership", "CSV não contém todos os IDs do catálogo.", missing=sorted(set(expected) - set(rows)))
    result = copy.deepcopy(catalog)
    result["items"] = [rows[item["id"]] for item in catalog["items"]]
    return result


def export_tables(parser: Any = None) -> dict[str, str]:
    parser = parser or load_textgen()
    result = {}
    for name, encoding in parser.load_charmap("us").items():
        mappings = {value: "{" + tag + "}" for tag, value in encoding.controls.items()}
        mappings.update({encoding.pack([unit]): char for unit, char in encoding.chars.items()})
        # CP932 is variable length despite width=1; enumerate at most 65,792
        # candidates, retaining only the codec owner's canonical round-trip.
        if encoding.width == 2:
            candidates = (bytes([number]) for number in range(256))
        else:
            candidates = (number.to_bytes(size, "big") for size in (1, 2) for number in range(256 ** size))
        for candidate in candidates:
            char = encoding.codec_char(candidate)
            if char is not None:
                encoded = encoding.char(char, name)
                mappings.setdefault(encoded, char)
        lines = ["; Gerada de khcom " + COMMIT, "; Chaves são sequências de bytes em ordem de arquivo, não valores u16.", "; Controles são tokens; esta tabela não comprova glifos nem largura visual."]
        for payload, display in sorted(mappings.items()):
            if "\n" in display or "\r" in display:
                continue
            lines.append(payload.hex().upper() + "=" + display)
        result[name + "-us.tbl"] = "\n".join(lines) + "\n"
    return result


def write_private(path: Path, data: bytes) -> None:
    """Publish a new private output atomically, never replace existing data."""
    resolved = path.resolve()
    private = PROJECT_ROOT / "private"
    if not resolved.is_relative_to(private):
        raise KhcomError("private_output_required", "Catálogos e derivados devem ficar em private/ (ignorada).", path=str(path))
    write_new(resolved, data)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sanitized_summary(catalog: dict) -> dict:
    return {"origin": catalog["origin"], "upstream": catalog["upstream"], "coverage": catalog["coverage"], "pools": catalog["pools"], "codecs": dict(Counter(item["codec_id"] for item in catalog["items"])), "items_with_opaque_codes": sum(bool(item["opaque_codes"]) for item in catalog["items"])}
