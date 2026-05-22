"""Rate limiting con slowapi.

Anti brute-force en login y anti abuse en endpoints costosos.

Configuración:
- Login endpoints: 5 intentos por minuto por IP (suficiente para gente
  legítima que se confunde, insuficiente para brute-force).
- Chat endpoints: 30 mensajes por minuto por user (controla costo y abuso).

Si querés desactivar para tests, setear `RATE_LIMIT_ENABLED=false` en env.
"""

from __future__ import annotations

import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_by_ip(request: Request) -> str:
    """Key del rate-limit. Usa la IP del cliente respetando X-Forwarded-For
    si está detrás de un reverse proxy (configurar trusted_proxies si es el caso)."""
    return get_remote_address(request)


_enabled = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() != "false"

limiter = Limiter(
    key_func=_key_by_ip,
    enabled=_enabled,
    # Almacenamiento en memoria — OK para single-process. Si escalás a múltiples
    # workers, migrar a Redis con `storage_uri="redis://..."`
    storage_uri="memory://",
    # Keep limits active without requiring every decorated endpoint to accept
    # an explicit Starlette Response object. With headers_enabled=True, slowapi
    # can raise 500s on plain dict/streaming responses.
    headers_enabled=False,
)


# Reglas predefinidas (uso vía decorador @limiter.limit())
LOGIN_LIMIT = "5/minute"      # 5 intentos de login por IP por minuto
CHAT_LIMIT = "30/minute"      # 30 mensajes por IP por minuto
ADMIN_ACTION_LIMIT = "60/minute"  # acciones admin (CRUD users, agents, etc.)
