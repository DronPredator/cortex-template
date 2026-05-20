"""Login de usuarios y de admin."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger

from app.auth import create_token, safe_eq
from app.config import settings
from app.models import LoginRequest
from app.security.rate_limit import LOGIN_LIMIT, limiter
from app.storage.audit import audit_event
from app.storage.users import authenticate, ensure_users_file, touch_last_active


router = APIRouter(tags=["auth"])


@router.post("/api/login")
@limiter.limit(LOGIN_LIMIT)
def login(req: LoginRequest, request: Request):
    ensure_users_file()
    if not authenticate(req.username, req.password):
        logger.warning("login_failed | username={}", req.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
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
            detail="Admin no configurado. Definí ADMIN_USER y ADMIN_PASSWORD en .env",
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
            detail="Credenciales de administrador incorrectas",
        )
    logger.info("admin_login_success | username={}", req.username)
    audit_event(
        actor=req.username,
        action="admin_login_success",
        request=request,
    )
    return {"token": create_token(req.username, {"role": "admin"})}
