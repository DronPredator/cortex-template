"""Middleware que agrega headers HTTP de seguridad a todas las respuestas.

Estos headers son de bajo costo y mitigan ataques comunes:
- `X-Content-Type-Options: nosniff` → el browser no adivina el MIME type
  (mitiga ataques de MIME confusion)
- `X-Frame-Options: DENY` → bloquea que la app sea embebida en <iframe>
  de otros sitios (mitiga clickjacking)
- `Referrer-Policy: strict-origin-when-cross-origin` → no leakea la URL
  completa a sitios externos en navegaciones
- `Permissions-Policy` → desactiva APIs sensibles del browser que no usamos
  (cámara, micrófono, geo) → si hay XSS, no pueden abusarse esas APIs
- `Cross-Origin-Opener-Policy: same-origin` → aisla el contexto del browser
  para mitigar ataques tipo Spectre

CSP no se agrega acá porque requiere testing detallado por componente y
puede romper el frontend (React via CDN + Babel standalone). Es Tier 3.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": (
        "camera=(), microphone=(self), geolocation=(), "
        "payment=(), usb=(), accelerometer=(), gyroscope=()"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inyecta headers de seguridad en cada response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for k, v in _HEADERS.items():
            # Solo agregar si la response no lo seteó ya (no pisar)
            if k not in response.headers:
                response.headers[k] = v
        return response
