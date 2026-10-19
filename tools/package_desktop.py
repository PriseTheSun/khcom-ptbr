#!/usr/bin/env python3
"""Cria .app/ZIP desktop experimental com fontes correspondentes e sem ROM/BPS."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tarfile
import urllib.request

from khcom.errors import KhcomError
from khcom.io import read_file, write_json_new, write_new
from khcom.package import MAX_FILE, MAX_TOTAL, FORBIDDEN, architecture, audit, deterministic_zip, digest, relative
from stage_sources import inventory

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "KHCoM PT-BR.app"


def dependency_archive(row: dict, fetch: bool) -> bytes:
    path = ROOT / ".deps" / row["archive"]
    if not path.exists() and fetch:
        with urllib.request.urlopen(row["url"], timeout=60) as response:
            data = response.read(MAX_FILE + 1)
        if len(data) > MAX_FILE or digest(data) != row["sha256"]:
            raise KhcomError("package_dependency", "Download diverge do manifesto.", archive=row["archive"])
        write_new(path, data)
    data = read_file(path, MAX_FILE)
    if digest(data) != row["sha256"]:
        raise KhcomError("package_dependency", "Arquivo de fontes diverge do manifesto.", archive=row["archive"])
    return data


def source_zip(path: Path, dependencies: dict, fetch: bool) -> str:
    entries = [("project/" + name.as_posix(), data, 0o644) for name, data in inventory(ROOT)]
    for name, row in dependencies["sources"].items():
        data = dependency_archive(row, fetch)
        if name != "mgba":
            entries.append(("project/.deps/" + row["archive"], data, 0o644))
            continue
        # Upstream includes 162 test ROMs in cinema/. None is part of the
        # embedded core build. Ship corresponding build sources, not that corpus.
        excluded, files, total = [], [], 0
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive:
                parts = relative(member.name).parts
                if len(parts) == 1 or member.isdir():
                    continue
                local = "/".join(parts[1:])
                if parts[1] == "cinema":
                    excluded.append(local)
                    continue
                if not member.isfile() or member.size > MAX_FILE:
                    raise KhcomError("package_source", "Entrada de fonte não regular/excessiva.", path=local)
                if Path(local).suffix.lower() in FORBIDDEN | {".gb", ".gbc", ".nds"}:
                    raise KhcomError("package_source", "ROM inesperada fora do corpus excluído.", path=local)
                total += member.size
                if total > MAX_TOTAL:
                    raise KhcomError("package_source", "Fontes descomprimidas acima do orçamento.")
                stream = archive.extractfile(member)
                payload = stream.read(member.size + 1)
                if len(payload) != member.size:
                    raise KhcomError("package_source", "Fonte truncada.", path=local)
                entries.append(("project/.deps/mgba-source/" + local, payload, 0o644))
                files.append({"path": local, "size": len(payload), "sha256": digest(payload)})
        proof = {"archive_sha256": row["sha256"], "excluded_prefixes": ["cinema/"],
                 "excluded_files": len(excluded), "files": files}
        entries.append(("project/.deps/mgba-source-inventory.json", (json.dumps(proof, indent=2) + "\n").encode(), 0o644))
    deterministic_zip(path, entries)
    return digest(read_file(path, MAX_FILE))


def verify_macos(binary: Path, expected: list[str]) -> dict:
    if sys.platform != "darwin":
        raise KhcomError("package_host", "A auditoria Mach-O requer as ferramentas Apple no macOS.")
    slices = subprocess.check_output(["lipo", "-archs", str(binary)], text=True).split()
    if sorted(slices) != expected:
        raise KhcomError("package_architecture", "lipo diverge do parser de arquiteturas.")
    libraries = subprocess.check_output(["otool", "-L", str(binary)], text=True)
    dependencies = [line.strip().split(" (", 1)[0] for line in libraries.splitlines() if line.startswith("\t")]
    unexpected = [name for name in dependencies if not name.startswith(("/usr/lib/", "/System/Library/"))]
    commands = subprocess.check_output(["otool", "-l", str(binary)], text=True)
    if unexpected or "LC_RPATH" in commands:
        raise KhcomError("package_dependency", "Binário requer bibliotecas/rpaths fora do sistema.", unexpected=unexpected)
    return {"architectures": expected, "dependencies": sorted(set(dependencies)), "rpaths": [],
            "method": "lipo -archs; otool -L; otool -l", "native_qa": False}


def build(args) -> dict:
    out = args.out.absolute()
    if out.exists() or out.is_symlink():
        raise KhcomError("output_exists", "Escolha uma pasta nova para o pacote.")
    binary = read_file(args.binary, MAX_FILE)
    arches = architecture(binary)
    if args.platform == "macos":
        platform_evidence = verify_macos(args.binary, arches)
    elif arches != ["x86_64"] or binary[:2] != b"MZ":
        raise KhcomError("package_architecture", "O pacote Windows requer PE x64.")
    else:
        platform_evidence = {"architectures": arches, "native_qa": False,
                             "dependency_audit": "required-on-Windows-runner"}
    notices = read_file(args.build / "third-party-notices.txt", 4 * 1024 * 1024)
    deps = json.loads(read_file(ROOT / "manifests/runtime-deps.json", 1024 * 1024))
    out.mkdir(parents=True)
    payload = out / "payload"
    payload.mkdir()
    roles = {}

    def emit(name, data, role, executable=False):
        write_new(payload / name, data)
        if executable:
            (payload / name).chmod(0o755)
        roles[name] = role

    if args.platform == "macos":
        executable = f"{APP_NAME}/Contents/MacOS/khcom-desktop"
        emit(executable, binary, "executable", True)
        plist = {"CFBundleDevelopmentRegion": "pt_BR", "CFBundleDisplayName": "KHCoM PT-BR",
                 "CFBundleExecutable": "khcom-desktop", "CFBundleIdentifier": "org.khcom.ptbr.experimental",
                 "CFBundleName": "KHCoM PT-BR", "CFBundlePackageType": "APPL",
                 "CFBundleShortVersionString": "0.1.0", "CFBundleVersion": "1",
                 "LSMinimumSystemVersion": "13.0", "NSHighResolutionCapable": True,
                 "NSHumanReadableCopyright": "Aplicativo experimental. Marcas pertencem aos seus titulares."}
        emit(f"{APP_NAME}/Contents/Info.plist", plistlib.dumps(plist, sort_keys=True), "bundle-metadata")
        emit(f"{APP_NAME}/Contents/Resources/third-party-notices.txt", notices, "notices")
        # Ad-hoc seal makes local loading explicit. It is NOT Developer ID/notarization.
        subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(payload / APP_NAME)], check=True)
        for p in (payload / APP_NAME).rglob("*"):
            if p.is_file() and p.relative_to(payload).as_posix() not in roles:
                roles[p.relative_to(payload).as_posix()] = "signature"
    else:
        executable = "khcom-desktop.exe"
        emit(executable, binary, "executable", True)
        emit("third-party-notices.txt", notices, "notices")
    sources_hash = source_zip(payload / "corresponding-source.zip", deps, args.fetch_deps)
    roles["corresponding-source.zip"] = "sources"
    components = []
    licenses = {"mgba": "MPL-2.0", "sdl": "Zlib", "imgui": "MIT", "json": "MIT", "miniz": "MIT"}
    for name, row in deps["sources"].items():
        components.append({"type": "library", "name": name, "version": row["version"],
                           "bom-ref": name, "hashes": [{"alg": "SHA-256", "content": row["sha256"]}],
                           "licenses": [{"license": {"id": licenses[name]}}],
                           "externalReferences": [{"type": "distribution", "url": row["url"]}]})
    for name, license_id in deps["licenses"].items():
        components.append({"type": "file", "name": name, "bom-ref": "notice:" + name,
                           "properties": [{"name": "khcom:license-notice", "value": license_id}]})
    emit("sbom.cdx.json", (json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
          "components": components}, ensure_ascii=False, indent=2) + "\n").encode(), "sbom")
    instructions = """KHCoM PT-BR — aplicativo experimental, tradução parcial

Esta distribuição não contém ROM, BIOS, tradução completa ou dados do jogo.
Abra o aplicativo e selecione sua ROM USA B8CE e o pacote local de tradução.
Use Escape/F1 para abrir o menu. Saves/configuração ficam na pasta de dados
indicada na aba Dados, fora desta instalação. Remover o aplicativo não os apaga.

macOS: copie o .app para sua pasta Aplicativos. A assinatura é somente ad-hoc;
não há Developer ID nem notarização. Windows: abra o .exe no ZIP extraído ou
use o instalador. Este pacote não comprova suporte às versões mínimas dos SOs.

Fontes correspondentes/relink: extraia corresponding-source.zip. A pasta
project contém o código desta compilação, quatro arquivos upstream em .deps
e fontes mGBA em .deps/mgba-source (sem o corpus cinema de ROMs de teste), com
inventário por arquivo e SHA-256 do upstream em manifests/runtime-deps.json.
Instale as ferramentas de requirements-build.txt em ambiente próprio, execute
cmake -S project -B build -DCMAKE_BUILD_TYPE=Release
  -DFETCHCONTENT_SOURCE_DIR_MGBA=/caminho/absoluto/project/.deps/mgba-source
e cmake --build build. Antes aplique o ajuste de build com
cmake -DSOURCE_DIR=/caminho/absoluto/project/.deps/mgba-source
  -P project/cmake/PatchMgbaVersion.cmake.
No macOS use -DCMAKE_OSX_ARCHITECTURES=arm64 ou x86_64. No Windows use o
gerador Visual Studio 17 2022, -A x64 e --config Release. Para modificar uma
dependência, extraia seu arquivo e configure -DFETCHCONTENT_SOURCE_DIR_MGBA=
caminho/da/fonte (ou SDL/IMGUI/JSON/MINIZ). Para mGBA aplique também
cmake/PatchMgbaVersion.cmake, conforme o build original. O blip_buf LGPL
encontra-se em src/third-party/blip_buf. O aplicativo pode ser reconstruído
com a biblioteca modificada; não são impostas restrições de engenharia reversa
necessária à depuração dessas modificações. Os avisos e licenças acompanham
o aplicativo e as fontes; as fontes do jogo comercial não são incluídas.

O pacote é uma prévia técnica, não a conclusão da localização PT-BR.
"""
    emit("LEIA-ME.txt", instructions.encode(), "instructions")
    manifest = {"schema_version": 1, "kind": "desktop-without-game-data", "status": "experimental",
                "platform": args.platform, "architectures": arches, "version": "0.1.0",
                "sources_sha256": sources_hash, "binary_input_sha256": digest(binary),
                "platform_evidence": platform_evidence,
                "signature": "ad-hoc" if args.platform == "macos" else "unsigned",
                "release_approved": False, "files": []}
    for name, role in sorted(roles.items()):
        data = read_file(payload / name, MAX_FILE)
        manifest["files"].append({"path": name, "role": role, "size": len(data), "sha256": digest(data)})
    write_json_new(payload / "package-manifest.json", manifest)
    report = audit(payload, manifest)
    write_json_new(out / "audit.json", report)
    name = "KHCoM-PTBR-" + args.platform + "-" + ("universal" if len(arches) == 2 else arches[0]) + "-experimental.zip"
    entries = [(p.relative_to(payload).as_posix(), read_file(p, MAX_FILE), 0o755 if os.access(p, os.X_OK) else 0o644)
               for p in payload.rglob("*") if p.is_file()]
    deterministic_zip(out / name, entries)
    result = {"ok": True, "package": str(payload), "archive": str(out / name),
              "sha256": digest(read_file(out / name, MAX_FILE)), "audit": report}
    write_json_new(out / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--platform", choices=["macos", "windows"], required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fetch-deps", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), ensure_ascii=False))
        return 0
    except (KhcomError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(json.dumps({"ok": False, "error": error.as_dict() if isinstance(error, KhcomError) else str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
