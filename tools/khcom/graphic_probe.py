"""One source-only graphic recipe; outputs are private, unapproved candidates.

Pixels are authored here, never embedded from the commercial ROM. Existing
OAM, animation, palette and tile identities remain owned by the pinned parser.
"""
from .errors import KhcomError
from .graphic_assets import decode_graphic
from .graphics import rom_slice
from .rom import identify_bytes
from .text import ROM_BASE
from .upstream import COMMIT, load_asset_manifests, sha256


# Authored 5x7 bitmap capitals. These are recipe source, not extracted glyphs.
LETTERS = {
    "A": (14, 17, 17, 31, 17, 17, 17),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "N": (17, 25, 25, 21, 19, 19, 17),
    "C": (14, 17, 16, 16, 16, 17, 14),
    " ": (0,) * 7,
}
TITLE_TEXT = "APERTE INICIAR"


def replace_fixed_tiles(raw: bytes, layout: dict, animations: int, layers: list, sheet) -> tuple[bytes, dict]:
    """Replace pixels while retaining every original OAM/tile allocation.

    All uses of a shared tile must request identical bytes. Conflicts require
    a separate relocation decision; deduplication must not silently move OAM.
    The caller must establish ownership of the block and external consumers.
    """
    try:
        frames, anims, tiles = sheet.parse_records(raw, len(layout["frames"]), animations)
        sheet.decode(frames, tiles, layout)  # validates placement against ROM
        atlas = sheet.Sheet(layout)
        if len(layers) != sheet.layer_count(layout) or any(len(layer) != atlas.width * atlas.height for layer in layers):
            raise KhcomError("graphic_geometry", "Camadas não correspondem ao layout fixado.")
        claimed = {}
        candidate = bytearray(tiles)
        for index, (described, actual) in enumerate(zip(layout["frames"], frames)):
            for position, (piece, attributes) in enumerate(zip(described, actual)):
                found = sheet.piece_from_oam(attributes)
                rows = atlas.read(layers[piece["layer"]], index, piece)
                if any(value and value >> 4 != piece["pal"] for row in rows for value in row):
                    raise KhcomError("graphic_palette", "Pixels exigem um banco de paleta diferente.", frame=index, piece=position)
                indices = sheet.flipped([bytes(value & 15 for value in row) for row in rows], piece["hflip"], piece["vflip"])
                block = sheet.rows_tiles(indices, piece["w"], piece["h"])
                start = found["tile"] * 32
                if start + len(block) > len(tiles):
                    raise KhcomError("graphic_range", "Peça ultrapassa os tiles próprios.")
                for offset in range(0, len(block), 32):
                    tile = (start + offset) // 32
                    wanted = block[offset:offset + 32]
                    if tile in claimed and claimed[tile] != wanted:
                        raise KhcomError("graphic_shared_conflict", "Edições de um tile compartilhado divergem; realocação necessária.", tile=tile, frame=index, piece=position)
                    claimed[tile] = wanted
                    candidate[start + offset:start + offset + 32] = wanted
        _, observed = sheet.decode(frames, bytes(candidate), layout)
        if any(bytes(a) != bytes(b) for a, b in zip(layers, observed)):
            raise KhcomError("graphic_composition", "Pixels solicitados não correspondem à composição das peças.")
        records = raw[:len(raw) - len(tiles)]
        if sheet.record_bytes(frames, anims) != records:
            raise KhcomError("graphic_records", "Registros originais não foram reconstruídos.")
        result = records + bytes(candidate)
        return result, {"record_bytes_preserved": len(records), "tile_bytes": len(tiles),
                        "tiles_changed": sum(tiles[i:i + 32] != candidate[i:i + 32] for i in range(0, len(tiles), 32)),
                        "shared_tile_uses_consistent": True, "all_layers_redecoded_exactly": True,
                        "oam_animation_and_size_unchanged": True}
    except sheet.SheetError as error:
        raise KhcomError("graphic_fixed_layout", "Layout fixado não representa a edição.", reason=str(error)) from error


def build_title_probe(data: bytes, *, fetch: bool = False) -> tuple[bytes, dict]:
    identify_bytes(data)
    owner, manifests = load_asset_manifests(fetch=fetch)
    manifest = next(m for m in manifests if m.group == "sprites_title")
    entry = manifest.by_name["gTitlePressStartTiles"]
    lookup = {e["name"]: m for m in manifests for e in m.entries if "us" in e}
    borrowers = [e["name"] for m in manifests for e in m.entries if "us" in e and e.get("tiles") == entry["name"]]
    if borrowers or entry.get("tiles") or entry["us"].get("compress"):
        raise KhcomError("graphic_ownership", "O piloto exige tiles próprios, sem consumidores por empréstimo declarados.", borrowers=borrowers)
    original, files = decode_graphic(data, manifest, entry, owner, lookup)
    layout = manifest.sheet(entry, "us")
    if layout["cell"] != [240, 16] or layout["columns"] != 5 or len(layout["frames"]) != 5 or owner.sprite_sheet.layer_count(layout) != 1:
        raise KhcomError("graphic_probe_layout", "Layout de título diferente da receita revisada.")
    layers = owner.sprite_sheet.read_sheets(layout, files["main.png"], None)
    atlas = owner.sprite_sheet.Sheet(layout)
    for frame in range(5):
        # The first 16 columns hold the animated button; row 10 is its bar.
        # Only the letter region is replaced. Transparency remains index zero.
        x0 = frame * 240
        for y in range(8):
            layers[0][y * atlas.width + x0 + 20:y * atlas.width + x0 + 112] = bytes(92)
        for letter, char in enumerate(TITLE_TEXT):
            for y, bits in enumerate(LETTERS[char]):
                for x in range(5):
                    if bits & (1 << (4 - x)):
                        layers[0][y * atlas.width + x0 + 20 + letter * 6 + x] = 15
    start, size = entry["us"]["address"] - ROM_BASE, manifest.size(entry, "us")
    raw = rom_slice(data, entry["us"]["address"], size)
    edited, details = replace_fixed_tiles(raw, layout, len(manifest.animations(entry, "us")), layers, owner.sprite_sheet)
    candidate = data[:start] + edited + data[start + size:]
    report = {"schema_version": 1, "operation": "title_graphic_probe", "source_sha256": sha256(data),
              "target_sha256": sha256(candidate), "commit": COMMIT,
              "resource": original["entry_name"], "source_resource_sha256": sha256(raw), "target_resource_sha256": sha256(edited),
              "source_span": {"start": start, "size": size}, "original_text": "PRESS START", "translation": TITLE_TEXT,
              "recipe": "authored_5x7_capitals_v1", "frames_edited": 5, "text_bounds": [20, 0, 97, 7],
              "declared_tile_borrowers": borrowers, **details,
              "bytes_changed": sum(a != b for a, b in zip(data, candidate)), "rom_size_unchanged": len(candidate) == len(data),
              "outside_resource_unchanged": candidate[:start] == data[:start] and candidate[start + size:] == data[start + size:],
              "runtime_verified": False, "release_approved": False,
              "limitations": ["One title prompt, not complete title/menu localization.",
                              "No relocation, compression or external-consumer reachability proof.",
                              "Palette, animation and composition still require runtime inspection."]}
    return candidate, report
