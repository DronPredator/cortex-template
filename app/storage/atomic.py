"""Helpers para escrituras atómicas de archivos.

`atomic_write` escribe a un .tmp y renombra. Si la app crashea a mitad
de escritura, el archivo original queda intacto.
"""

from __future__ import annotations

import threading
from pathlib import Path

# Lock global compartido para evitar dos threads escribiendo al mismo archivo
_file_lock = threading.Lock()


def atomic_write(path: Path, content: str) -> None:
    """Escribe `content` a `path` de forma atómica vía tmp + rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _file_lock:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _file_lock:
        tmp.write_bytes(content)
        tmp.replace(path)
