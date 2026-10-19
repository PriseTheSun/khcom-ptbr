#!/usr/bin/env python3
"""Compõe os pilotos já verificados em um pacote privado para o aplicativo."""

import argparse
import json
from pathlib import Path
import sys

from khcom.bps import apply, create
from khcom.credits_profile import build_profile
from khcom.errors import KhcomError
from khcom.graphic_probe import build_title_probe
from khcom.rom import read_rom
from khcom.relocation_probe import build_verified_relocation_probe
from khcom.text import build_dialogue_probe, json_bytes, write_private
from khcom.upstream import PROJECT_ROOT, sha256


def compose(source: bytes, candidates: list[tuple[str, bytes]]) -> tuple[bytes, list[dict]]:
    """Every changed byte must have exactly one owner, even if values agree."""
    target = bytearray(source)
    owners: dict[int, str] = {}
    report = []
    if not candidates or len({name for name, _ in candidates}) != len(candidates):
        raise KhcomError("composition_identity", "Componentes devem ser não vazios e distintos.")
    for name, candidate in candidates:
        if len(candidate) != len(source):
            raise KhcomError("composition_size", "Um piloto alterou o tamanho da ROM.", component=name)
        count = 0
        spans = []
        for offset, (before, after) in enumerate(zip(source, candidate)):
            if before == after:
                continue
            if offset in owners:
                raise KhcomError("composition_overlap", "Dois pilotos reivindicam o mesmo byte.",
                                 offset=offset, first=owners[offset], second=name)
            owners[offset] = name
            target[offset] = after
            count += 1
            if spans and spans[-1][1] == offset:
                spans[-1][1] = offset + 1
            else:
                spans.append([offset, offset + 1])
        if count == 0:
            raise KhcomError("composition_empty", "O piloto não contém alterações.", component=name)
        report.append({"component": name, "changed_bytes": count,
                       "candidate_sha256": sha256(candidate), "changed_spans": spans})
    return bytes(target), report


def reconstruct(source: bytes, *, fetch=False, version=2):
    if version not in (1, 2):
        raise KhcomError("recipe_version", "Versão de receita não suportada.")
    dialogue, dialogue_report = build_dialogue_probe(source, fetch=fetch)
    title, title_report = build_title_probe(source)
    fonts, font_report, _atlases = build_profile(source)
    candidates = [("sora-dialogue", dialogue), ("title-prompt", title), ("credits-fonts", fonts)]
    details = {"dialogue": dialogue_report, "title": title_report, "fonts": font_report}
    if version == 2:
        riku, riku_report = build_dialogue_probe(source, fetch=fetch, scene="riku-opening")
        menu, menu_report = build_verified_relocation_probe(source)
        candidates.extend([("riku-dialogue", riku), ("save-menu-relocation", menu)])
        details.update(riku=riku_report, menu=menu_report)
    candidate, components = compose(source, candidates)
    return candidate, components, details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--member")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fetch-upstream", action="store_true")
    parser.add_argument("--recipe-version", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    try:
        destination = args.out.resolve()
        if not destination.is_relative_to(PROJECT_ROOT / "private"):
            raise KhcomError("private_output_required", "Este pacote experimental contém derivados privados.")
        if args.out.exists() or args.out.is_symlink():
            raise KhcomError("output_exists", "Escolha uma pasta de saída nova.")
        rom = read_rom(args.rom, member=args.member)
        candidate, components, details = reconstruct(rom.data, fetch=args.fetch_upstream, version=args.recipe_version)
        patch, patch_report = create(rom.data, candidate)
        if apply(rom.data, patch, expected_target_sha256=sha256(candidate)) != candidate:
            raise KhcomError("composition_reapply", "O BPS composto não reconstituiu o destino.")
        manifest = {"schema_version": 1, "id": f"khcom-ptbr-demo-v{args.recipe_version}", "status": "experimental",
                    "source_sha256": sha256(rom.data), "target_sha256": sha256(candidate),
                    "patch_sha256": sha256(patch), "source_size": len(rom.data),
                    "target_size": len(candidate), "patch_size": len(patch),
                    "patch_file": "translation.bps", "save_compatibility": "B8CE-sram-v1",
                    "distribution_approved": False, "complete_game_coverage": False,
                    "description": ("Piloto: APERTE INICIAR, uma fala de Sora e fontes de créditos. "
                                    + ("Inclui uma fala de Riku e Salvar jogo?/Sim/Não. " if args.recipe_version == 2 else "")
                                    + "A maior parte do jogo permanece em inglês."),
                    "components": components}
        destination.mkdir(parents=True, exist_ok=False)
        write_private(destination / "candidate.gba", candidate)
        write_private(destination / "translation.bps", patch)
        write_private(destination / "evidence.json", json_bytes({
            "input": rom.identity["input"], "components": components,
            **details,
            "patch": patch_report, "combined_runtime_verified": False,
            "limitations": ["A composição exige teste próprio no aplicativo.",
                            "Nenhuma linha diagnóstica TESTE foi incluída nos créditos.",
                            "Não é uma tradução completa nem um pacote público de distribuição."]}))
        write_private(destination / "manifest.json", json_bytes(manifest))
        print(json.dumps({"ok": True, "manifest": str(destination / "manifest.json"),
                          "target_sha256": manifest["target_sha256"], "patch_size": len(patch)}))
        return 0
    except (KhcomError, OSError) as error:
        detail = error.as_dict() if isinstance(error, KhcomError) else {"code": "io_error", "message": str(error)}
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
