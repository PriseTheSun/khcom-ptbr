"""Coverage denominators and evidence contracts, independent of editorial counts.

Receipts record the reviewing producer's conclusion. File integrity and scope
are verified here; a receipt does not make this tool a linguistic reviewer.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .errors import KhcomError
from .io import read_file

SURFACES = ("sora", "riku", "optional", "cards-items-abilities", "tutorials-menus",
            "dynamic-text", "graphics", "movies", "credits", "link-errors",
            "font-variants", "desktop-installer")
MAX_ITEMS = 50000
MAX_RECEIPTS = 100000
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def canonical_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def inventory_from_sources(catalog: dict, assets: dict) -> dict:
    if catalog["origin"]["sha256"] != assets["source_sha256"]:
        raise KhcomError("coverage_origin", "Texto e recursos pertencem a origens diferentes.")
    items = [{"id": item["id"], "kind": "text", "domain": item["domain"],
              "source_sha256": item["source_sha256"], "span": [item["source_span"]["start"], item["source_span"]["end"]], "occurrences": [],
              "occurrences_closed": False} for item in catalog["items"]]
    items.extend({"id": item["id"], "kind": "resource", "domain": item["format"],
                  "source_sha256": item["sha256"], "span": [item["start"], item["end"]], "occurrences": [],
                  "occurrences_closed": False} for item in assets["assets"])
    return {"schema_version": 1, "source_sha256": catalog["origin"]["sha256"],
            "upstream_commit": assets["commit"], "items": sorted(items, key=lambda item: item["id"]),
            "surfaces": list(SURFACES), "discovery_closed": False,
            "unknowns": ["Inventário de consumidores, variantes e texto audiovisual ainda aberto."],
            "provenance": {"catalog_sha256": canonical_digest(catalog),
                           "assets_sha256": canonical_digest(assets)}}


def _index(rows, field: str, maximum: int) -> dict:
    if not isinstance(rows, list) or len(rows) > maximum:
        raise KhcomError("coverage_schema", "Lista inválida ou acima do orçamento.", field=field)
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not row["id"] or len(row["id"]) > 1024 or row["id"] in result):
            raise KhcomError("coverage_identity", "Identidade ausente ou duplicada.", field=field)
        result[row["id"]] = row
    return result


def _digest(value) -> bool:
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def bind_inventory(inventory: dict, actual: dict, source: bytes) -> None:
    """Retain every freshly extracted owner; new discoveries need exact spans."""
    if not isinstance(inventory, dict) or inventory.get("source_sha256") != actual["source_sha256"]:
        raise KhcomError("coverage_origin", "O inventário pertence a outra ROM.")
    expected = _index(actual.get("items"), "actual", MAX_ITEMS)
    submitted = _index(inventory.get("items"), "inventory", MAX_ITEMS)
    if expected.keys() - submitted.keys():
        raise KhcomError("coverage_membership", "O inventário omite recursos descobertos.",
                         missing=sorted(expected.keys() - submitted.keys()))
    for identity, item in submitted.items():
        if identity in expected:
            if any(item.get(key) != expected[identity][key]
                   for key in ("kind", "domain", "source_sha256", "span")):
                raise KhcomError("coverage_provenance", "Dados de origem alterados.", id=identity)
        else:
            span = item.get("span")
            if (not isinstance(span, list) or len(span) != 2 or any(type(n) is not int for n in span)
                    or not 0 <= span[0] < span[1] <= len(source)
                    or hashlib.sha256(source[span[0]:span[1]]).hexdigest() != item.get("source_sha256")):
                raise KhcomError("coverage_provenance", "Recurso adicional não está ligado aos bytes da ROM.", id=identity)


def evaluate(inventory: dict, ledger: dict, evidence_root: Path) -> dict:
    if (not isinstance(inventory, dict) or inventory.get("schema_version") != 1
            or not isinstance(ledger, dict) or ledger.get("schema_version") != 1
            or not _digest(inventory.get("source_sha256"))):
        raise KhcomError("coverage_schema", "Inventário/ledger inválido ou versão não suportada.")
    items = _index(inventory.get("items"), "items", MAX_ITEMS)
    reviews = _index(ledger.get("items", []), "reviews", MAX_ITEMS)
    if (not isinstance(inventory.get("surfaces"), list)
            or any(not isinstance(value, str) for value in inventory["surfaces"])
            or len(inventory["surfaces"]) != len(set(inventory["surfaces"]))):
        raise KhcomError("coverage_schema", "Lista de superfícies inválida.")
    occurrences = {}
    for item in items.values():
        if (item.get("kind") not in ("text", "resource") or not _digest(item.get("source_sha256"))
                or not isinstance(item.get("domain"), str) or not item["domain"]):
            raise KhcomError("coverage_schema", "Tipo ou digest do item inválido.", id=item["id"])
        for identity, occurrence in _index(item.get("occurrences"), "occurrences", MAX_ITEMS).items():
            if identity in occurrences or occurrence.get("surface") not in SURFACES:
                raise KhcomError("coverage_identity", "Ocorrência duplicada ou superfície desconhecida.", id=identity)
            if len(occurrences) >= MAX_RECEIPTS:
                raise KhcomError("coverage_budget", "Inventário de ocorrências acima do orçamento.")
            occurrences[identity] = (item, occurrence)
    if len(occurrences) > MAX_RECEIPTS:
        raise KhcomError("coverage_budget", "Inventário de ocorrências acima do orçamento.")
    evidence_root = evidence_root.resolve()
    receipts = ledger.get("receipts", {})
    if not isinstance(receipts, dict) or len(receipts) > MAX_RECEIPTS:
        raise KhcomError("coverage_schema", "Índice de evidências inválido.")
    cache = {}
    bytes_read = 0
    blockers = []

    def block(code, identity=None):
        blockers.append({"code": code, **({"id": identity} if identity else {})})

    def receipt(ref, kind, identity, source_digest, translation_digest=None):
        nonlocal bytes_read
        if not isinstance(ref, str) or ref not in receipts:
            return False
        descriptor = receipts[ref]
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("path"), str) or not _digest(descriptor.get("sha256")):
            return False
        path = Path(descriptor["path"])
        if path.is_absolute() or ".." in path.parts or path.suffix != ".json":
            return False
        resolved = (evidence_root / path).resolve()
        if not resolved.is_relative_to(evidence_root):
            return False
        cache_key = (str(resolved), descriptor["sha256"])
        if cache_key not in cache:
            try:
                remaining = 64 * 1024 * 1024 - bytes_read
                if remaining <= 0:
                    return False
                raw = read_file(resolved, min(remaining, 1024 * 1024))
                bytes_read += len(raw)
                if bytes_read > 64 * 1024 * 1024:
                    raise KhcomError("coverage_budget", "Evidências excedem orçamento agregado de 64 MiB.")
                if hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
                    return False
                cache[cache_key] = json.loads(raw)
            except (OSError, ValueError, RecursionError, KhcomError):
                return False
        value = cache[cache_key]
        return (isinstance(value, dict) and value.get("schema_version") == 1
                and value.get("kind") == kind and value.get("subject_id") == identity
                and value.get("source_sha256") == source_digest
                and value.get("target_sha256") == ledger.get("target_sha256")
                and value.get("build_sha256") == ledger.get("build_sha256")
                and (translation_digest is None or value.get("translation_sha256") == translation_digest)
                and value.get("result") == "pass"
                and isinstance(value.get("reviewer"), str) and bool(value["reviewer"].strip())
                and isinstance(value.get("method"), str) and bool(value["method"].strip()))

    if ledger.get("inventory_sha256") != canonical_digest(inventory):
        block("inventory_changed")
    if ledger.get("source_sha256") != inventory["source_sha256"]:
        block("source_changed")
    if not all(_digest(ledger.get(key)) for key in ("target_sha256", "build_sha256", "patch_sha256")):
        block("release_identity_unknown")
    if set(inventory.get("surfaces", [])) != set(SURFACES):
        block("surface_inventory_incomplete")
    if inventory.get("discovery_closed") is not True or inventory.get("unknowns") != []:
        block("discovery_open")
    if not items:
        block("empty_inventory")
    for identity in reviews.keys() - items.keys():
        block("review_for_unknown_item", identity)
    counts = Counter()
    for identity, item in items.items():
        before = len(blockers)
        review = reviews.get(identity, {})
        classification = review.get("classification", "unknown")
        counts[classification if classification in ("visible_text", "non_text", "unreachable") else "unknown"] += 1
        if review.get("source_sha256") != item["source_sha256"]:
            block("item_review_missing_or_stale", identity)
        if classification not in ("visible_text", "non_text", "unreachable"):
            block("classification_unknown", identity)
        if not receipt(review.get("classification_evidence"), "classification", identity, item["source_sha256"]):
            block("classification_evidence_missing", identity)
        if item["kind"] == "text" and classification == "non_text":
            block("text_cannot_be_non_text", identity)
        if classification == "visible_text":
            if not _digest(review.get("translation_sha256")):
                block("translation_missing", identity)
            if review.get("unchanged") is True:
                exception = review.get("exception", {})
                if (not isinstance(exception, dict) or exception.get("category") not in ("proper_name", "brand", "title")
                        or not isinstance(exception.get("reason"), str) or not exception["reason"].strip()
                        or not receipt(exception.get("evidence"), "name_exception", identity, item["source_sha256"])):
                    block("unchanged_without_specific_exception", identity)
            elif review.get("unchanged") is not False:
                block("source_comparison_unknown", identity)
            for kind in ("linguistic", "binary"):
                if not receipt(review.get(kind + "_evidence"), kind, identity, item["source_sha256"], review.get("translation_sha256")):
                    block(kind + "_review_missing", identity)
            if item.get("occurrences_closed") is not True or not item["occurrences"]:
                block("occurrences_open", identity)
            visual = review.get("visual_evidence", {})
            if not isinstance(visual, dict):
                visual = {}
            for occurrence in item["occurrences"]:
                if not receipt(visual.get(occurrence["id"]), "visual", occurrence["id"], item["source_sha256"], review.get("translation_sha256")):
                    block("visual_review_missing", occurrence["id"])
                else:
                    counts["verified_occurrences"] += 1
        if len(blockers) == before:
            counts["closed_items"] += 1
    surface_refs = ledger.get("surfaces", {})
    if not isinstance(surface_refs, dict):
        surface_refs = {}
    for surface in SURFACES:
        if not receipt(surface_refs.get(surface), "surface", surface, inventory["source_sha256"]):
            block("surface_review_missing", surface)
    return {"schema_version": 1, "operation": "coverage_gate", "inventory_sha256": canonical_digest(inventory),
            "source_sha256": inventory["source_sha256"],
            "target_sha256": ledger.get("target_sha256"), "build_sha256": ledger.get("build_sha256"),
            "patch_sha256": ledger.get("patch_sha256"), "items_total": len(items),
            "denominators_by_kind": dict(Counter(item["kind"] for item in items.values())),
            "denominators_by_domain": dict(Counter(item["domain"] for item in items.values())),
            "occurrences_by_surface": dict(Counter(row[1]["surface"] for row in occurrences.values())),
            "occurrences_total": len(occurrences), "counts": dict(counts),
            "blocker_counts": dict(Counter(row["code"] for row in blockers)), "blockers": blockers,
            "coverage_complete": not blockers, "release_approved": False,
            "receipt_files_verified": len(cache), "receipt_bytes_read": bytes_read,
            "limitations": ["Conclusões linguísticas e visuais são declarações dos produtores identificados nos recibos.",
                            "Este verificador confere escopo, integridade e completude dessas declarações, não revisa pixels/prosa sozinho.",
                            "Revisão final do proprietário, assinatura, licenças e plataformas são gates separados."]}
