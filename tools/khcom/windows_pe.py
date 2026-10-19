"""Bounded PE import inspection; never loads or executes a DLL.

This checks declared normal/delay imports, not arbitrary LoadLibrary calls or
Windows loader equivalence. RVA mappings exclude unbacked virtual zero-fill.
"""
from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

from .errors import KhcomError
from .io import read_file
from .package import audit

MAX_PE = 256 * 1024 * 1024
MAX_IMPORTS = 4096
DLL_NAME = re.compile(r"[A-Za-z0-9_+.-]{1,240}\.dll", re.I)
API_SET = re.compile(r"(?:api|ext)-ms-[a-z0-9-]+\.dll", re.I)
EXTERNAL_CRT = re.compile(r"(?:vcruntime\d.*|msvcp\d.*|msvcr\d.*|concrt\d.*|ucrtbased)\.dll", re.I)


def pe_imports(data: bytes) -> dict:
    def fail(reason: str):
        raise KhcomError("pe_format", reason)

    def unpack(fmt: str, offset: int):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(data):
            fail("Estrutura PE truncada.")
        return struct.unpack_from(fmt, data, offset)

    if not 64 <= len(data) <= MAX_PE or data[:2] != b"MZ":
        fail("Cabeçalho DOS ausente ou arquivo fora do limite.")
    pe = unpack("<I", 60)[0]
    if pe < 64 or data[pe:pe + 4] != b"PE\0\0":
        fail("Assinatura PE inválida.")
    machine, count, _, _, _, optional_size, _ = unpack("<HHIIIHH", pe + 4)
    if machine not in {0x14C, 0x8664, 0xAA64} or not 1 <= count <= 96:
        fail("Máquina ou número de seções PE não suportado.")
    optional = pe + 24
    magic = unpack("<H", optional)[0]
    if magic == 0x10B:
        directories, number_offset, image_base = 96, 92, unpack("<I", optional + 28)[0]
    elif magic == 0x20B:
        directories, number_offset, image_base = 112, 108, unpack("<Q", optional + 24)[0]
    else:
        fail("OptionalHeader não é PE32/PE32+.")
    if optional_size < directories or optional + optional_size + 40 * count > len(data):
        fail("OptionalHeader/seções truncados.")
    directory_count = unpack("<I", optional + number_offset)[0]
    if directory_count > (optional_size - directories) // 8:
        fail("NumberOfRvaAndSizes excede OptionalHeader.")
    header_size = unpack("<I", optional + 60)[0]
    if not optional + optional_size + 40 * count <= header_size <= len(data):
        fail("SizeOfHeaders inválido.")
    mappings = [(0, header_size, 0, header_size)]
    raw_ranges = [(0, header_size)]
    for i in range(count):
        pos = optional + optional_size + 40 * i
        virtual_size, rva, raw_size, raw = unpack("<IIII", pos + 8)
        extent = max(virtual_size, raw_size)
        if rva + extent > 0x100000000 or raw + raw_size > len(data):
            fail("Seção PE excede o arquivo/espaço RVA.")
        if extent and any(rva < b and a < rva + extent for a, b, _, _ in mappings):
            fail("Seções PE têm RVAs ambíguos.")
        if raw_size and any(raw < b and a < raw + raw_size for a, b in raw_ranges):
            fail("Seções PE têm bytes sobrepostos.")
        if extent:
            mappings.append((rva, rva + extent, raw, raw_size))
        if raw_size:
            raw_ranges.append((raw, raw + raw_size))

    def locate(rva: int, size: int) -> int:
        if rva < 0 or size < 0 or rva + size > 0x100000000:
            fail("RVA inválido.")
        candidates = [(a, raw, backed) for a, b, raw, backed in mappings
                      if a <= rva and rva + size <= b and rva - a + size <= backed]
        if len(candidates) != 1:
            fail("RVA sem bytes no arquivo ou com mapeamento ambíguo.")
        start, raw, _ = candidates[0]
        return raw + rva - start

    def dll_name(rva: int) -> str:
        name = bytearray()
        for index in range(245):
            value = data[locate(rva + index, 1)]
            if not value:
                try:
                    result = name.decode("ascii")
                except UnicodeDecodeError:
                    fail("Nome de DLL não ASCII.")
                if not DLL_NAME.fullmatch(result) or result.startswith(".") or ".." in result:
                    fail("Nome de DLL não é um basename permitido.")
                return result
            name.append(value)
        fail("Nome de DLL não terminado ou excessivo.")

    result = {"machine": {0x14C: "x86", 0x8664: "x86_64", 0xAA64: "arm64"}[machine],
              "format": "PE32+" if magic == 0x20B else "PE32", "imports": [], "delay_imports": []}
    for directory, width, label in [(1, 20, "imports"), (13, 32, "delay_imports")]:
        if directory >= directory_count:
            continue
        rva, size = unpack("<II", optional + directories + 8 * directory)
        if rva == size == 0:
            continue
        if not rva or size < width or size // width > MAX_IMPORTS + 1:
            fail("Diretório de imports inválido/excessivo.")
        locate(rva, size)
        terminated = False
        for index in range(size // width):
            row = unpack("<" + "I" * (width // 4), locate(rva + width * index, width))
            if not any(row):
                terminated = True
                break
            if index >= MAX_IMPORTS:
                fail("Imports excedem limite.")
            if directory == 13:
                if row[0] not in {0, 1}:
                    fail("Atributos delay-import desconhecidos.")
                name_rva = row[1] if row[0] == 1 else row[1] - image_base
            else:
                name_rva = row[3]
            if name_rva <= 0:
                fail("Import não possui RVA de nome válido.")
            result[label].append(dll_name(name_rva))
        if not terminated:
            fail("Diretório de imports sem descritor nulo no tamanho declarado.")
    return result


def audit_windows(package: Path, manifest: dict, system32: Path) -> dict:
    """Verify app-local closure and direct System32/API-set resolution only."""
    checked = audit(package, manifest)
    if manifest.get("platform") != "windows" or manifest.get("architectures") != ["x86_64"]:
        raise KhcomError("pe_platform", "Este ensaio exige pacote Windows x86_64.")
    if not system32.is_dir() or system32.is_symlink():
        raise KhcomError("pe_system", "System32 precisa ser um diretório explícito regular.")
    entries = {row["path"].lower(): row for row in manifest["files"]}
    if len(entries) != len(manifest["files"]):
        raise KhcomError("pe_inventory", "Inventário tem colisão de nomes no Windows.")
    pending = [row["path"] for row in manifest["files"] if row["role"] == "executable"]
    inspected, resolutions, failures = {}, [], []
    while pending:
        relative = pending.pop()
        if relative.lower() in inspected:
            continue
        if len(inspected) >= 128:
            raise KhcomError("pe_limit", "Fechamento de DLLs locais excede limite.")
        info = pe_imports(read_file(package / relative, MAX_PE))
        inspected[relative.lower()] = info
        if info["machine"] != "x86_64":
            failures.append({"file": relative, "reason": "architecture"})
        for label in ("imports", "delay_imports"):
            for name in info[label]:
                row = {"consumer": relative, "kind": label, "dll": name}
                if EXTERNAL_CRT.fullmatch(name):
                    row["resolution"] = "forbidden-external-vc-runtime"
                    failures.append(row.copy())
                elif name.lower() in entries:
                    row["resolution"] = "audited-app-local"
                    row["sha256"] = entries[name.lower()]["sha256"]
                    pending.append(entries[name.lower()]["path"])
                elif API_SET.fullmatch(name):
                    row["resolution"] = "api-set-contract-not-a-file"
                else:
                    target = system32 / name
                    if target.is_file() and not target.is_symlink():
                        raw = read_file(target, MAX_PE)
                        row.update(resolution="system32-file", path=str(target), size=len(raw),
                                   sha256=hashlib.sha256(raw).hexdigest())
                    else:
                        row["resolution"] = "unresolved"
                        failures.append(row.copy())
                resolutions.append(row)
    return {"schema_version": 1, "audit_passed": not failures,
            "package_manifest_sha256": checked["manifest_sha256"], "images": inspected,
            "dependencies": resolutions, "failures": failures, "release_approved": False,
            "limitations": ["System32 location/hash does not attest Microsoft signature or a clean host.",
                            "API-set contracts require the real Windows loader startup check.",
                            "System DLL import closure and arbitrary LoadLibrary calls are not proven."]}
