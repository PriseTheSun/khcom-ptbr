"""Pacotes sem dados de jogo, com inventário fechado e fontes para reconstrução."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import zipfile

from .errors import KhcomError
from .io import read_file

MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 768 * 1024 * 1024
MAX_FILES = 10000
FORBIDDEN = {".gba", ".sav", ".srm", ".bps", ".khcs", ".dmp"}
ROLES = {"executable", "bundle-metadata", "signature", "notices", "sources", "sbom", "instructions"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise KhcomError("package_path", "Caminho inválido no inventário.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in value.split("/")) or ":" in value:
        raise KhcomError("package_path", "Caminho não relativo/canônico no inventário.", path=value)
    return path


def architecture(data: bytes) -> list[str]:
    """Read architecture identities; platform tools validate dynamic dependencies."""
    machine = {0x1000007: "x86_64", 0x100000C: "arm64"}
    if data[:4] == b"\xcf\xfa\xed\xfe" and len(data) >= 32:
        return [machine.get(struct.unpack_from("<I", data, 4)[0], "unknown")]
    if data[:4] in {b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"} and len(data) >= 8:
        count = struct.unpack_from(">I", data, 4)[0]
        width = 20 if data[:4] == b"\xca\xfe\xba\xbe" else 32
        if not 1 <= count <= 16 or 8 + count * width > len(data):
            raise KhcomError("package_macho", "Cabeçalho universal inválido.")
        result, ranges = [], []
        for index in range(count):
            start = 8 + index * width
            cpu = struct.unpack_from(">I", data, start)[0]
            offset, size = struct.unpack_from(">II" if width == 20 else ">QQ", data, start + 8)
            if offset < 8 + count * width or size < 32 or offset + size > len(data):
                raise KhcomError("package_macho", "Slice excede o executável.")
            if any(offset < b and a < offset + size for a, b in ranges):
                raise KhcomError("package_macho", "Slices sobrepostas.")
            ranges.append((offset, offset + size))
            name = machine.get(cpu, "unknown")
            if data[offset:offset + 4] != b"\xcf\xfa\xed\xfe" or architecture(data[offset:offset + size]) != [name] or name in result:
                raise KhcomError("package_macho", "Identidade da slice diverge do cabeçalho.")
            result.append(name)
        return sorted(result)
    if data[:2] == b"MZ" and len(data) >= 64:
        pe = struct.unpack_from("<I", data, 60)[0]
        if pe + 24 <= len(data) and data[pe:pe + 4] == b"PE\0\0":
            return [{0x8664: "x86_64", 0xaa64: "arm64"}.get(struct.unpack_from("<H", data, pe + 4)[0], "unknown")]
    raise KhcomError("package_executable", "Formato executável não reconhecido.")


def audit(root: Path, manifest: dict) -> dict:
    if manifest.get("schema_version") != 1 or manifest.get("kind") != "desktop-without-game-data":
        raise KhcomError("package_schema", "Manifesto de pacote incompatível.")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
        raise KhcomError("package_inventory", "Inventário vazio ou excessivo.")
    expected, total, roles = {}, 0, set()
    for row in entries:
        if not isinstance(row, dict):
            raise KhcomError("package_inventory", "Item de inventário inválido.")
        name = str(relative(row.get("path")))
        if name in expected or name == "package-manifest.json" or row.get("role") not in ROLES:
            raise KhcomError("package_inventory", "Item duplicado, reservado ou sem papel permitido.", path=name)
        if PurePosixPath(name).suffix.lower() in FORBIDDEN or any(p.lower() in {"private", "cache", "saves"} for p in PurePosixPath(name).parts):
            raise KhcomError("package_game_data", "Dados privados não entram no pacote público.", path=name)
        expected[name] = row
        roles.add(row["role"])
    actual = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise KhcomError("package_symlink", "O pacote não admite links.", path=str(path))
        if path.is_file() and path != root / "package-manifest.json":
            name = path.relative_to(root).as_posix()
            if name not in expected:
                raise KhcomError("package_extra", "Arquivo fora da allowlist.", path=name)
            data = read_file(path, min(MAX_FILE, MAX_TOTAL - total))
            total += len(data)
            row = expected[name]
            if row.get("size") != len(data) or row.get("sha256") != digest(data):
                raise KhcomError("package_digest", "Conteúdo diverge do inventário.", path=name)
            if len(data) == 33554432 and data[0xac:0xb0] == b"B8CE":
                raise KhcomError("package_game_data", "Cartucho comercial detectado no pacote.", path=name)
            if data.startswith(b"BPS1"):
                raise KhcomError("package_game_data", "Este perfil público não admite patches.", path=name)
            if row["role"] == "executable" and architecture(data) != sorted(manifest.get("architectures", [])):
                raise KhcomError("package_architecture", "Arquiteturas divergem do pacote.")
            actual[name] = row
    if set(actual) != set(expected):
        raise KhcomError("package_missing", "Arquivo obrigatório ausente.", missing=sorted(set(expected) - set(actual)))
    if not {"executable", "notices", "sources", "sbom", "instructions"} <= roles:
        raise KhcomError("package_obligations", "Faltam fontes, avisos ou instruções de reconstrução.")
    return {"schema_version": 1, "audit_passed": True, "files": len(actual), "bytes": total,
            "manifest_sha256": digest(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()),
            "game_payload": "absent-by-packager-allowlist", "release_approved": False,
            "limitations": ["Hashes e allowlist não substituem revisão de proveniência do código.",
                            "Não comprova assinatura, QA de plataforma ou tradução completa."]}


def deterministic_zip(path: Path, entries: list[tuple[str, bytes, int]]) -> None:
    if path.exists():
        raise KhcomError("output_exists", "O arquivo de saída já existe.", path=str(path))
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        seen = set()
        for name, data, mode in sorted(entries):
            relative(name)
            if name in seen:
                raise KhcomError("package_inventory", "Entrada ZIP duplicada.")
            seen.add(name)
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
