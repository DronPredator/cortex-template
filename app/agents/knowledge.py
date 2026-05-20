"""Base de conocimiento por agente — documentos de referencia siempre en contexto.

Cada agente puede tener una carpeta `app/agents/knowledge/<agent_id>/` con
archivos `.md` que se concatenan al system prompt automáticamente.

Uso típico: catálogos, reglamentos, normas, manuales internos que el agente
DEBE consultar antes de responder. Equivalente al "Knowledge" de un Gem de
Google AI Studio.

Limitaciones intencionales:
- Solo se aceptan archivos `.md` (texto plano). Para PDFs, convertir primero.
- Se cargan todos los archivos de la carpeta (no hay filtrado por relevancia).
  Si la carpeta crece >500k tokens, migrar a un sistema de retrieval.
- Cache por mtime — editás un archivo y se aplica sin reiniciar.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.config import AGENT_KNOWLEDGE_DIR


# Cache: agent_id → (max_mtime_seen, content_concatenado)
_cache: dict[str, tuple[float, str]] = {}


def _agent_knowledge_dir(agent_id: str) -> Path:
    return AGENT_KNOWLEDGE_DIR / agent_id


def list_knowledge_files(agent_id: str) -> list[Path]:
    """Lista los archivos .md de conocimiento de un agente, ordenados por nombre.

    Excluye archivos que arrancan con `_` (convención para README, notas
    internas, drafts) y los que arrancan con `.` (ocultos).
    """
    d = _agent_knowledge_dir(agent_id)
    if not d.exists():
        return []
    return sorted(
        f for f in d.glob("*.md")
        if not f.name.startswith("_") and not f.name.startswith(".")
    )


def load_knowledge(agent_id: str) -> str:
    """Devuelve la concatenación de todos los archivos .md del agente.

    Si no hay archivos, devuelve string vacío. Si hay archivos, agrega un
    header navegable al inicio para que el modelo sepa de qué se trata.
    """
    files = list_knowledge_files(agent_id)
    if not files:
        return ""

    # Cache key: max mtime de todos los archivos. Si alguno cambió → rebuild.
    max_mtime = max(f.stat().st_mtime for f in files)
    cached = _cache.get(agent_id)
    if cached and cached[0] == max_mtime:
        return cached[1]

    parts: list[str] = [
        "",
        "═══════════════════════════════════════════════════════",
        "DOCUMENTOS DE REFERENCIA",
        "Consultá estos documentos cuando necesites datos exactos de tablas,",
        "normativas, especificaciones técnicas, fórmulas o valores tabulados.",
        "Citá siempre la fuente exacta (nombre de archivo + sección).",
        "═══════════════════════════════════════════════════════",
        "",
    ]
    total_bytes = 0
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("knowledge_file_read_failed | agent={} file={} err={}", agent_id, f.name, e)
            continue
        parts.append(f"## DOCUMENTO: {f.name}")
        parts.append("")
        parts.append(content)
        parts.append("")
        parts.append("---")
        parts.append("")
        total_bytes += len(content)

    result = "\n".join(parts)
    _cache[agent_id] = (max_mtime, result)
    logger.info(
        "knowledge_loaded | agent={} files={} bytes={}",
        agent_id, len(files), total_bytes,
    )
    return result


def invalidate_cache(agent_id: str | None = None) -> None:
    """Limpia el cache. Si agent_id es None, limpia todo."""
    if agent_id is None:
        _cache.clear()
    else:
        _cache.pop(agent_id, None)
