"""Log de auditoría dedicado para acciones administrativas.

A diferencia del log general (loguru) que mezcla debug, info y warnings,
el audit log es append-only y solo registra acciones de admin con valor
forense:

- Quién (actor)
- Qué (action)
- Sobre qué (target, opcional)
- Cuándo (timestamp UTC)
- Desde dónde (IP del cliente, si está disponible)
- Metadata adicional (qué cambió, valores anteriores, etc.)

Reglas:
- Append-only: nunca se modifican entradas existentes
- Una línea = un evento (JSONL)
- Sin info sensible (no passwords, no tokens completos)

Eventos típicos:
- user_created, user_deleted, user_password_changed
- agent_created, agent_updated, agent_deleted, agent_prompt_saved
- model_changed, system_prompt_updated, auto_route_toggled
- memory_refreshed, conversations_purged
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from loguru import logger

from app.config import AUDIT_LOG_PATH


_lock = threading.Lock()


def _safe_ip(request: Request | None) -> str:
    if request is None:
        return ""
    try:
        # Si hay reverse proxy, X-Forwarded-For es la fuente real
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()[:64]
        client = request.client
        return (client.host if client else "")[:64]
    except Exception:
        return ""


def audit_event(
    actor: str,
    action: str,
    target: str = "",
    request: Request | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Append una entrada al audit log.

    Args:
        actor: usuario que realiza la acción (ej: "admin", "Fide1")
        action: nombre del evento (ej: "user_created", "agent_deleted")
        target: sobre qué recurso (ej: "user:nuevo_user", "agent:steamy_seg")
        request: opcional, FastAPI Request para extraer IP/UA
        meta: dict adicional con detalles (cambios, valores, etc.)
    """
    entry: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": (actor or "(anónimo)")[:64],
        "action": action[:64],
        "target": (target or "")[:200],
        "ip": _safe_ip(request),
    }
    if meta:
        # Truncar valores muy largos en meta (defensive)
        clean_meta = {}
        for k, v in meta.items():
            k = str(k)[:64]
            if isinstance(v, str):
                clean_meta[k] = v[:500]
            elif isinstance(v, (int, float, bool)) or v is None:
                clean_meta[k] = v
            else:
                clean_meta[k] = str(v)[:500]
        entry["meta"] = clean_meta

    try:
        with _lock:
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # No tirar el endpoint si falla la auditoría — solo loguear
        logger.error("audit_event_failed | {} | entry={}", e, entry)


def read_audit_events(limit: int = 100) -> list[dict]:
    """Lee los últimos N eventos del audit log (más recientes primero)."""
    if not AUDIT_LOG_PATH.exists():
        return []
    limit = max(1, min(int(limit), 1000))
    out: list[dict] = []
    try:
        lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
                if len(out) >= limit:
                    break
            except Exception:
                pass
    except Exception as e:
        logger.error("read_audit_events_failed | {}", e)
    return out
