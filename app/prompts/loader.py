"""Carga prompts desde archivos .md en disco con caché en memoria.

Permite editarlos sin reiniciar el server: si el archivo cambia, se recarga.
"""

from __future__ import annotations

from pathlib import Path

from app.config import PROMPTS_DIR


_cache: dict[str, tuple[float, str]] = {}  # name → (mtime, content)


def _load(name: str) -> str:
    """Carga un prompt por nombre (sin extensión). Cachea por mtime."""
    path: Path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt no encontrado: {path}")
    mtime = path.stat().st_mtime
    cached = _cache.get(name)
    if cached and cached[0] == mtime:
        return cached[1]
    content = path.read_text(encoding="utf-8")
    _cache[name] = (mtime, content)
    return content


def system_prompt(n_items: int, custom: str = "") -> str:
    """Prompt principal del agente. Inyecta n_items y opcional custom rules."""
    base = _load("system").format(n_items=n_items)
    if custom:
        base += (
            "\n\n## ⚡ INSTRUCCIONES PERSONALIZADAS DEL ADMINISTRADOR (PRIORIDAD MÁXIMA)\n"
            "Las siguientes son reglas adicionales definidas por el administrador del sistema. "
            "TENÉS QUE SEGUIRLAS en cada respuesta, junto con las reglas de comportamiento anteriores. "
            "Si hay conflicto entre estas y las reglas base, prevalecen estas:\n\n"
            f"{custom}"
        )
    return base


def admin_prompt(admin_name: str, n_items: int, custom_prompt: str, memory_summary: str) -> str:
    """Prompt del chat admin (configuración conversacional del agente)."""
    return _load("admin").format(
        admin_name=admin_name,
        n_items=n_items,
        custom_prompt=custom_prompt or "(sin personalización activa)",
        memory_summary=memory_summary,
    )
