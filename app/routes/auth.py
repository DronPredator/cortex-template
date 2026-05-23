"""User & admin login + JWT token refresh."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from loguru import logger

from app.auth import create_token, safe_eq
from app.config import settings
from app.models import LoginRequest
from app.security.rate_limit import LOGIN_LIMIT, limiter
from app.storage.audit import audit_event
from app.storage.users import authenticate, ensure_users_file, touch_last_active


router = APIRouter(tags=["auth"])
_bearer = HTTPBearer()


@router.post("/api/login")
@limiter.limit(LOGIN_LIMIT)
def login(req: LoginRequest, request: Request):
    ensure_users_file()
    if not authenticate(req.username, req.password):
        logger.warning("login_failed | username={}", req.username)
        # Forensic trail. The audit log is the source of truth for detecting
        # brute-force attempts that sneak under the rate-limit (e.g. rotating IPs).
        audit_event(
            actor=req.username[:32],
            action="user_login_failed",
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    touch_last_active(req.username)
    logger.info("login_success | username={}", req.username)
    return {"token": create_token(req.username), "username": req.username}


@router.post("/api/admin/login")
@limiter.limit(LOGIN_LIMIT)
def admin_login(req: LoginRequest, request: Request):
    if not settings.admin_password:
        raise HTTPException(
            status_code=503,
            detail="Admin not configured. Set ADMIN_USER and ADMIN_PASSWORD in .env",
        )
    if not (
        safe_eq(req.username, settings.admin_user)
        and safe_eq(req.password, settings.admin_password)
    ):
        logger.warning("admin_login_failed | attempted={}", req.username)
        audit_event(
            actor=req.username[:32],
            action="admin_login_failed",
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )
    logger.info("admin_login_success | username={}", req.username)
    audit_event(
        actor=req.username,
        action="admin_login_success",
        request=request,
    )
    return {"token": create_token(req.username, {"role": "admin"})}


@router.post("/api/auth/refresh")
def refresh_token(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Renew the current user's JWT token.

    Accepts any valid JWT and returns a new one with a fresh expiration.
    The frontend invokes this silently every ~6h so the user never has
    to re-login while the app is actively used (Gmail-style).

    If the token has already expired (jose.JWTError "Signature has expired"),
    returns 401 — the frontend then redirects to the login screen.

    Preserves the original JWT's `role` claim (admin → admin) so privileges
    don't get lost on refresh.
    """
    try:
        payload = jwt.decode(
            creds.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as e:
        # Token expired or invalid → can't refresh. The frontend detects
        # the 401 and forces a re-login.
        logger.info("token_refresh_rejected | err={}", str(e)[:80])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token — please log in again",
        )

    user = payload.get("user", "")
    if not user:
        raise HTTPException(status_code=400, detail="Token missing user claim")

    # Preserve the role if present (admin / regular)
    extra = {}
    role = payload.get("role")
    if role:
        extra["role"] = role

    new_token = create_token(user, extra=extra or None)
    return {"token": new_token, "username": user, "role": role}
