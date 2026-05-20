"""Autenticación JWT — creación y verificación de tokens, dependencies de FastAPI."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings


security = HTTPBearer()


def safe_eq(a: str, b: str) -> bool:
    """Comparación constant-time para evitar timing attacks."""
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def create_token(username: str | None = None, extra: dict | None = None) -> str:
    payload = {
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    }
    if username:
        payload["user"] = username
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token_dep(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """FastAPI dependency: devuelve el username del JWT o lanza 401."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("user", "")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )


def verify_token_with_role_dep(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """FastAPI dependency: devuelve {user, is_admin}. NO rechaza no-admins.

    Útil para endpoints que sirven a ambos roles con resultados filtrados
    (ej: /api/agents devuelve más agentes si sos admin).
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return {
            "user": payload.get("user", ""),
            "is_admin": payload.get("role") == "admin",
        }
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )


def verify_admin_token_dep(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """FastAPI dependency: valida que el JWT tenga role=admin."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requieren credenciales de administrador",
            )
        return credentials.credentials
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )
