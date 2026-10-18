"""Identificação única da ROM e admissão limitada de ZIP, sem extração implícita."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
from typing import Any
import zipfile
import zlib

from .errors import KhcomError

MIB = 1024 * 1024
MAX_ROM_BYTES = 32 * MIB
# Resource budgets, not assertions about the ZIP file format. Only one selected
# ROM is decoded; the total is checked before any compressed member is opened.
MAX_ARCHIVE_BYTES = 64 * MIB
MAX_EXPANDED_BYTES = 128 * MIB
MAX_ZIP_ENTRIES = 128
MAX_MEMBER_NAME = 1024
MAX_CENTRAL_DIRECTORY_BYTES = MAX_ZIP_ENTRIES * (46 + MAX_MEMBER_NAME + 65535 * 2)
MANIFEST = Path(__file__).resolve().parents[2] / "manifests" / "rom-us.json"


@dataclass(frozen=True)
class RomImage:
    data: bytes
    identity: dict[str, Any]
    source: Path
    member: str | None


def read_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KhcomError("invalid_manifest", "Não foi possível ler o manifesto da ROM.",
                         path=str(path), reason=str(exc)) from exc
    if not isinstance(result, dict) or not isinstance(result.get("sha256"), str):
        raise KhcomError("invalid_manifest", "Manifesto da ROM inválido.")
    if not re.fullmatch(r"[0-9a-f]{64}", result["sha256"]):
        raise KhcomError("invalid_manifest", "SHA-256 inválido no manifesto.")
    size = result.get("size")
    if type(size) is not int or not 192 <= size <= MAX_ROM_BYTES:
        raise KhcomError("invalid_manifest", "Tamanho inválido no manifesto.")
    if (not isinstance(result.get("id"), str) or not result["id"]
            or not isinstance(result.get("game_code"), str)
            or not re.fullmatch(r"[A-Z0-9]{4}", result["game_code"])
            or type(result.get("revision")) is not int
            or not 0 <= result["revision"] <= 255):
        raise KhcomError("invalid_manifest", "Identidade/revisão inválida no manifesto.")
    return result


def parse_header(data: bytes) -> dict[str, Any]:
    if len(data) < 192:
        raise KhcomError("truncated_rom", "O cabeçalho da ROM está incompleto.",
                         actual_size=len(data), minimum_size=192)
    return {
        "title": data[0xA0:0xAC].rstrip(b"\0").decode("ascii", errors="backslashreplace"),
        "game_code": data[0xAC:0xB0].decode("ascii", errors="backslashreplace"),
        "maker_code": data[0xB0:0xB2].decode("ascii", errors="backslashreplace"),
        "fixed_byte": data[0xB2],
        "unit_code": data[0xB3],
        "revision": data[0xBC],
        "checksum_stored": data[0xBD],
        "checksum_computed": (-sum(data[0xA0:0xBD]) - 0x19) & 0xFF,
        "entry_word_le": f"0x{struct.unpack_from('<I', data)[0]:08x}",
    }


def identify_bytes(data: bytes, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    expected = read_manifest() if expected is None else expected
    if not 192 <= len(data) <= MAX_ROM_BYTES:
        raise KhcomError("rom_size", "Tamanho de ROM não suportado.",
                         actual_size=len(data), expected_size=expected["size"])
    header = parse_header(data)
    identity = {
        "schema_version": 1, "rom_id": expected["id"], "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sha1": hashlib.sha1(data).hexdigest(),
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", "header": header,
    }
    mismatches = []
    if len(data) != expected["size"]:
        mismatches.append("size")
    if identity["sha256"] != expected["sha256"]:
        mismatches.append("sha256")
    for key in ("game_code", "revision"):
        if header[key] != expected[key]:
            mismatches.append(key)
    if header["fixed_byte"] != 0x96 or header["checksum_stored"] != header["checksum_computed"]:
        mismatches.append("header_integrity")
    if mismatches:
        # Keep observed identity separate from the supported revision label.
        identity["rom_id"] = None
        raise KhcomError("unsupported_rom", "A ROM não corresponde à revisão USA B8CE suportada.",
                         mismatches=mismatches, observed=identity,
                         expected={k: expected[k] for k in ("id", "size", "sha256")})
    return identity


def _inventory(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > MAX_ZIP_ENTRIES:
        raise KhcomError("zip_budget", "O ZIP excede o limite de entradas.",
                         count=len(entries), limit=MAX_ZIP_ENTRIES)
    names: set[str] = set()
    expanded = 0
    for entry in entries:
        name = entry.filename
        original = entry.orig_filename
        parts = name.rstrip("/").split("/")
        if (not name or name != original or "\x00" in original or len(name) > MAX_MEMBER_NAME
                or name.startswith("/") or "\\" in name or re.match(r"^[a-zA-Z]:", name)
                or any(p in ("", ".", "..") for p in parts)):
            raise KhcomError("unsafe_zip_path", "O ZIP contém um caminho não admitido.", member=original)
        if name in names:
            raise KhcomError("duplicate_zip_member", "O ZIP contém nomes duplicados.", member=name)
        names.add(name)
        kind = stat.S_IFMT(entry.external_attr >> 16)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind == stat.S_IFDIR and not entry.is_dir()):
            raise KhcomError("zip_member_type", "Links e entradas especiais não são admitidos.", member=name)
        if entry.flag_bits & 1:
            raise KhcomError("encrypted_zip", "ZIP criptografado não é suportado.", member=name)
        if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise KhcomError("zip_compression", "O método de compressão do ZIP não é suportado.", member=name)
        if entry.file_size > MAX_ROM_BYTES:
            raise KhcomError("zip_budget", "Uma entrada excede o limite de expansão.",
                             member=name, size=entry.file_size, limit=MAX_ROM_BYTES)
        expanded += entry.file_size
        if expanded > MAX_EXPANDED_BYTES:
            raise KhcomError("zip_budget", "A soma expandida do ZIP excede o orçamento.",
                             size=expanded, limit=MAX_EXPANDED_BYTES)
    return entries


def _check_zip_directory(stream: Any, size: int) -> None:
    """Bound metadata before ZipFile allocates its list of directory entries."""
    stream.seek(max(0, size - (65535 + 22)))
    tail = stream.read(65535 + 22)
    end = tail.rfind(b"PK\x05\x06")
    if end < 0 or end + 22 > len(tail):
        raise KhcomError("invalid_zip", "Diretório ZIP ausente ou truncado.")
    _, disk, start_disk, disk_count, count, directory_size, offset, comment = struct.unpack_from(
        "<4s4H2IH", tail, end)
    if end + 22 + comment != len(tail):
        raise KhcomError("invalid_zip", "O fim do ZIP diverge do tamanho declarado.")
    if count == 0xFFFF or directory_size == 0xFFFFFFFF or offset == 0xFFFFFFFF:
        raise KhcomError("zip64_unsupported", "ZIP64 não é admitido por este importador limitado.")
    if disk != 0 or start_disk != 0 or disk_count != count:
        raise KhcomError("split_zip", "ZIP dividido em volumes não é suportado.")
    if count > MAX_ZIP_ENTRIES or directory_size > MAX_CENTRAL_DIRECTORY_BYTES:
        raise KhcomError("zip_budget", "O diretório ZIP excede o orçamento de metadados.",
                         count=count, size=directory_size)
    end_offset = max(0, size - (65535 + 22)) + end
    if offset + directory_size != end_offset:
        raise KhcomError("invalid_zip", "O intervalo do diretório ZIP é inconsistente.")
    # Verify the declared number of headers as well: EOCD counts are untrusted.
    stream.seek(offset)
    remaining = directory_size
    actual = 0
    while remaining:
        header = stream.read(46)
        if len(header) != 46 or header[:4] != b"PK\x01\x02":
            raise KhcomError("invalid_zip", "Entrada truncada no diretório ZIP.")
        name_len, extra_len, comment_len = struct.unpack_from("<3H", header, 28)
        entry_size = 46 + name_len + extra_len + comment_len
        if name_len > MAX_MEMBER_NAME or entry_size > remaining:
            raise KhcomError("zip_budget", "Entrada do diretório ZIP excede os limites.")
        actual += 1
        if actual > MAX_ZIP_ENTRIES:
            raise KhcomError("zip_budget", "O ZIP excede o limite de entradas.")
        stream.seek(entry_size - 46, 1)
        remaining -= entry_size
    if actual != count:
        raise KhcomError("invalid_zip", "Contagem divergente no diretório ZIP.")
    stream.seek(0)


def _read_limited(stream: Any, expected_size: int) -> bytes:
    data = stream.read(expected_size + 1)
    if len(data) != expected_size:
        raise KhcomError("size_changed", "O tamanho lido diverge do tamanho declarado.",
                         expected=expected_size, actual=len(data))
    return data


def read_rom(path: str | Path, *, member: str | None = None,
             expected: dict[str, Any] | None = None) -> RomImage:
    source = Path(path).absolute()
    expected = read_manifest() if expected is None else expected
    try:
        # Keep one handle open across identification and reading; a pathname
        # replacement must not switch the bytes selected by this operation.
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(source, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise KhcomError("input_type", "Selecione um arquivo regular.", path=str(source))
            signature = stream.read(4)
            stream.seek(0)
            is_zip = signature.startswith(b"PK") or source.suffix.lower() == ".zip"
            if is_zip:
                if before.st_size > MAX_ARCHIVE_BYTES:
                    raise KhcomError("zip_budget", "O ZIP excede o tamanho de entrada admitido.",
                                     size=before.st_size, limit=MAX_ARCHIVE_BYTES)
                _check_zip_directory(stream, before.st_size)
                with zipfile.ZipFile(stream) as archive:
                    entries = _inventory(archive)
                    candidates = [e for e in entries if not e.is_dir() and e.filename.lower().endswith(".gba")]
                    if member is None:
                        if len(candidates) != 1:
                            raise KhcomError("rom_selection", "Selecione explicitamente uma ROM do ZIP.",
                                             candidates=[e.filename for e in candidates])
                        selected = candidates[0]
                    else:
                        selected = next((e for e in candidates if e.filename == member), None)
                        if selected is None:
                            raise KhcomError("rom_selection", "A entrada escolhida não é uma ROM candidata.",
                                             member=member, candidates=[e.filename for e in candidates])
                    if selected.file_size != expected["size"]:
                        raise KhcomError("rom_size", "A ROM do ZIP tem tamanho incompatível.",
                                         member=selected.filename, actual_size=selected.file_size,
                                         expected_size=expected["size"])
                    with archive.open(selected, "r") as decoded:
                        data = _read_limited(decoded, selected.file_size)
                    selected_member = selected.filename
            else:
                if member is not None:
                    raise KhcomError("rom_selection", "--member só se aplica a arquivos ZIP.")
                if before.st_size != expected["size"]:
                    raise KhcomError("rom_size", "A ROM tem tamanho incompatível.",
                                     actual_size=before.st_size, expected_size=expected["size"])
                data = _read_limited(stream, before.st_size)
                selected_member = None
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise KhcomError("input_changed", "O arquivo de entrada mudou durante a leitura.")
    except KhcomError:
        raise
    except (OSError, zipfile.BadZipFile, EOFError, RuntimeError, UnicodeError, zlib.error) as exc:
        raise KhcomError("input_read", "Não foi possível ler a entrada com integridade.",
                         path=str(source), reason=str(exc)) from exc
    identity = identify_bytes(data, expected)
    identity["input"] = {"path": str(source), "member": selected_member,
                         "container_size": before.st_size}
    return RomImage(data, identity, source, selected_member)
