"""Middleware que limita el tamaño del body por endpoint.

Defensa básica contra abuso: alguien que mande un body de 100MB a /api/login
puede consumirte la memoria del servidor. Estos límites cortan esos abusos
antes de que el handler reciba los datos.

Política:
- Endpoints de login y auth: 4 KB (más que suficiente para un username +
  password razonable; sirve para detectar abusos obvios).
- Endpoints de chat: 5 MB (deja margen para mensajes con system_context
  cargado de documentos extraídos).
- Endpoints admin: 200 KB (suficiente para prompts largos).
- Endpoint de upload: el `settings.max_upload_bytes` ya lo controla.
- Resto: 1 MB default razonable.

Si el body excede, devuelve 413 Payload Too Large.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# (path_prefix, max_bytes) — orden importa, se evalúa la primera coincidencia.
# Reglas más específicas (paths más largos) PRIMERO.
_LIMITS: list[tuple[str, int]] = [
    ("/api/login", 4 * 1024),
    ("/api/admin/login", 4 * 1024),
    ("/api/chat/stream", 5 * 1024 * 1024),
    ("/api/admin/chat/stream", 5 * 1024 * 1024),
    ("/api/upload-document", 30 * 1024 * 1024),  # cubre el max_upload_bytes
    # Upload de knowledge files (multipart): hasta 16 MB para cubrir PDFs grandes
    # con el overhead del multipart encoding. El handler cap a 15 MB el contenido.
    ("/api/admin/agents/", 16 * 1024 * 1024),
    ("/api/admin/agents", 200 * 1024),  # listado/CRUD (JSON pequeño)
    ("/api/admin/system-prompt", 200 * 1024),
    ("/api/admin/", 200 * 1024),
    ("/api/", 1 * 1024 * 1024),
]


def _limit_for(path: str) -> int | None:
    for prefix, lim in _LIMITS:
        if path.startswith(prefix):
            return lim
    return None  # sin límite (assets estáticos, /docs, etc.)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        lim = _limit_for(request.url.path)
        if lim is not None:
            cl = request.headers.get("content-length")
            if cl:
                try:
                    size = int(cl)
                    if size > lim:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": (
                                    f"Payload too large ({size} bytes). "
                                    f"Max para este endpoint: {lim} bytes."
                                )
                            },
                        )
                except (ValueError, TypeError):
                    pass
        return await call_next(request)
