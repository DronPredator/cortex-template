"""Helpers de seguridad para manejo de archivos subidos.

Evita ataques tipo:
- Path traversal: un usuario sube "../../../etc/passwd" y escribe fuera del
  directorio destino.
- Reserved names en Windows: CON, PRN, AUX, NUL, COM1..9, LPT1..9.
- Caracteres ilegales en filesystems (\\ / : * ? " < > |).
- Hidden files: archivos que empiezan con punto.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


_FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def safe_filename(name: str, *, max_len: int = 120, default: str = "archivo") -> str:
    """Devuelve un filename seguro a partir de uno arbitrario.

    - Quita componentes de path (basename only)
    - Normaliza Unicode (NFKD)
    - Reemplaza caracteres ilegales con `_`
    - Bloquea hidden files (empiezan con `.`)
    - Bloquea nombres reservados de Windows
    - Trunca a max_len

    Si después del saneamiento el nombre queda vacío, devuelve `default`.
    """
    if not isinstance(name, str):
        name = str(name or "")

    # Solo nos quedamos con el último componente — bloquea path traversal absoluto
    name = Path(name.replace("\\", "/")).name
    # Normalizar Unicode (NFKD descompone caracteres compuestos)
    name = unicodedata.normalize("NFKD", name)
    # Reemplazar caracteres ilegales
    name = _FORBIDDEN_CHARS.sub("_", name)
    # Quitar . y espacios al inicio/fin (Windows borra el . al final)
    name = name.strip(". ").strip()

    if not name:
        return default

    # Reserved names: si el stem (sin extensión) es reservado, prefijar
    stem, _, ext = name.partition(".")
    if stem.upper() in _WIN_RESERVED:
        name = f"_{name}"

    # Limitar largo respetando la extensión
    if len(name) > max_len:
        stem, _, ext = name.rpartition(".")
        if stem and ext and len(ext) <= 8:
            keep = max_len - len(ext) - 1
            name = stem[:max(1, keep)] + "." + ext
        else:
            name = name[:max_len]

    return name or default


def is_within_dir(target: Path, base: Path) -> bool:
    """Verifica que `target` esté dentro de `base` (resolviendo symlinks).

    Útil como guard extra después de construir una ruta destino con un
    filename que vino del usuario.
    """
    try:
        target_resolved = target.resolve()
        base_resolved = base.resolve()
        return base_resolved in target_resolved.parents or target_resolved == base_resolved
    except Exception:
        return False
