#!/usr/bin/env python3
"""Audita o piloto fixado e emite receita sem bytes de ROM/assets para execução local."""
import argparse
import json
from pathlib import Path

from build_demo_package import reconstruct
from khcom.bps import apply, create, digest
from khcom.errors import KhcomError
from khcom.io import read_file, write_json_new
from khcom.rom import read_rom
from khcom.upstream import PROJECT_ROOT

def builder_digests():
    paths = sorted((PROJECT_ROOT / "tools/khcom").glob("*.py"))
    paths += [PROJECT_ROOT / name for name in ("tools/build_demo_package.py", "tools/audit_patch.py", "tools/reconstruct_recipe.py",
              "manifests/upstream.json", "manifests/rom-us.json", "manifests/relocation-menu-v1.json")]
    return {p.relative_to(PROJECT_ROOT).as_posix(): digest(read_file(p, 4 * 1024 * 1024)) for p in paths}


def provenance(literals, components):
    spans = sorted((start, end, c["component"]) for c in components for start, end in c["changed_spans"])
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise KhcomError("literal_owner", "Proveniência contém sobreposição.")
    result = []
    for literal in literals:
        start, end = literal["target_start"], literal["target_start"] + literal["length"]
        covered, names = 0, set()
        for first, last, name in spans:
            overlap = max(0, min(last, end) - max(first, start))
            if overlap:
                covered += overlap
                names.add(name)
        if covered != end - start:
            raise KhcomError("literal_owner", "Literal sem produtor exato.", target_start=start)
        permitted = names <= {"sora-dialogue", "riku-dialogue", "save-menu-relocation"}
        result.append({**literal, "components": sorted(names),
                       "provenance": "authored-translation-encoding" if permitted else "local-rom-derived-composition",
                       "public_literal_approved": permitted})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--member")
    parser.add_argument("--patch", required=True, type=Path)
    parser.add_argument("--recipe-out", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--recipe-version", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    try:
        source = read_rom(args.rom, member=args.member).data
        builders = builder_digests()
        candidate, components, _details = reconstruct(source, version=args.recipe_version)
        if builder_digests() != builders:
            raise KhcomError("recipe_changed", "Os builders mudaram durante a execução.")
        actual = read_file(args.patch, 64 * 1024 * 1024)
        regenerated, proof = create(source, candidate)
        if actual != regenerated or apply(source, actual) != candidate:
            raise KhcomError("literal_recipe", "Este patch não é reproduzido pela receita fixa sem metadados.")
        literals = provenance(proof["literals"], components)
        recipe = {"schema_version": 1, "recipe": "khcom-ptbr-pilots", "recipe_version": args.recipe_version,
                  "source_sha256": digest(source), "target_sha256": digest(candidate),
                  "patch_sha256": digest(actual),
                  "builders": builders,
                  "contains_original_payload": False, "full_translation": False}
        report = {**proof, "literals": literals, "recipe_sha256": digest((json.dumps(recipe, ensure_ascii=False, indent=2) + "\n").encode()),
                  "recipe_reconstructs_exact_target": True, "recipe_reconstructs_exact_patch": True,
                  "original_payload_in_recipe": False, "distribution_approved": False,
                  "reason": "O BPS contém composições derivadas da ROM. Distribuir a receita/código e gerar esses bytes localmente.",
                  "limitations": ["Auditoria limitada à receita fixa de pilotos; não certifica patches arbitrários.",
                                  "Uma distribuição futura deve vincular todos os builders e repetir a auditoria."]}
        write_json_new(args.recipe_out, recipe)
        write_json_new(args.report, report)
        print(json.dumps({"ok": True, "literal_records": len(literals), "literal_bytes": sum(x["length"] for x in literals),
                          "target_sha256": digest(candidate), "public_bps_approved": False, "recipe_verified": True}))
        return 0
    except (KhcomError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": error.as_dict() if isinstance(error, KhcomError) else str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
