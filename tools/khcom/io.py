"""Publicação exclusiva de saídas; a origem nunca é um destino implícito."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from .errors import KhcomError


def read_file(path: str | Path, maximum: int) -> bytes:
    """Read one regular file with a byte budget and detect concurrent mutation."""
    source = Path(path).absolute()
    try:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(source, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise KhcomError("input_type", "Selecione um arquivo regular.", path=str(source))
            if before.st_size > maximum:
                raise KhcomError("input_budget", "Arquivo excede o orçamento de leitura.",
                                 path=str(source), size=before.st_size, maximum=maximum)
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            if len(data) != before.st_size or (before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_mtime_ns, after.st_ctime_ns):
                raise KhcomError("input_changed", "Arquivo mudou durante a leitura.", path=str(source))
            return data
    except OSError as exc:
        raise KhcomError("input_read", "Não foi possível ler o arquivo.",
                         path=str(source), reason=str(exc)) from exc


def write_new(path: str | Path, data: bytes) -> None:
    target = Path(path).absolute()
    if target.exists() or target.is_symlink():
        raise KhcomError("output_exists", "O destino já existe; escolha um novo caminho.", path=str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".khcom-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # An atomic hard link creates the target only if it is still absent.
        # It cannot clobber a file created concurrently after the initial check.
        os.link(temporary, target)
    except OSError as exc:
        raise KhcomError("output_write", "Não foi possível publicar a saída.",
                         path=str(target), reason=str(exc)) from exc
    finally:
        try:
            os.unlink(temporary)
        except OSError as exc:
            raise KhcomError("cleanup_failed", "A saída temporária requer nova tentativa de limpeza.",
                             temporary=temporary, target=str(target), reason=str(exc)) from exc


def write_json_new(path: str | Path, value: Any) -> None:
    write_new(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
