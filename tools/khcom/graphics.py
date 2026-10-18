"""Selected font proof, using the pinned upstream parser and PNG codec.

This extracts only reviewed uncompressed font assets. It does not edit graphics,
claim original palette colours, approve translations or execute game code.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct

from .errors import KhcomError
from .io import read_file
from .text import ROM_BASE
from .upstream import COMMIT, PROJECT_ROOT, SNAPSHOT, load_assetgen, sha256, upstream_rom_identity


def rom_slice(data: bytes, address: int, size: int) -> bytes:
    offset = address - ROM_BASE
    if size < 0 or offset < 0 or offset + size > len(data):
        raise KhcomError("graphics_range", "Recurso gráfico fora da ROM.", address=address, size=size)
    return data[offset:offset + size]


def latin_widths(source: str) -> list[int]:
    """Read the one literal table and its explicit US preprocessor branch."""
    match = re.search(r"static const GlyphWidthTable sLatinGlyphWidths = \{\s*\{(.*?)\}\s*,?\s*\};", source, re.S)
    if not match:
        raise KhcomError("metrics_source", "Tabela latina não encontrada na fonte fixada.")
    selected = re.sub(r"#ifdef VERSION_EU\s*.*?#else\s*(.*?)#endif", r"\1", match.group(1), flags=re.S)
    if re.sub(r"[\d\s,]", "", selected):
        raise KhcomError("metrics_source", "Tabela latina deixou de ser o literal revisado.")
    numbers = [int(number) for number in re.findall(r"\b\d+\b", selected)]
    if len(numbers) != 256 or any(number > 65535 for number in numbers):
        raise KhcomError("metrics_source", "Tabela latina deve conter 256 larguras u16.")
    return numbers


def match_metrics(data: bytes, widths: list[int]) -> dict:
    # include/evt/msg_types.h defines GlyphWidthTable.widths as u16[256].
    raw = struct.pack("<256H", *widths)
    first = data.find(raw)
    if first < 0 or data.find(raw, first + 1) >= 0:
        raise KhcomError("metrics_identity", "Larguras da fonte não têm correspondência única na ROM.")
    return {"source": "src/msg/msg.c:sLatinGlyphWidths", "type_source": "include/evt/msg_types.h:GlyphWidthTable", "address": f"0x{ROM_BASE + first:08X}", "size": len(raw), "sha256": sha256(raw), "values": widths, "verification": "unique_exact_byte_match_to_pinned_source_u16le", "runtime_verified": False}


def verify_frame_pointers(data: bytes, manifest, entry: dict, table_name: str, frames: list) -> dict:
    table = manifest.by_name[table_name]
    expected_symbols = [frame["symbol"] for frame in manifest.frames(entry, "us")]
    if manifest.data(table, "us", "items") != expected_symbols:
        raise KhcomError("font_pointer_schema", "Tabela de frames não acompanha a ordem do atlas.", symbol=entry["name"])
    addresses = []
    address = entry["us"]["address"]
    for frame in frames:
        addresses.append(address)
        address += 2 + 6 * len(frame) + (2 if frame else 0)
    expected = struct.pack(f"<{len(addresses)}I", *addresses)
    observed = rom_slice(data, table["us"]["address"], len(expected))
    if observed != expected:
        raise KhcomError("font_pointer_mismatch", "Ponteiros de frames divergem do payload verificado.", symbol=table_name)
    return {"symbol": table_name, "address": f"0x{table['us']['address']:08X}", "count": len(addresses), "sha256": sha256(expected), "verified": True}


def inspect_font(data: bytes, spec: dict, assetgen, manifest) -> tuple[dict, bytes]:
    entry = manifest.by_name[spec["symbol"]]
    address, size = entry["us"]["address"], manifest.size(entry, "us")
    raw = rom_slice(data, address, size)
    if entry.get("compression") or entry.get("tiles"):
        raise KhcomError("font_format", "O spike aceita somente fontes próprias sem compressão.", symbol=entry["name"])
    report = {**spec, "manifest_resource_address": f"0x{address:08X}", "size": size, "sha256": sha256(raw), "format": entry["format"], "palette": "diagnostic_grayscale_not_original_colours", "runtime_verified": False}
    try:
        if entry["format"] == "sprite_sheet":
            files = assetgen.decode_sheet(manifest, entry, "us", raw, b"")
            payloads = list(files.values())
            if len(payloads) != 1:
                raise KhcomError("font_layers", "Fonte selecionada tem camadas não previstas.")
            png = payloads[0]
            frames, _anims, tiles = assetgen.sprite_sheet.parse_records(raw, len(manifest.frames(entry, "us")), len(manifest.animations(entry, "us")))
            report["tile_payload_address"] = f"0x{address + len(raw) - len(tiles):08X}"
            report["tile_payload_size"] = len(tiles)
            report.update(glyph_count=len(frames), cell=list(entry["cell"]), columns=entry["columns"], roundtrip_equal=True)
            report["frame_pointer_table"] = verify_frame_pointers(data, manifest, entry, spec["pointer_table"], frames)
        elif entry["format"] == "glyphs":
            report["glyph_payload_address"] = f"0x{address:08X}"
            png = assetgen.glyphs_to_png(entry, raw)
            if assetgen.png_to_glyphs(entry, png, size) != raw:
                raise KhcomError("font_roundtrip", "PNG de glifos não reconstitui os bytes originais.")
            geometry = assetgen.glyph_geometry(entry, size)
            report.update(glyph_count=geometry[4], cell=list(entry["glyph"]), columns=entry["columns"], bpp=entry["bpp"], roundtrip_equal=True)
            widths_entry = manifest.by_name[spec["widths"]]
            widths = bytes(manifest.values(widths_entry, "us"))
            if rom_slice(data, widths_entry["us"]["address"], len(widths)) != widths or len(widths) != geometry[4]:
                raise KhcomError("font_widths", "Larguras dos créditos divergem dos bytes/quantidade de glifos.")
            report["metrics"] = {"address": f"0x{widths_entry['us']['address']:08X}", "sha256": sha256(widths), "values": list(widths), "verified": True}
        else:
            raise KhcomError("font_format", "Formato não implementado neste spike.", format=entry["format"])
        width, height, pixels = assetgen.sprite_sheet.read_png(png)
        cell_w, cell_h = report["cell"]
        report["glyphs"] = []
        for index in range(report["glyph_count"]):
            x, y = index % report["columns"] * cell_w, index // report["columns"] * cell_h
            rows = [pixels[(y + row) * width + x:(y + row) * width + x + cell_w] for row in range(cell_h)]
            occupied = [(cx, cy) for cy, row in enumerate(rows) for cx, value in enumerate(row) if value]
            bbox = None if not occupied else [min(x for x, y in occupied), min(y for x, y in occupied), max(x for x, y in occupied) + 1, max(y for x, y in occupied) + 1]
            report["glyphs"].append({"index": index, "nonzero_pixels": len(occupied), "bounds": bbox, "pixel_sha256": sha256(b"".join(rows))})
        report["atlas"] = {"width": width, "height": height, "sha256": sha256(png)}
        return report, png
    except (assetgen.ManifestError, assetgen.sprite_sheet.SheetError) as error:
        raise KhcomError("font_format_mismatch", "Parser fixado não confirmou a fonte da ROM.", symbol=entry["name"], reason=str(error)) from error


def accent_preview(png: bytes, characters: str, sprite_sheet) -> bytes:
    """Diagnostic nearest-neighbour view; index order is recorded in report."""
    width, _height, pixels = sprite_sheet.read_png(png)
    cell, columns, scale = 16, 12, 4
    out_width = columns * cell * scale
    out_height = ((len(characters) + columns - 1) // columns) * cell * scale
    result = bytearray(out_width * out_height)
    source_columns = width // cell
    for position, char in enumerate(characters):
        index = ord(char)
        sx, sy = index % source_columns * cell, index // source_columns * cell
        dx, dy = position % columns * cell * scale, position // columns * cell * scale
        for y in range(cell):
            row = b"".join(bytes([value]) * scale for value in pixels[(sy + y) * width + sx:(sy + y) * width + sx + cell])
            for repeat in range(scale):
                offset = (dy + y * scale + repeat) * out_width + dx
                result[offset:offset + len(row)] = row
    palette = [(0, 0, 0), (30, 30, 30), (255, 255, 255)] + [(n * 17,) * 3 for n in range(3, 16)]
    return sprite_sheet.write_png(out_width, out_height, result, palette)


def extract_fonts(data: bytes, *, fetch: bool = False) -> tuple[dict, dict[str, bytes]]:
    assetgen = load_assetgen(fetch=fetch)
    declared = upstream_rom_identity()
    if hashlib.sha1(data).hexdigest() != declared["sha1"]:
        raise KhcomError("upstream_rom_mismatch", "Fontes requerem a revisão US fixada.")
    spec = json.loads(read_file(PROJECT_ROOT / "manifests/fonts.json", 65536).decode("utf-8"))
    if spec.get("format_version") != 1 or spec.get("commit") != COMMIT:
        raise KhcomError("font_manifest", "Manifesto de fontes incompatível.")
    metrics = match_metrics(data, latin_widths((SNAPSHOT / "src/msg/msg.c").read_text()))
    manifests = {}
    fonts, files = [], {}
    for selected in spec["fonts"]:
        name = selected["manifest"]
        if name not in manifests:
            manifests[name] = assetgen.Manifest(SNAPSHOT / "config/assets" / name)
        report, png = inspect_font(data, selected, assetgen, manifests[name])
        report["required_characters"] = []
        for char in spec["required_characters"]:
            if selected["mapping"] == "latin_codepoint_index":
                index = ord(char)
                glyph = report["glyphs"][index]
                state = {"character": char, "index": index, "advance_pixels": metrics["values"][index], "nonzero_pixels": glyph["nonzero_pixels"], "state": "glyph_bytes_present_visual_review_required"}
            elif selected["mapping"] == "EncodeSmallFontString":
                state = {"character": char, "state": "unmapped_in_source_renderer"}
            else:
                try:
                    char.encode("cp932")
                    state = {"character": char, "state": "mapping_and_visual_unknown"}
                except UnicodeEncodeError:
                    state = {"character": char, "state": "not_encodable_by_current_cp932_pipeline"} if selected["encoding"] == "sjis" else {"character": char, "state": "mapping_unknown"}
            report["required_characters"].append(state)
        fonts.append(report)
        files[f"{selected['id']}.png"] = png
        if selected["id"] == "message_latin":
            files["message_latin_accents_preview.png"] = accent_preview(png, spec["required_characters"], assetgen.sprite_sheet)
            report["accent_preview"] = {"file": "message_latin_accents_preview.png", "character_order": spec["required_characters"], "columns": 12, "scale": 4, "palette": "diagnostic_high_contrast"}
    return {"format_version": 1, "operation": "selected_font_extraction", "source_sha256": sha256(data), "commit": COMMIT, "complete_graphics_inventory": False, "latin_metrics": metrics, "fonts": fonts, "limitations": ["Five selected font resources only; not all image text or videos.", "PNG palettes are diagnostic grayscale, not in-game colour evidence.", "Byte and pointer-table matches do not establish rendering in every consumer.", "Accented glyph identity requires visual review; small and credits renderers require separate work."]}, files
