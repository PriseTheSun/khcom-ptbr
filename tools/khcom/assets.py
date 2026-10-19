"""Inventory pinned asset layouts, retaining partial record verification.

Layout ownership is not a graphics round-trip or a complete reachability map.
Unresolved symbol fields stay unknown rather than pass as verified pointers.
"""

from collections import Counter

from .errors import KhcomError
from .graphics import rom_slice
from .rom import identify_bytes
from .text import ROM_BASE
from .upstream import COMMIT, SNAPSHOT, load_asset_manifests, sha256


def inventory_assets(data: bytes, *, fetch: bool = False) -> dict:
    identify_bytes(data)
    owner, manifests = load_asset_manifests(fetch=fetch)
    return inspect_asset_layouts(data, manifests, owner, source_root=SNAPSHOT, commit=COMMIT)


def inspect_asset_layouts(data: bytes, manifests: list, owner, *, source_root, commit: str) -> dict:
    """Inspect already parsed layouts; the acquisition boundary owns identity."""
    entries = []
    addresses = {}
    seen = set()
    try:
        for manifest in manifests:
            manifest.members("us")  # Checks object membership, alignment and ends.
            for entry in manifest.entries:
                if "us" not in entry:
                    continue
                name = entry["name"]
                if name in seen:
                    raise KhcomError("asset_identity", "Nome de entrada de asset duplicado.", entry_name=name)
                seen.add(name)
                entries.append((manifest, entry))
                # A sprite_sheet's resource begins with frames/animations, not
                # with its tile payload. Never resolve that symbol to its start.
                if entry.get("format") != "sprite_sheet":
                    addresses[name] = entry["us"]["address"]
        assets = []
        for manifest, entry in entries:
            start = entry["us"]["address"]
            size = manifest.size(entry, "us")
            raw = rom_slice(data, start, size)
            kind = manifest.kind(entry) or entry["format"]
            unresolved = []
            references = []
            verification = {"kind": "layout_only", "checked_bytes": 0}
            if kind in ("struct", "array", "table", "string"):
                for offset, width, value in owner.record_chunks(manifest, entry, "us"):
                    if not isinstance(value, str):
                        continue
                    name = value.partition("+")[0] if "+" in value else value.partition("-")[0]
                    resolved = name.strip() in addresses
                    field = {"offset": offset, "width": width, "expression": value,
                             "observed_value": int.from_bytes(raw[offset:offset + width], "little"),
                             "resolved_against_asset_layout": resolved}
                    references.append(field)
                    if not resolved:
                        unresolved.append(field)
                owner.check_record(manifest, entry, "us", raw, addresses)
                verification = {"kind": "partial_record_match" if unresolved else "complete_record_match",
                                "checked_bytes": size - sum(field["width"] for field in unresolved)}
            elif kind == "fill":
                if raw != bytes([entry["value"]]) * size:
                    raise KhcomError("asset_fill", "Padding difere do manifesto.", entry_name=entry["name"])
                verification = {"kind": "exact_fill_match_not_proven_reusable", "checked_bytes": size}
            assets.append({"id": f"us/asset/{manifest.group}/{entry['name']}", "entry_name": entry["name"],
                           "emitted_symbols": manifest.symbols(entry, "us"),
                           "emitted_symbol_addresses_resolved": entry.get("format") != "sprite_sheet",
                           "kind": "asset", "format": kind, "start": start - ROM_BASE, "end": start - ROM_BASE + size,
                           "sha256": sha256(raw), "verification": verification, "references": references,
                           "compression": entry["us"].get("compress"), "palette_entry": entry.get("palette"),
                           "borrowed_tiles_entry": entry.get("tiles"), "reusable": None,
                           "provenance": {"commit": commit, "manifest": manifest.path.relative_to(source_root).as_posix(),
                                          "kind": "pinned_layout_on_supplied_bytes"}})
        cursor = 0
        for asset in sorted(assets, key=lambda asset: asset["start"]):
            if asset["start"] < cursor:
                raise KhcomError("asset_overlap", "Recursos de assets se sobrepõem.", id=asset["id"])
            cursor = asset["end"]
    except owner.ManifestError as error:
        raise KhcomError("asset_manifest", "Manifesto não confirmou o inventário de assets.", reason=str(error)) from error
    return {"format_version": 1, "source_sha256": sha256(data), "commit": commit,
            "manifest_count": len(manifests), "assets": assets,
            "asset_bytes": sum(asset["end"] - asset["start"] for asset in assets),
            "counts_by_format": dict(Counter(asset["format"] for asset in assets)),
            "verification_counts": dict(Counter(asset["verification"]["kind"] for asset in assets)),
            "unresolved_reference_fields": sum(not ref["resolved_against_asset_layout"] for asset in assets for ref in asset["references"]),
            "complete_graphics_inventory": False, "runtime_verified": False,
            "limitations": ["Layout and record checks do not decode every graphic, animation, audio or video payload.",
                            "Record pointers to unresolved symbols remain unknown, including frame, code and text references.",
                            "Uniform fill, unobserved resources and gaps are not proven reusable space.",
                            "Only pinned manifests are included; semantic text-in-image coverage requires a separate visual inventory."]}
