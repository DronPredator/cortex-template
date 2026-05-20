"""Sanitización de datos sensibles antes de loguear o devolver al cliente.

Evita que tokens, passwords, secrets, api keys, JWTs filtren al log o al
response body de un error de validación.
"""

from __future__ import annotations

import re
from typing import Any


# Campos cuyos valores se redactan completamente
SENSITIVE_KEYS = {
    "password", "passwd", "pwd",
    "secret", "client_secret", "secret_key",
    "token", "access_token", "refresh_token", "id_token", "jwt",
    "authorization", "auth",
    "api_key", "apikey", "x-api-key",
    "credential", "credentials",
    "private_key", "session", "cookie",
}

# Patrón para detectar JWTs en strings sueltos (3 segmentos base64 separados por puntos)
_JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")

# Patrón para detectar headers Bearer
_BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}", re.IGNORECASE)


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    k = key.lower().strip()
    return any(s in k for s in SENSITIVE_KEYS)


def redact_value(value: Any) -> Any:
    """Redacta strings que contengan JWT o Bearer tokens."""
    if isinstance(value, str):
        out = _JWT_PATTERN.sub("***JWT_REDACTED***", value)
        out = _BEARER_PATTERN.sub("Bearer ***REDACTED***", out)
        return out
    return value


def sanitize_dict(d: Any) -> Any:
    """Recorre recursivamente un dict/list y redacta valores sensibles."""
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            if _is_sensitive_key(k):
                out[k] = "***REDACTED***"
            else:
                out[k] = sanitize_dict(v)
        return out
    if isinstance(d, list):
        return [sanitize_dict(x) for x in d]
    return redact_value(d)


def sanitize_pydantic_errors(errors: list[dict]) -> list[dict]:
    """Limpia los `input` de validation errors si el campo es sensible.

    Pydantic devuelve `errors()` con una key `input` que contiene el valor
    que falló validación. Si el campo es `password`, eso es una leak directa.
    """
    out = []
    for err in errors or []:
        e = dict(err)
        loc = e.get("loc", ())
        if any(_is_sensitive_key(p) for p in loc):
            if "input" in e:
                e["input"] = "***REDACTED***"
        # También redactar JWTs si aparecen en `input` o `msg`
        if "input" in e:
            e["input"] = redact_value(e["input"])
        if "msg" in e:
            e["msg"] = redact_value(e["msg"])
        out.append(e)
    return out
