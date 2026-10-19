"""Bounded US staff-roll font profile, reconstructed from the user's ROM.

The original catalog and CP932 codec remain unchanged. This profile accepts
the original US alphabet plus Portuguese accents; it is not a general SJIS
replacement, text reinserter, or claim of complete consumer coverage.
"""

from __future__ import annotations

import unicodedata

from .credits import audit_credits, parse_line, read_credit_tables, CreditTables
from .credits_font import REQUIRED, generate_accent
from .errors import KhcomError
from .graphics import rom_slice
from .rom import identify_bytes
from .text import ROM_BASE, extract_catalog
from .upstream import COMMIT, SNAPSHOT, load_assetgen, sha256

PROFILE_ID = "staff-roll-ptbr-v1"
DOMAIN = "staff_roll_script_text"
FIRST_INDEX = 210
FIRST_CODE = 0x82A0
END_INDEX = FIRST_INDEX + len(REQUIRED)

# These are encoding facts, not original game text or bitmap data. The two
# wide punctuation characters occur in the US inventory and must be retained.
MAPPINGS = {chr(code): bytes([code]) for code in range(0x20, 0x7F)}
MAPPINGS.update({"”": b"\x81\x68", "＠": b"\x81\x97"})
MAPPINGS.update({char: (FIRST_CODE + i).to_bytes(2, "big")
                 for i, char in enumerate(REQUIRED)})
DECODE = {payload: char for char, payload in MAPPINGS.items()}
MAX_LINE_BYTES = 128 * 1024  # Same editorial resource bound as parse_line.


def encode_line(text: str) -> bytes:
    """Encode a plain NFC line and append NUL; no inline {END} token syntax."""
    if not isinstance(text, str) or len(text) >= MAX_LINE_BYTES:
        raise KhcomError("credits_profile_text", "Linha fora do contrato editorial.")
    if unicodedata.normalize("NFC", text) != text:
        raise KhcomError("credits_profile_nfc", "Normalize a edição em NFC preservando a entrada original.")
    result = bytearray()
    for offset, character in enumerate(text):
        payload = MAPPINGS.get(character)
        if payload is None:
            raise KhcomError("credits_profile_character", "Caractere fora do perfil de créditos US/PT-BR.",
                             character=character, offset=offset)
        result.extend(payload)
    if len(result) >= MAX_LINE_BYTES:
        raise KhcomError("credits_profile_text", "Linha excede o orçamento codificado.")
    return bytes(result) + b"\0"


def decode_line(raw: bytes) -> str:
    """Decode one terminated profile line without silently falling back to CP932."""
    if (not isinstance(raw, bytes) or not raw or len(raw) > MAX_LINE_BYTES
            or raw[-1] != 0 or 0 in raw[:-1]):
        raise KhcomError("credits_profile_line", "Linha requer um único NUL final.")
    result = []
    cursor = 0
    while cursor < len(raw) - 1:
        size = 2 if raw[cursor] & 0x80 else 1
        payload = raw[cursor:cursor + size]
        character = DECODE.get(payload)
        if character is None:
            raise KhcomError("credits_profile_code", "Código fora do perfil de créditos US/PT-BR.",
                             offset=cursor, bytes_hex=payload.hex())
        result.append(character)
        cursor += size
    return "".join(result)


def export_table() -> str:
    lines = [f"; Perfil {PROFILE_ID}; somente {DOMAIN} com as fontes reconstruídas.",
             "; Ordem de bytes em arquivo. Não substitui a tabela CP932 da origem.",
             "; {END} nesta tabela representa NUL; a API recebe texto sem esse token.",
             "00={END}"]
    lines.extend(payload.hex().upper() + "=" + char
                 for payload, char in sorted(DECODE.items()))
    return "\n".join(lines) + "\n"


def build_profile(data: bytes, *, fetch: bool = False) -> tuple[bytes, dict, dict[str, bytes]]:
    """Rebuild only the four proven font regions; never edit script text here."""
    identity = identify_bytes(data)
    owner = load_assetgen(fetch=fetch)
    tables, records, addresses = read_credit_tables(data, owner)
    audit = audit_credits(data)
    used = {index for font in audit["glyph_usage"]
            for index in font["indices_observed_in_this_script"]}
    if used.intersection(range(FIRST_INDEX, END_INDEX)):
        raise KhcomError("credits_profile_usage", "O roteiro original usa um índice reservado pelo perfil.")
    for i in range(len(REQUIRED)):
        if tables.glyph(FIRST_CODE + i) != FIRST_INDEX + i:
            raise KhcomError("credits_profile_mapping", "O mapa da origem diverge do perfil fixado.")

    # Every original US item must retain its exact encoding, including wide
    # punctuation and commands. No unknown character becomes a replacement box.
    catalog = extract_catalog(data)
    original_items = [item for item in catalog["items"] if item["domain"] == DOMAIN]
    if len(original_items) != 255:
        raise KhcomError("credits_profile_inventory", "Inventário de créditos diverge da revisão verificada.")
    for item in original_items:
        span = item["source_span"]
        original = data[span["start"]:span["end"]]
        if encode_line(decode_line(original)) != original:
            raise KhcomError("credits_profile_roundtrip", "Perfil alteraria um texto original.", id=item["id"])

    manifest = owner.Manifest(SNAPSHOT / "config/assets/staff_roll_font.yaml")
    candidate = bytearray(data)
    fonts, spans, files, widths = [], [], {}, []
    for font, height in ((0, 16), (1, 8)):
        name = f"gStaffRollFont{font}Glyphs"
        entry = manifest.by_name[name]
        source = rom_slice(data, addresses[name], manifest.size(entry, "us"))
        png = owner.glyphs_to_png(entry, source)
        width, atlas_height, original_pixels = owner.sprite_sheet.read_png(png)
        if width != 128 or len(source) != len(tables.widths[font]) * height * 2:
            raise KhcomError("credits_profile_geometry", "Geometria das fontes diverge do perfil fixado.")
        pixels = bytearray(original_pixels)
        advances = bytearray(tables.widths[font])
        glyphs = []
        for i, character in enumerate(REQUIRED):
            base = unicodedata.normalize("NFD", character)[0]
            base_index = tables.glyph(tables.single_byte_map[ord(base)])
            x, y = base_index % 16 * 8, base_index // 16 * height
            base_rows = [original_pixels[(y + row) * width + x:(y + row) * width + x + 8]
                         for row in range(height)]
            generated = generate_accent(character, base_rows, tables.widths[font][base_index])
            index = FIRST_INDEX + i
            tx, ty = index % 16 * 8, index // 16 * height
            for row, values in enumerate(generated["rows"]):
                pixels[(ty + row) * width + tx:(ty + row) * width + tx + 8] = values
            advances[index] = generated["advance"]
            glyphs.append({"character": character, "index": index, "code_hex": f"{FIRST_CODE + i:04X}",
                           "base_index": base_index, "base_sha256": sha256(b"".join(base_rows)),
                           "pixels_sha256": sha256(b"".join(generated["rows"])),
                           "advance": generated["advance"], "recipe": generated["metadata"]})
        if len({glyph["pixels_sha256"] for glyph in glyphs}) != len(REQUIRED):
            raise KhcomError("credits_profile_distinct", "Acentos resultaram em matrizes duplicadas.")
        output_png = owner.sprite_sheet.write_png(width, atlas_height, pixels, owner.GLYPH_GREYS[2])
        encoded = owner.png_to_glyphs(entry, output_png, len(source))
        unit = height * 2
        start, end = FIRST_INDEX * unit, END_INDEX * unit
        if encoded[:start] != source[:start] or encoded[end:] != source[end:]:
            raise KhcomError("credits_profile_extent", "Receita alterou glifos fora do perfil.")
        for resource, before, after, begin, finish in (
                (name, source, encoded, start, end),
                (f"gStaffRollFont{font}Widths", tables.widths[font], bytes(advances), FIRST_INDEX, END_INDEX)):
            offset = addresses[resource] - ROM_BASE
            candidate[offset + begin:offset + finish] = after[begin:finish]
            spans.append({"resource": resource, "start": offset + begin, "end": offset + finish,
                          "source_sha256": sha256(before[begin:finish]),
                          "target_sha256": sha256(after[begin:finish]),
                          "changed_bytes": sum(a != b for a, b in zip(before[begin:finish], after[begin:finish]))})
        files[f"font{font}.png"] = output_png
        widths.append(bytes(advances))
        fonts.append({"font": font, "cell": [8, height], "glyphs": glyphs})

    result = bytes(candidate)
    cursor = 0
    for span in sorted(spans, key=lambda value: value["start"]):
        if span["start"] < cursor or data[cursor:span["start"]] != result[cursor:span["start"]]:
            raise KhcomError("credits_profile_extent", "Regiões sobrepostas ou bytes externos modificados.")
        cursor = span["end"]
    if len(result) != len(data) or result[cursor:] != data[cursor:]:
        raise KhcomError("credits_profile_extent", "Receita modificou o tamanho ou a cauda da ROM.")
    candidate_tables = CreditTables(tables.pages_and_codes, tables.single_byte_map, tuple(widths))
    font_state = 0
    for row in audit["rows"]:
        item = next(item for item in original_items if item["id"] == row["id"])
        span = item["source_span"]
        parsed = parse_line(result[span["start"]:span["end"]], font_state, candidate_tables)
        font_state = parsed["font_after"]
        if parsed["runs"] != row["runs"] or parsed["commands"] != row["commands"]:
            raise KhcomError("credits_profile_baseline", "As métricas/comandos da origem mudaram.", row=row["row"])
    report = {"schema_version": 1, "operation": "prepare_credits_profile", "profile_id": PROFILE_ID,
              "domain": DOMAIN, "upstream_commit": COMMIT, "origin": identity,
              "source_sha256": sha256(data), "target_sha256": sha256(result),
              "allowed_spans": spans, "allowed_bytes": sum(s["end"] - s["start"] for s in spans),
              "changed_bytes": sum(s["changed_bytes"] for s in spans),
              "outside_spans_unchanged": True, "original_items_roundtripped": len(original_items),
              "script_rows_with_unchanged_metrics": len(audit["rows"]), "fonts": fonts,
              "table_records": {name: sha256(raw) for name, raw in records.items()},
              "runtime_verified": False, "typography_approved": False, "release_approved": False,
              "limitations": ["Font-only candidate: no game text is translated by this operation.",
                              "Slot reuse is limited to the verified US script and documented consumer investigation.",
                              "The generic CP932 catalog and reinsertion gates remain unchanged.",
                              "Outputs contain user-ROM derivatives; source staging excludes them.",
                              "New text still requires command, byte, pixel, reference and runtime checks."]}
    files[PROFILE_ID + ".tbl"] = export_table().encode("utf-8")
    return result, report, files
