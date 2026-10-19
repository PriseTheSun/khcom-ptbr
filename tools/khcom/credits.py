"""Source-derived staff-roll semantics with ROM-verified tables and ordering.

This is a read-only audit. It does not certify unobserved renderers, select spare
glyphs, authorize relocation or replace the canonical text catalog's decoder.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import struct

from .errors import KhcomError
from .graphics import rom_slice
from .text import ROM_BASE, extract_catalog
from .upstream import COMMIT, SNAPSHOT, load_assetgen, read_source, sha256


@dataclass(frozen=True)
class CreditTables:
    pages_and_codes: bytes
    single_byte_map: tuple[int, ...]
    widths: tuple[bytes, bytes]

    def glyph(self, code: int) -> int:
        page = (code & 0x7F00) >> 6
        if page + 4 > len(self.pages_and_codes):
            raise KhcomError("credits_page", "Página de créditos fora da tabela.", glyph_code=code)
        offset, first = struct.unpack_from("<HH", self.pages_and_codes, page)
        if offset == 0xFFFF:
            raise KhcomError("credits_unmapped", "Código sem página de créditos.", glyph_code=code)
        cell = (offset + 0xFFC0 + (code & 0xFF)) & 0xFFFF
        if cell >= len(self.pages_and_codes):
            raise KhcomError("credits_page", "Código aponta além da tabela.", glyph_code=code)
        value = self.pages_and_codes[cell]
        if value == 0xFF:
            raise KhcomError("credits_unmapped", "Código sem glifo de créditos.", glyph_code=code)
        index = first + value
        if any(index >= len(widths) for widths in self.widths):
            raise KhcomError("credits_glyph", "Índice de glifo fora dos atlas.", glyph_code=code, index=index)
        return index

    def measure(self, raw: bytes, font: int) -> dict:
        if font not in (0, 1):
            raise KhcomError("credits_font", "Fonte de créditos deve ser 0 ou 1.")
        codes, indices = [], []
        cursor = 0
        while cursor < len(raw):
            first = raw[cursor]
            if first == 0:
                raise KhcomError("credits_nul", "NUL embutido no trecho de créditos.")
            if first & 0x80:
                if cursor + 1 >= len(raw) or raw[cursor + 1] == 0:
                    raise KhcomError("credits_truncated", "Código de dois bytes incompleto.", offset=cursor)
                code = first << 8 | raw[cursor + 1]
                cursor += 2
            else:
                code = self.single_byte_map[first]
                cursor += 1
            codes.append(code)
            indices.append(self.glyph(code))
        # The 256-cell queue uses equal read/write positions to mean empty.
        # Each draw drains before enqueue and after enqueue in sroll_tmr.c.
        if len(indices) >= 256:
            raise KhcomError("credits_queue", "Trecho excede os 255 glifos úteis da fila.")
        return {"bytes": len(raw), "codes": codes, "glyph_indices": indices,
                "advance_pixels": sum(self.widths[font][i] or 8 for i in indices)}


def parse_line(raw: bytes, font: int, tables: CreditTables) -> dict:
    """Parse one terminated script line, preserving commands and font state.

    Prefix parsing uses bytes, as StaffRollRunCredits does. Drawing bounds are
    a static advance check, not a claim that every glyph pixel was observed.
    """
    if not raw or len(raw) > 128 * 1024 or raw[-1] != 0 or 0 in raw[:-1]:
        raise KhcomError("credits_line", "Linha requer um único NUL final e limite editorial de 128 KiB.")
    original = raw
    raw = raw[:-1]
    cursor = 0
    commands = []
    color = "normal"
    while cursor < len(raw):
        token = raw[cursor:cursor + 1]
        if token == b"#":
            if raw[cursor + 1:cursor + 2] not in (b"0", b"1"):
                raise KhcomError("credits_font", "Comando # exige fonte 0 ou 1.", offset=cursor)
            font = raw[cursor + 1] - ord("0")
            commands.append({"offset": cursor, "command": "font", "value": font})
            cursor += 2
        elif token == b"@":
            color = "highlight"
            commands.append({"offset": cursor, "command": "color", "value": color})
            cursor += 1
        else:
            break
    token = raw[cursor:cursor + 1]
    body = raw[cursor:]
    result = {"font_after": font, "commands": commands, "runs": [],
              "source_bytes": len(original), "source_sha256": sha256(original),
              "runtime_verified": False}
    if token in (b"!", b"*", b"<", b"["):
        if token == b"*" and body[1:2] not in (b"D", b"S", b"J"):
            raise KhcomError("credits_logo", "Comando de logo desconhecido.")
        result.update(kind={b"!": "skip", b"*": "logo", b"<": "section_graphic", b"[": "section_end"}[token], opaque_tail_bytes=len(body) - 1)
        commands.append({"offset": cursor, "command": result["kind"], "value": chr(body[1]) if token == b"*" else None})
        return result

    def run(payload: bytes, x: int, tint: str, start: int, end: int, suffix: bytes = b"") -> dict:
        metrics = tables.measure(payload + suffix, font)
        right = x + metrics["advance_pixels"]
        return {**metrics, "source_span_in_line": [start, end], "generated_suffix_hex": suffix.hex(),
                "font": font, "color": tint, "x": x, "right": right,
                "within_visible_advance_window": x >= 16 and right <= 224,
                "within_tilemap_advance": 0 <= x <= right <= 240}

    if token == b"~":
        commands.append({"offset": cursor, "command": "columns"})
        body = body[1:]
        split = body.find(b"~")
        if split < 0:
            raise KhcomError("credits_separator", "Comando ~ sem separador de colunas.")
        left, right = body[:split], body[split + 1:]
        if len(left) > 76 or len(right) > 79:
            raise KhcomError("credits_buffer", "Coluna excede o buffer de 80 bytes.", left=len(left), right=len(right))
        # Match the producer's measurement of the full body, including any
        # later tildes, and then its subtraction of only the first delimiter.
        width = tables.measure(body, font)["advance_pixels"] - tables.measure(b"~", font)["advance_pixels"] + tables.measure(b" ", font)["advance_pixels"] * 3
        x = (240 - width) >> 1
        first = run(left, x, "highlight", cursor + 1, cursor + 1 + split, b"   ")
        second = run(right, first["right"], "normal", cursor + 2 + split, len(raw))
        result.update(kind="columns", runs=[first, second])
    else:
        align = {b"=": "center", b"-": "left", b"+": "right"}.get(token, "center")
        if token in (b"=", b"-", b"+"):
            commands.append({"offset": cursor, "command": "alignment", "value": align})
        start = cursor + (1 if token in (b"=", b"-", b"+") else 0)
        body = raw[start:]
        width = tables.measure(body, font)["advance_pixels"]
        x = 0 if align == "left" else 240 - width if align == "right" else (240 - width) >> 1
        result.update(kind="text", alignment=align, runs=[run(body, x, color, start, len(raw))])
    return result


def script_symbols(source: str) -> list[str | None]:
    """Accept only the reviewed literal US declaration, not arbitrary C."""
    match = re.search(r"#ifdef VERSION_US\s+static u8\* sStaffRollLines\[(\d+)\] = \{([^{}]*)\};", source)
    if not match:
        raise KhcomError("credits_script", "Declaração literal US dos créditos ausente.")
    parts = match.group(2).split(",")
    if parts[-1].strip():
        raise KhcomError("credits_script", "Forma não revisada do array de créditos.")
    names = [part.strip() for part in parts[:-1]]
    if len(names) != int(match.group(1)) or any(not re.fullmatch(r"gStaffRoll[A-Za-z0-9_]+|NULL", name) for name in names):
        raise KhcomError("credits_script", "Contagem/símbolos dos créditos divergentes.")
    if names[-1] != "NULL" or "NULL" in names[:-1]:
        raise KhcomError("credits_script", "Sentinel do roteiro não está no fim.")
    return [None if name == "NULL" else name for name in names]


def read_credit_tables(data: bytes, owner) -> tuple[CreditTables, dict, dict]:
    """Single owner of the ROM-verified staff-roll tables and their addresses."""
    manifest = owner.Manifest(SNAPSHOT / "config/assets/staff_roll_font.yaml")
    asset_addresses = {entry["name"]: entry["us"]["address"] for entry in manifest.entries if "us" in entry}
    records = {}
    try:
        for name in ("gStaffRollFontPages", "gStaffRollFontCodes", "gStaffRollFonts", "gStaffRollSingleByteCharMap", "gStaffRollFont0Widths", "gStaffRollFont1Widths"):
            entry = manifest.by_name[name]
            raw = rom_slice(data, asset_addresses[name], manifest.size(entry, "us"))
            # Reject unresolved pointer fields rather than check_record's
            # permitted partial check; these records have all owners present.
            for _off, _width, value in owner.record_chunks(manifest, entry, "us"):
                if isinstance(value, str) and value not in asset_addresses:
                    raise KhcomError("credits_reference", "Ponteiro de fonte não resolvido.", symbol=value)
            owner.check_record(manifest, entry, "us", raw, asset_addresses)
            records[name] = raw
    except owner.ManifestError as error:
        raise KhcomError("credits_tables", "Tabelas de créditos divergem do manifesto.", reason=str(error)) from error
    pages, codes = records["gStaffRollFontPages"], records["gStaffRollFontCodes"]
    if asset_addresses["gStaffRollFontPages"] + len(pages) != asset_addresses["gStaffRollFontCodes"]:
        raise KhcomError("credits_tables", "Páginas e códigos deixaram de ser adjacentes.")
    tables = CreditTables(pages + codes, struct.unpack("<256H", records["gStaffRollSingleByteCharMap"]), (records["gStaffRollFont0Widths"], records["gStaffRollFont1Widths"]))
    return tables, records, asset_addresses


def audit_credits(data: bytes, *, fetch: bool = False) -> dict:
    owner = load_assetgen(fetch=fetch)
    catalog = extract_catalog(data)
    items = {item["symbol"]: item for item in catalog["items"] if item["domain"] == "staff_roll_script_text"}
    source = read_source("src/sroll/mode_staffroll.c").decode("utf-8")
    symbols = script_symbols(source)
    addresses = {name: ROM_BASE + item["source_span"]["start"] for name, item in items.items()}
    try:
        pointers = struct.pack(f"<{len(symbols)}I", *(0 if name is None else addresses[name] for name in symbols))
    except KeyError as error:
        raise KhcomError("credits_symbol", "Roteiro referencia símbolo fora do catálogo.", symbol=str(error)) from error
    offset = data.find(pointers)
    if offset < 0 or data.find(pointers, offset + 1) >= 0:
        raise KhcomError("credits_order", "Array de ponteiros não tem correspondência única na ROM.")
    tables, records, asset_addresses = read_credit_tables(data, owner)
    rows, font = [], 0  # sStaffRollTextInit.font == 0 in the pinned source.
    used = [set(), set()]
    for row, name in enumerate(symbols[:-1]):
        item = items[name]
        span = item["source_span"]
        raw = data[span["start"]:span["end"]]
        parsed = parse_line(raw, font, tables)
        font = parsed["font_after"]
        for run in parsed["runs"]:
            used[font].update(run["glyph_indices"])
        rows.append({"row": row, "id": item["id"], "pointer_address": f"0x{ROM_BASE + offset + row * 4:08X}", **parsed})
    return {"format_version": 1, "operation": "credits_source_and_rom_audit", "commit": COMMIT,
            "source_sha256": sha256(data), "runtime_verified": False,
            "script_table": {"address": f"0x{ROM_BASE + offset:08X}", "entries": len(symbols), "size": len(pointers), "sha256": sha256(pointers), "verification": "unique_exact_pointer_array_match"},
            "tables": {name: {"address": f"0x{asset_addresses[name]:08X}", "size": len(raw), "sha256": sha256(raw)} for name, raw in records.items()},
            "rows": rows, "visible_advance_warnings": sum(not run["within_visible_advance_window"] for row in rows for run in row["runs"] if run["bytes"]),
            "catalog_items": len(items), "referenced_items": len(set(symbols) - {None}),
            "items_not_referenced_by_this_array": sorted(item["id"] for name, item in items.items() if name not in symbols),
            "glyph_usage": [{"font": font, "indices_observed_in_this_script": sorted(indices), "indices_not_observed_not_proven_free": sorted(set(range(len(tables.widths[font]))) - indices)} for font, indices in enumerate(used)],
            "limitations": ["Source-derived renderer model; no credits gameplay capture yet.", "Glyphs absent from this script are not proven reusable; other consumers and computed references remain unknown.", "Advance windows do not prove pixel bounds, queue timing, video timing or complete image-text coverage.", "CP932 catalog decoding does not authorize all CP932 codes in the game renderer.", "No ROM modification, new glyph mapping or translation release approval."]}
