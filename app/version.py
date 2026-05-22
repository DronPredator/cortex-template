"""Versión del proyecto — lee del archivo `VERSION` en la raíz.

Single source of truth. Para subir versión:
1. Editar el archivo `VERSION` (un único string tipo `1.2.3`)
2. Agregar entrada al CHANGELOG.md
3. Commit + tag: `git tag -a v1.2.3 -m "..."`
4. `git push --tags`

El número se expone en:
- FastAPI `app.version` (visible en /docs y /openapi.json)
- /api/version endpoint público (para monitoring/healthcheck)
- Logs al startup
"""

from __future__ import annotations

from pathlib import Path


_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
_FALLBACK = "0.0.0+unknown"


def _read_version() -> str:
    try:
        text = _VERSION_FILE.read_text(encoding="utf-8").strip()
        # Tomar solo la primera línea no vacía, sin comentarios
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    except Exception:
        pass
    return _FALLBACK


__version__ = _read_version()
