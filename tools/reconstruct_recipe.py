#!/usr/bin/env python3
"""Executa somente a receita fixa auditada, sobre a ROM fornecida pelo usuário."""
import argparse
import json
from pathlib import Path

from audit_patch import builder_digests
from build_demo_package import reconstruct
from khcom.bps import apply, create, digest
from khcom.errors import KhcomError
from khcom.io import read_file, write_json_new, write_new
from khcom.rom import read_rom
from khcom.upstream import PROJECT_ROOT

FIELDS = {"schema_version", "recipe", "recipe_version", "source_sha256", "target_sha256",
          "patch_sha256", "builders", "contains_original_payload", "full_translation"}


def validate_recipe(recipe, builders):
    if (not isinstance(recipe, dict) or set(recipe) != FIELDS or recipe.get("schema_version") != 1
            or recipe.get("recipe") != "khcom-ptbr-pilots" or type(recipe.get("recipe_version")) is not int
            or recipe["recipe_version"] not in (1, 2, 3, 4) or recipe.get("contains_original_payload") is not False
            or recipe.get("full_translation") is not False):
        raise KhcomError("recipe_schema", "Receita não pertence ao perfil fixo sem payload.")
    if recipe.get("builders") != builders:
        raise KhcomError("recipe_builders", "Os builders não correspondem à receita auditada.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--member")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        recipe = json.loads(read_file(args.recipe, 1024 * 1024))
        builders = builder_digests()
        validate_recipe(recipe, builders)
        source = read_rom(args.rom, member=args.member).data
        if digest(source) != recipe["source_sha256"]:
            raise KhcomError("recipe_source", "Origem não corresponde à receita.")
        candidate, components, _details = reconstruct(source, version=recipe["recipe_version"])
        patch, _proof = create(source, candidate)
        if (builder_digests() != builders or digest(candidate) != recipe["target_sha256"]
                or digest(patch) != recipe["patch_sha256"] or apply(source, patch) != candidate):
            raise KhcomError("recipe_result", "Reconstrução diverge da prova auditada.")
        out = args.out.resolve()
        if not out.is_relative_to(PROJECT_ROOT / "private") or out.exists() or args.out.is_symlink():
            raise KhcomError("recipe_output", "Escolha uma pasta privada nova.")
        out.mkdir(parents=True)
        write_new(out / "candidate.gba", candidate)
        write_new(out / "translation.bps", patch)
        manifest = {"schema_version": 1, "id": "khcom-ptbr-demo-v" + str(recipe["recipe_version"]),
                    "status": "experimental", "source_sha256": digest(source), "target_sha256": digest(candidate),
                    "patch_sha256": digest(patch), "source_size": len(source), "target_size": len(candidate),
                    "patch_size": len(patch), "patch_file": "translation.bps", "save_compatibility": "B8CE-sram-v1",
                    "distribution_approved": False, "complete_game_coverage": False,
                    "description": "Pilotos reconstruídos da sua ROM. A maior parte do jogo permanece em inglês.",
                    "components": components}
        write_json_new(out / "manifest.json", manifest)
        print(json.dumps({"ok": True, "target_sha256": digest(candidate), "patch_sha256": digest(patch),
                          "recipe_verified": True, "manifest": str(out / "manifest.json")}))
        return 0
    except (KhcomError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": error.as_dict() if isinstance(error, KhcomError) else str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
