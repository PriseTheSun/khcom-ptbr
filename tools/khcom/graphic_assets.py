"""Lossless private extraction of the graphics declared by pinned manifests.

Screen composition, reachability and text coverage remain separate questions.
No upstream build/extraction entry point or external converter is executed.
"""
from collections import Counter
from pathlib import Path
import struct

from .assets import inspect_asset_layouts
from .errors import KhcomError
from .graphics import rom_slice
from .rom import identify_bytes
from .text import ROM_BASE, json_bytes, write_private
from .upstream import COMMIT, SNAPSHOT, load_asset_manifests, sha256

GRAPHIC_FORMATS = frozenset({"sprite_sheet", "glyphs", "tiles4", "tiles8", "palette", "tilemap"})


def tile_atlas(raw: bytes, depth: int, columns: int, sheet, palette: bytes) -> bytes:
    unit = 8 * depth
    if depth not in (4, 8) or not raw or len(raw) % unit or type(columns) is not int or columns < 1:
        raise KhcomError("tile_geometry", "Bloco não contém tiles completos de 8x8.")
    count = len(raw) // unit
    if count % columns:
        raise KhcomError("tile_geometry", "Largura do atlas não divide a quantidade de tiles.")
    width, height = columns * 8, count // columns * 8
    if depth == 4:
        rows = sheet.tile_rows(raw, 0, width, height)
    else:
        rows = [bytearray(width) for _ in range(height)]
        for tile in range(count):
            x, y = tile % columns * 8, tile // columns * 8
            for row in range(8):
                rows[y + row][x:x + 8] = raw[tile * 64 + row * 8:tile * 64 + row * 8 + 8]
    return sheet.write_png(width, height, b"".join(rows), sheet.sheet_palette(palette, 1 << depth))


def atlas_tiles(png: bytes, depth: int, sheet) -> bytes:
    width, height, pixels = sheet.read_png(png)
    if depth not in (4, 8) or width % 8 or height % 8 or any(value >= 1 << depth for value in pixels):
        raise KhcomError("tile_geometry", "Atlas excede o formato de tiles selecionado.")
    rows = [pixels[y * width:(y + 1) * width] for y in range(height)]
    if depth == 4:
        return sheet.rows_tiles(rows, width, height)
    return b"".join(rows[y + dy][x:x + 8] for y in range(0, height, 8)
                    for x in range(0, width, 8) for dy in range(8))


def decode_graphic(data: bytes, manifest, entry: dict, owner, lookup: dict,
                   palette_entries: frozenset = frozenset()) -> tuple[dict, dict[str, bytes]]:
    """Use parsed manifest identities; preserve original palette words and OAM."""
    storage_format = entry["format"]
    kind = "palette" if storage_format == "raw" and entry["name"] in palette_entries else storage_format
    start, size = entry["us"]["address"], manifest.size(entry, "us")
    raw = rom_slice(data, start, size)
    report = {"entry_name": entry["name"], "format": storage_format, "interpreted_as": kind, "start": start - ROM_BASE,
              "size": size, "sha256": sha256(raw), "compression": entry["us"].get("compress"),
              "roundtrip_equal": False, "runtime_verified": False,
              "screen_composition_verified": False, "palette_entry": entry.get("palette"),
              "borrowed_tiles_entry": entry.get("tiles"), "borrowed_tiles_offset": entry.get("tiles_offset", 0)}
    files = {"original.bin": raw}
    if report["compression"]:
        report["status"] = "compressed_original_retained_codec_not_implemented"
        return report, files
    palette = b""
    if entry.get("palette"):
        name = entry["palette"]
        if name not in lookup or "us" not in lookup[name].by_name[name]:
            raise KhcomError("graphic_palette", "Paleta US não resolvida.", entry_name=name)
        pm, pe = lookup[name], lookup[name].by_name[name]
        if pe.get("format") not in ("palette", "raw") or pe["us"].get("compress"):
            raise KhcomError("graphic_palette", "Formato de paleta ainda não interpretado.", entry_name=name)
        palette = rom_slice(data, pe["us"]["address"], pm.size(pe, "us"))
        if len(palette) % 2:
            raise KhcomError("graphic_palette", "Paleta referenciada não contém palavras u16 completas.")
        report["palette_sha256"] = sha256(palette)
        report["palette_interpretation"] = "explicit_palette_reference_in_pinned_manifest"
    report["preview_palette"] = "manifest_palette_with_diagnostic_fallback" if palette else "diagnostic_grayscale"
    try:
        if kind == "sprite_sheet":
            borrowed = None
            if entry.get("tiles"):
                lender, target = owner.lender(lookup, entry, "us")
                borrowed = rom_slice(data, target["us"]["address"], lender.size(target, "us"))
                if target["us"].get("compress"):
                    raise KhcomError("graphic_lender", "Tiles compartilhados comprimidos exigem decoder próprio.")
                if target["format"] == "sprite_sheet":
                    borrowed = owner.sprite_sheet.parse_records(borrowed, len(lender.frames(target, "us")), len(lender.animations(target, "us")))[2]
                borrowed = borrowed[entry.get("tiles_offset", 0):]
                report["borrowed_tiles_sha256"] = sha256(borrowed)
            decoded = owner.decode_sheet(manifest, entry, "us", raw, palette, borrowed)
            # decode_sheet re-encodes the PNG layers, OAM and animations and
            # rejects any byte difference, including borrowed/shared tile use.
            layout = manifest.sheet(entry, "us")
            layer_count = owner.sprite_sheet.layer_count(layout)
            png_layers = []
            for index, png in enumerate(decoded.values()):
                name = "main.png" if index == 0 else "extra-layers.png"
                files[name] = png
                width, height, _pixels = owner.sprite_sheet.read_png(png)
                stacked = 1 if index == 0 else layer_count - 1
                if not stacked or height % stacked:
                    raise KhcomError("graphic_layers", "Altura das camadas não corresponde ao layout.")
                png_layers.append({"file": name, "first_layer": index, "stacked_layers": stacked,
                                   "width": width, "height_per_layer": height // stacked,
                                   "stacking": "vertical"})
            oam, animations, tiles = owner.sprite_sheet.parse_records(raw, len(manifest.frames(entry, "us")), len(manifest.animations(entry, "us")))
            report.update(frames=oam, animations=animations, layout=layout,
                          layer_count=layer_count, png_layers=png_layers,
                          tile_payload_size=len(tiles), tile_payload_sha256=sha256(tiles))
        elif kind == "glyphs":
            png = owner.glyphs_to_png(entry, raw)
            if owner.png_to_glyphs(entry, png, size) != raw:
                raise KhcomError("graphic_roundtrip", "Glifos não reconstituem os bytes originais.")
            files["glyphs.png"] = png
            report.update(glyph=entry["glyph"], bpp=entry["bpp"], columns=entry["columns"])
        elif kind in ("tiles4", "tiles8"):
            depth = int(kind[-1]); columns = entry.get("width", 1)
            png = tile_atlas(raw, depth, columns, owner.sprite_sheet, palette)
            if atlas_tiles(png, depth, owner.sprite_sheet) != raw:
                raise KhcomError("graphic_roundtrip", "Atlas não reconstitui os bytes originais.")
            files["tiles.png"] = png
            report.update(bpp=depth, columns=columns, tile_count=len(raw) // (depth * 8))
        elif kind in ("palette", "tilemap"):
            if len(raw) % 2:
                raise KhcomError("graphic_words", "Recurso não contém palavras u16 completas.")
            words = [value[0] for value in struct.iter_unpack("<H", raw)]
            if struct.pack(f"<{len(words)}H", *words) != raw:
                raise KhcomError("graphic_roundtrip", "Palavras do recurso divergem dos bytes.")
            # Preserve all 16 bits. A tilemap has no inferred width/mode/bank;
            # a palette's high bit is retained, even though RGB ignores it.
            files["words.json"] = json_bytes({"byte_order": "little", "words_u16": words})
            report["word_count"] = len(words)
            if kind == "tilemap":
                report["screen_mode"] = None
            else:
                files["palette-preview.json"] = json_bytes({"rgb": [owner.gba_to_rgb(value) for value in words], "word_high_bits_retained_in": "words.json"})
        else:
            raise KhcomError("graphic_format", "Formato gráfico não implementado.", format=kind)
    except (owner.ManifestError, owner.sprite_sheet.SheetError) as error:
        raise KhcomError("graphic_decode", "Reconstrução gráfica diverge do recurso.", entry_name=entry["name"], reason=str(error)) from error
    report.update(status="decoded_and_reencoded_exactly", roundtrip_equal=True)
    report["files"] = {name: {"size": len(content), "sha256": sha256(content)} for name, content in files.items()}
    return report, files


def extract_known_graphics(data: bytes, destination: Path, *, fetch: bool = False, input_origin: dict | None = None) -> dict:
    identify_bytes(data)
    if destination.exists() or destination.is_symlink():
        raise KhcomError("output_exists", "Escolha uma nova pasta de saída.", path=str(destination))
    owner, manifests = load_asset_manifests(fetch=fetch)
    inventory = inspect_asset_layouts(data, manifests, owner, source_root=SNAPSHOT, commit=COMMIT)
    lookup = {entry["name"]: manifest for manifest in manifests for entry in manifest.entries if "us" in entry}
    palette_entries = frozenset(entry["palette"] for manifest in manifests for entry in manifest.entries
                                if "us" in entry and entry.get("palette"))
    results = []
    for manifest in manifests:
        for entry in manifest.entries:
            if "us" not in entry or not (entry.get("format") in GRAPHIC_FORMATS
                                         or entry.get("format") == "raw" and entry["name"] in palette_entries):
                continue
            report, files = decode_graphic(data, manifest, entry, owner, lookup, palette_entries)
            relative = Path(manifest.group) / entry["name"]
            if relative.is_absolute() or ".." in relative.parts:
                raise KhcomError("graphic_path", "Identidade de recurso não forma caminho relativo.")
            for name, content in files.items():
                write_private(destination / relative / name, content)
            write_private(destination / relative / "resource.json", json_bytes(report))
            results.append({"id": f"us/asset/{manifest.group}/{entry['name']}", "report": (relative / "resource.json").as_posix(),
                            "format": report["format"], "interpreted_as": report["interpreted_as"], "size": report["size"], "status": report["status"],
                            "roundtrip_equal": report["roundtrip_equal"]})
    report = {"schema_version": 1, "source_sha256": sha256(data), "commit": COMMIT, "input": input_origin,
              "manifests_examined": inventory["manifest_count"], "resources": results,
              "counts_by_format": dict(Counter(item["format"] for item in results)),
              "exact_roundtrips": sum(item["roundtrip_equal"] for item in results),
              "complete_graphics_inventory": False, "runtime_verified": False,
              "limitations": ["Only graphics declared in the pinned manifests are selected; unknown ROM regions and video are not covered.",
                              "Tilemap u16 words preserve all attributes, without claiming screen mode or composition.",
                              "Preview palettes can use diagnostic fallback; in-game palette states require separate verification.",
                              "No text-in-image identification, translation, shared-consumer runtime QA or distribution approval is implied."]}
    write_private(destination / "report.json", json_bytes(report))
    return report
