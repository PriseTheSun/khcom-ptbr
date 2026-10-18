"""Bounded BPS1 codec. Only the application admits supported commercial ROMs.

Format: byuu's public-domain BPS specification, mirrored in Sir-Walrus/Flips.
The generator is linear and deterministic; it deliberately makes no provenance
claim about literal bytes. Distribution requires a separate literal audit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
import zlib

from .errors import KhcomError

MAX_IMAGE = 32 * 1024 * 1024
MAX_PATCH = 64 * 1024 * 1024
MAX_METADATA = 64 * 1024
# Budgets bound parser CPU and the size of the provenance report, beyond the
# byte budgets. Patches exceeding these limits are unsupported, not malformed.
MAX_ACTIONS = 262144
MAX_LITERAL_RECORDS = 65536


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _crc(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _number(value: int) -> bytes:
    if not 0 <= value < 1 << 64:
        raise KhcomError("bps_integer", "Inteiro BPS fora do intervalo admitido.")
    result = bytearray()
    while True:
        low = value & 127
        value >>= 7
        if value == 0:
            result.append(low | 128)
            return bytes(result)
        result.append(low)
        value -= 1


@dataclass
class Reader:
    data: bytes
    position: int = 4

    def take(self, size: int) -> bytes:
        if size < 0 or self.position + size > len(self.data) - 12:
            raise KhcomError("bps_truncated", "Comando BPS excede o corpo do patch.")
        result = self.data[self.position:self.position + size]
        self.position += size
        return result

    def number(self) -> int:
        value, shift = 0, 1
        for _ in range(10):
            byte = self.take(1)[0]
            value += (byte & 127) * shift
            if value >= 1 << 64:
                break
            if byte & 128:
                return value
            shift <<= 7
            value += shift
        raise KhcomError("bps_integer", "Inteiro BPS excede 64 bits.")


def apply(source: bytes, patch: bytes, *, expected_target_sha256: str | None = None) -> bytes:
    if len(source) > MAX_IMAGE or not 19 <= len(patch) <= MAX_PATCH:
        raise KhcomError("bps_budget", "Entrada BPS excede os limites admitidos.")
    if patch[:4] != b"BPS1":
        raise KhcomError("bps_signature", "Assinatura BPS1 ausente.")
    source_crc, target_crc, patch_crc = struct.unpack_from("<III", patch, len(patch) - 12)
    if _crc(patch[:-4]) != patch_crc:
        raise KhcomError("bps_patch_crc", "CRC do patch inválido.")
    if _crc(source) != source_crc:
        raise KhcomError("bps_source_crc", "CRC da origem diverge do patch.")
    reader = Reader(patch)
    source_size, target_size, metadata_size = reader.number(), reader.number(), reader.number()
    if source_size != len(source):
        raise KhcomError("bps_source_size", "Tamanho da origem diverge do patch.")
    if target_size > MAX_IMAGE or metadata_size > MAX_METADATA:
        raise KhcomError("bps_budget", "Destino/metadados excedem o orçamento BPS.")
    reader.take(metadata_size)
    output = bytearray()
    source_relative = target_relative = 0
    action_count = 0
    while reader.position < len(patch) - 12:
        action_count += 1
        if action_count > MAX_ACTIONS:
            raise KhcomError("bps_budget", "O patch excede o orçamento de comandos.")
        command = reader.number()
        action, length = command & 3, (command >> 2) + 1
        start = len(output)
        if start + length > target_size:
            raise KhcomError("bps_target_bounds", "Comando excede o tamanho do destino.")
        if action == 0:
            if start + length > len(source):
                raise KhcomError("bps_source_bounds", "Leitura excede a origem.")
            output.extend(source[start:start + length])
        elif action == 1:
            output.extend(reader.take(length))
        else:
            encoded_offset = reader.number()
            delta = (encoded_offset >> 1) * (-1 if encoded_offset & 1 else 1)
            if action == 2:
                source_relative += delta
                if source_relative < 0 or source_relative + length > len(source):
                    raise KhcomError("bps_source_bounds", "Cópia excede a origem.")
                output.extend(source[source_relative:source_relative + length])
                source_relative += length
            else:
                target_relative += delta
                if target_relative < 0 or target_relative >= start:
                    raise KhcomError("bps_copy_bounds", "Cópia referencia bytes ainda não produzidos.")
                # Overlap repeats an already written period, avoiding a Python
                # iteration for each byte in a long self-referential copy.
                period = bytes(output[target_relative:min(start, target_relative + length)])
                repetitions, remainder = divmod(length, len(period))
                output.extend(period * repetitions)
                output.extend(period[:remainder])
                target_relative += length
    if len(output) != target_size:
        raise KhcomError("bps_target_size", "O patch não produz todo o destino declarado.")
    if _crc(output) != target_crc:
        raise KhcomError("bps_target_crc", "CRC do destino inválido.")
    if expected_target_sha256 is not None and digest(output) != expected_target_sha256:
        raise KhcomError("bps_target_digest", "SHA-256 do destino diverge do manifesto.")
    return bytes(output)


def create(source: bytes, target: bytes, metadata: bytes = b"") -> tuple[bytes, dict]:
    if max(len(source), len(target)) > MAX_IMAGE or len(metadata) > MAX_METADATA:
        raise KhcomError("bps_budget", "Origem, destino ou metadados excedem o orçamento BPS.")
    result = bytearray(b"BPS1" + _number(len(source)) + _number(len(target))
                       + _number(len(metadata)) + metadata)
    offset = 0
    literals = []
    action_count = 0
    while offset < len(target):
        action_count += 1
        if action_count > MAX_ACTIONS:
            raise KhcomError("bps_budget", "A diferença excede o orçamento de comandos.")
        same = offset < len(source) and source[offset] == target[offset]
        end = offset + 1
        if same:
            # Coalesce unchanged pages in C before handling boundary bytes.
            while end + 4096 <= min(len(source), len(target)) and source[end:end + 4096] == target[end:end + 4096]:
                end += 4096
            while end < min(len(source), len(target)) and source[end] == target[end]:
                end += 1
            result.extend(_number((end - offset - 1) << 2))
        else:
            if len(literals) >= MAX_LITERAL_RECORDS:
                raise KhcomError("bps_budget", "A diferença excede o orçamento de auditoria de literais.")
            while end < len(target) and (end >= len(source) or source[end] != target[end]):
                end += 1
            result.extend(_number(((end - offset - 1) << 2) | 1))
            patch_start = len(result)
            result.extend(target[offset:end])
            literals.append({"target_start": offset, "length": end - offset,
                             "patch_start": patch_start, "sha256": digest(target[offset:end]),
                             "provenance": "unreviewed"})
        offset = end
    result.extend(struct.pack("<II", _crc(source), _crc(target)))
    result.extend(struct.pack("<I", _crc(result)))
    patch = bytes(result)
    if len(patch) > MAX_PATCH:
        raise KhcomError("bps_budget", "Patch produzido excede o orçamento admitido.")
    report = {"schema_version": 1, "format": "BPS1", "generator": "khcom-linear-v1",
              "source_sha256": digest(source), "target_sha256": digest(target),
              "patch_sha256": digest(patch), "source_size": len(source),
              "target_size": len(target), "patch_size": len(patch),
              "distribution_approved": False, "literals": literals}
    return patch, report
