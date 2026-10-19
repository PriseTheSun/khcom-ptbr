"""Acquire and verify the selected, immutable khcom format sources.

Only the selected parser modules are imported. No upstream build, extractor,
configure or other entry point is executed.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import ModuleType
import urllib.error
import urllib.request

from .errors import KhcomError
from .io import read_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT_ROOT / "manifests" / "upstream.json"
SNAPSHOT = PROJECT_ROOT / ".deps" / "khcom"
COMMIT = "5dc49b75068bfe24e07bdaf365570d64682680c3"
RAW_BASE = f"https://raw.githubusercontent.com/Pheenoh/khcom/{COMMIT}/"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_manifest() -> dict:
    try:
        value = json.loads(read_file(MANIFEST, 256 * 1024).decode("utf-8"))
    except (OSError, ValueError) as error:
        raise KhcomError("upstream_manifest", "Manifesto upstream inválido.", reason=str(error)) from error
    if not isinstance(value, dict) or value.get("format_version") != 1 or not isinstance(value.get("files"), list):
        raise KhcomError("upstream_manifest", "Estrutura do manifesto upstream inválida.")
    if value.get("commit") != COMMIT or value.get("raw_base") != RAW_BASE:
        raise KhcomError("upstream_revision", "A revisão upstream não corresponde à versão suportada.")
    names = set()
    for item in value["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or type(item.get("size")) is not int or not 0 < item["size"] <= 4 * 1024 * 1024:
            raise KhcomError("upstream_manifest", "Registro de arquivo upstream inválido.")
        digest = item.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise KhcomError("upstream_manifest", "Digest de arquivo upstream inválido.")
        if item["path"] in names:
            raise KhcomError("upstream_manifest", "Caminho upstream duplicado.", path=item["path"])
        names.add(item["path"])
    return value


def verify_upstream(*, fetch: bool = False, snapshot: Path = SNAPSHOT) -> dict:
    manifest = read_manifest()
    for item in manifest["files"]:
        name = item["path"]
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise KhcomError("upstream_path", "Caminho upstream inválido.", path=name)
        path = snapshot / name
        if path.exists():
            try:
                content = read_file(path, item["size"])
            except OSError as error:
                raise KhcomError("upstream_read", "Falha ao ler fonte upstream.", path=name) from error
        elif fetch:
            try:
                with urllib.request.urlopen(RAW_BASE + name, timeout=30) as response:
                    content = response.read(item["size"] + 1)
            except (OSError, urllib.error.URLError) as error:
                raise KhcomError("upstream_download", "Falha no download da fonte fixada.", path=name, reason=str(error)) from error
        else:
            raise KhcomError("upstream_missing", "Fonte upstream ausente; use --fetch-upstream para obter a revisão fixada.", path=name)
        if len(content) != item["size"] or sha256(content) != item["sha256"]:
            raise KhcomError("upstream_integrity", "Fonte upstream divergente; o arquivo existente foi preservado.", path=name)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".khcom-fetch-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                # Atomic no-replace publication, including concurrent fetches.
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if sha256(read_file(path, item["size"])) != item["sha256"]:
                        raise KhcomError("upstream_integrity", "Fonte alterada durante aquisição.", path=name)
            finally:
                Path(temporary).unlink(missing_ok=True)
    return manifest


def _load_module(name: str, manifest: dict, snapshot: Path, siblings: dict | None = None) -> ModuleType:
    relative = f"tools/{name}.py"
    source = snapshot / relative
    expected = next(item for item in manifest["files"] if item["path"] == relative)
    content = read_file(source, expected["size"])
    if sha256(content) != expected["sha256"]:
        raise KhcomError("upstream_integrity", "O parser foi alterado durante a verificação.")
    # Compile exactly the verified bytes, never reuse an unchecked .pyc cache.
    module = ModuleType(f"khcom_pinned_{name}")
    module.__file__ = str(source)
    if siblings:
        def verified_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and name in siblings:
                return siblings[name]
            return builtins.__import__(name, globals, locals, fromlist, level)
        module.__dict__["__builtins__"] = {**vars(builtins), "__import__": verified_import}
    try:
        exec(compile(content, str(source), "exec"), module.__dict__)
    except ImportError as error:
        raise KhcomError("dependency_missing", "Instale as dependências fixadas do projeto no ambiente virtual.", reason=str(error)) from error
    return module


def load_textgen(*, fetch: bool = False, snapshot: Path = SNAPSHOT) -> ModuleType:
    return _load_module("textgen", verify_upstream(fetch=fetch, snapshot=snapshot), snapshot)


def read_source(name: str, *, manifest: dict | None = None, snapshot: Path = SNAPSHOT) -> bytes:
    """Return the verified bytes of one pinned source, including on rereads."""
    manifest = manifest or verify_upstream(snapshot=snapshot)
    expected = next((item for item in manifest["files"] if item["path"] == name), None)
    if expected is None:
        raise KhcomError("upstream_source", "Fonte não consta do manifesto fixado.", path=name)
    content = read_file(snapshot / name, expected["size"])
    if len(content) != expected["size"] or sha256(content) != expected["sha256"]:
        raise KhcomError("upstream_integrity", "Fonte alterada durante a leitura.", path=name)
    return content


def load_assetgen(*, fetch: bool = False, snapshot: Path = SNAPSHOT) -> ModuleType:
    manifest = verify_upstream(fetch=fetch, snapshot=snapshot)
    siblings = {name: _load_module(name, manifest, snapshot) for name in ("sprite_sheet", "m4a_assets")}
    return _load_module("assetgen", manifest, snapshot, siblings)


def load_asset_manifests(*, fetch: bool = False) -> tuple[ModuleType, list]:
    """The pinned acquisition owner selects the complete declared asset set."""
    owner = load_assetgen(fetch=fetch)
    paths = sorted(item["path"] for item in read_manifest()["files"]
                   if item["path"].startswith("config/assets/") and item["path"].endswith(".yaml"))
    return owner, [owner.Manifest(SNAPSHOT / path) for path in paths]


def upstream_rom_identity(snapshot: Path = SNAPSHOT) -> dict:
    """Read the declared target as a literal; never execute configure.py."""
    tree = ast.parse((snapshot / "configure.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VERSIONS" for t in node.targets):
            versions = ast.literal_eval(node.value)
            code, digest = versions["us"]
            return {"region": "us", "game_code": code, "sha1": digest, "commit": COMMIT}
    raise KhcomError("upstream_target", "O alvo US não foi encontrado no manifesto upstream.")
