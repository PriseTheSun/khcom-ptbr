"""Partições editoriais rastreáveis; planejamento nunca aprova tradução ou QA."""
from collections import defaultdict
import copy

from .coverage import canonical_digest
from .errors import KhcomError
from .text import bind_catalog, validate_catalog


def _index(rows):
    result = {}
    for row in rows:
        identity = row.get("id") if isinstance(row, dict) else None
        if not isinstance(identity, str) or not identity or identity in result:
            raise KhcomError("batch_identity", "ID ausente ou repetido no inventário.")
        result[identity] = row
    return result


def plan(catalog, inventory, events=None, *, max_items=48, max_characters=12000):
    validate_catalog(catalog)
    if (type(max_items) is not int or not 1 <= max_items <= 256
            or type(max_characters) is not int or not 100 <= max_characters <= 100000):
        raise KhcomError("batch_budget", "Orçamento da sessão editorial inválido.")
    if inventory.get("source_sha256") != catalog["origin"]["sha256"]:
        raise KhcomError("batch_origin", "Inventário e catálogo pertencem a ROMs diferentes.")
    texts, items = _index(catalog["items"]), _index(inventory["items"])
    if {k for k, v in items.items() if v["kind"] == "text"} != set(texts):
        raise KhcomError("batch_membership", "O inventário não cobre exatamente o catálogo textual.")
    contexts = defaultdict(list)
    if events is not None:
        if (events.get("schema") != "khcom-event-occurrences-v1"
                or events.get("source_sha256") != inventory["source_sha256"]):
            raise KhcomError("batch_context", "Ledger de eventos incompatível.")
        identities = set()
        for occurrence in events["occurrences"]:
            key = (occurrence["event_id"], occurrence["entry_index"])
            if key in identities:
                raise KhcomError("batch_context", "Ocorrência repetida no ledger de eventos.")
            identities.add(key)
            for identity in occurrence["catalog_ids"]:
                if identity not in texts:
                    raise KhcomError("batch_context", "Contexto aponta para ID textual desconhecido.")
                contexts[identity].append({k: occurrence[k] for k in
                    ("event_id", "entry_index", "script", "source_sha256", "portrait", "expression",
                     "effective_position", "origin", "alternate_palette", "unknowns", "runtime_observed", "layout")})
    groups = defaultdict(list)
    for identity, item in items.items():
        if item["kind"] == "text":
            source = texts[identity]
            if source["source_sha256"] != item["source_sha256"]:
                raise KhcomError("batch_origin", "Digest textual diverge do inventário.", id=identity)
            group = ("text", source["domain"], source["unit"])
        else:
            # Agrupar pelo dono declarado no ID do inventário, não adivinhar
            # se a imagem contém escrita a partir de seu nome/formato.
            group = ("resource", item["domain"], identity.rsplit("/", 1)[0])
        groups[group].append(identity)
    batches = []
    for group, members in sorted(groups.items()):
        ordered = sorted(members, key=lambda i: (items[i]["span"][0], i))
        chunks, current, characters = [], [], 0
        for identity in ordered:
            length = len(texts[identity]["source_text"]) if identity in texts else 0
            if current and (len(current) >= max_items or characters + length > max_characters):
                chunks.append(current)
                current, characters = [], 0
            current.append(identity)
            characters += length
        if current:
            chunks.append(current)
        for part, chunk in enumerate(chunks, 1):
            identity = "batch-" + canonical_digest({"group": group, "first_id": chunk[0]})[:16]
            batches.append({"id": identity, "kind": group[0], "domain": group[1], "context_group": group[2],
                "part": part, "parts": len(chunks), "items": chunk,
                "source_characters": sum(len(texts[i]["source_text"]) for i in chunk if i in texts),
                "source_digests": {i: items[i]["source_sha256"] for i in chunk},
                "contexts": {i: contexts[i] for i in chunk if contexts[i]},
                "campaign": None, "qa_route": None,
                "stages": {"classification": "pending", "translation": "pending", "review": "pending", "validation": "pending"},
                "unknowns": ["Campanha, percurso e todos os consumidores precisam de prova por ocorrência."]})
    _index(batches)
    result = {"schema": "khcom-editorial-batches-v1", "source_sha256": inventory["source_sha256"],
        "inventory_sha256": canonical_digest(inventory), "catalog_sha256": canonical_digest(catalog),
        "events_sha256": canonical_digest(events) if events is not None else None,
        "session_budget": {"max_items": max_items, "max_characters": max_characters,
            "meaning": "Limite editorial ajustável; não é limite do formato nem medição de tokens."},
        "items_total": len(items), "text_items": len(texts), "resource_items": len(items) - len(texts),
        "batches": batches, "discovery_closed": inventory.get("discovery_closed") is True,
        "full_translation": False, "runtime_qa_complete": False}
    verify_partition(result, inventory)
    return result


def verify_partition(value, inventory):
    if (value.get("schema") != "khcom-editorial-batches-v1"
            or value.get("source_sha256") != inventory["source_sha256"]
            or value.get("inventory_sha256") != canonical_digest(inventory)):
        raise KhcomError("batch_stale", "Inventário mudou; replaneje os lotes e suas revisões.")
    expected, seen = _index(inventory["items"]), set()
    for batch in _index(value.get("batches", [])).values():
        if not batch.get("items"):
            raise KhcomError("batch_empty", "Lote vazio não é uma sessão editorial.")
        for identity in batch["items"]:
            if identity not in expected or identity in seen:
                raise KhcomError("batch_membership", "ID extra ou em mais de um lote.", id=identity)
            if batch.get("source_digests", {}).get(identity) != expected[identity]["source_sha256"]:
                raise KhcomError("batch_origin", "Digest de origem do lote diverge.", id=identity)
            seen.add(identity)
    if seen != set(expected):
        raise KhcomError("batch_membership", "Há IDs sem lote.", missing=sorted(set(expected) - seen))


def editable_batches(value, catalog):
    if value["catalog_sha256"] != canonical_digest(catalog):
        raise KhcomError("batch_stale", "O catálogo não corresponde ao plano editorial.")
    texts = _index(catalog["items"])
    plan_digest = canonical_digest(value)
    return [{"schema": "khcom-editorial-session-v1", "batch_id": batch["id"],
             "plan_sha256": plan_digest, "items": [copy.deepcopy(texts[i]) for i in batch["items"]]}
            for batch in value["batches"] if batch["kind"] == "text"]


def assemble(value, sessions, catalog):
    expected = {row["batch_id"]: row for row in editable_batches(value, catalog)}
    if len(sessions) != len(expected):
        raise KhcomError("batch_sessions", "Forneça todos os lotes textuais, sem extras.")
    seen, rows = set(), []
    plan_digest = canonical_digest(value)
    for session in sessions:
        identity = session.get("batch_id")
        if (identity not in expected or identity in seen
                or session.get("schema") != "khcom-editorial-session-v1"
                or session.get("plan_sha256") != plan_digest
                or set(_index(session.get("items", []))) != set(_index(expected[identity]["items"]))):
            raise KhcomError("batch_sessions", "Lote trocado, incompleto, duplicado ou de outro plano.")
        seen.add(identity)
        rows.extend(session["items"])
    result = copy.deepcopy(catalog)
    by_id = _index(rows)
    if set(by_id) != set(_index(catalog["items"])):
        raise KhcomError("batch_membership", "O plano textual perdeu IDs do catálogo.")
    result["items"] = [by_id[item["id"]] for item in catalog["items"]]
    bind_catalog(result, catalog)
    return result


def checklist(value):
    lines = ["# Sessões editoriais do inventário conhecido", "",
             f"Plano `{canonical_digest(value)}`; {value['items_total']} IDs únicos.", "",
             "Cada caixa exige classificar, traduzir quando aplicável, revisar e validar todas as ocorrências.",
             "O inventário permanece aberto. As caixas abaixo não comprovam tradução, gameplay ou revisão humana.", ""]
    for batch in value["batches"]:
        group = batch["context_group"].replace("`", "")
        lines.append(f"- [ ] {batch['id']} — {batch['domain']} / `{group}` / parte {batch['part']}/{batch['parts']}: "
                     f"{len(batch['items'])} IDs; classificação, tradução, revisão e validação pendentes.")
    return "\n".join(lines) + "\n"
