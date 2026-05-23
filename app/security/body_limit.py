"""Middleware that limits the request body size per endpoint.

Basic abuse defense: someone sending a 100 MB body to /api/login could
exhaust the server's memory. These limits cut those abuses before the
handler receives any data.

Policy:
- Login / auth endpoints: 4 KB (more than enough for username + password;
  catches obvious abuses).
- Chat endpoints: 5 MB (room for messages with `system_context` loaded
  from extracted documents).
- Admin endpoints: 200 KB (enough for long prompts).
- Upload endpoint: `settings.max_upload_bytes` handles the actual cap.
- Default: 1 MB.

If the body exceeds the limit, returns 413 Payload Too Large.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# (path_prefix, max_bytes) — order matters, first match wins.
# More specific rules (longer paths) FIRST.
_LIMITS: list[tuple[str, int]] = [
    ("/api/login", 4 * 1024),
    ("/api/admin/login", 4 * 1024),
    ("/api/auth/refresh", 1 * 1024),  # bearer header only, no body
    ("/api/chat/stream", 5 * 1024 * 1024),
    ("/api/admin/chat/stream", 5 * 1024 * 1024),
    ("/api/upload-document", 30 * 1024 * 1024),  # covers settings.max_upload_bytes
    # Knowledge files upload (multipart): up to 16 MB to cover large PDFs
    # with multipart-encoding overhead. The handler caps content at 15 MB.
    ("/api/admin/agents/", 16 * 1024 * 1024),
    ("/api/admin/agents", 200 * 1024),  # list / CRUD (small JSON)
    ("/api/admin/system-prompt", 200 * 1024),
    ("/api/admin/", 200 * 1024),
    ("/api/", 1 * 1024 * 1024),
]


def _limit_for(path: str) -> int | None:
    for prefix, lim in _LIMITS:
        if path.startswith(prefix):
            return lim
    return None  # no limit (static assets, /docs, etc.)


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
                                    f"Max for this endpoint: {lim} bytes."
                                )
                            },
                        )
                except (ValueError, TypeError):
                    pass
        return await call_next(request)
