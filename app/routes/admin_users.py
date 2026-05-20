"""CRUD de usuarios desde el panel admin."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from app.auth import verify_admin_token_dep
from app.config import settings
from app.models import CreateUserRequest
from app.storage.audit import audit_event
from app.storage.users import (
    count_conversations_by_user,
    ensure_users_file,
    hash_password,
    load_users,
    save_users,
)


router = APIRouter(tags=["admin-users"])


@router.get("/api/admin/users")
def list_users(_token: str = Depends(verify_admin_token_dep)):
    ensure_users_file()
    users = load_users()
    counts = count_conversations_by_user()
    return {
        "users": sorted(
            [
                {
                    "username": name,
                    "created_at": data.get("created_at"),
                    "last_active": data.get("last_active"),
                    "conversation_count": counts.get(name, 0),
                }
                for name, data in users.items()
            ],
            key=lambda u: u["username"].lower(),
        )
    }


@router.post("/api/admin/users")
def create_user(
    req: CreateUserRequest,
    request: Request,
    _token: str = Depends(verify_admin_token_dep),
):
    ensure_users_file()
    users = load_users()
    if req.username in users:
        raise HTTPException(status_code=409, detail="El usuario ya existe")
    if req.username == settings.admin_user:
        raise HTTPException(
            status_code=400,
            detail="No podés usar el mismo nombre que el administrador",
        )
    users[req.username] = {
        "password_hash": hash_password(req.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_active": None,
    }
    save_users(users)
    logger.info("user_created | username={}", req.username)
    audit_event(
        actor=settings.admin_user,
        action="user_created",
        target=f"user:{req.username}",
        request=request,
    )
    return {"message": "Usuario creado", "username": req.username}


@router.delete("/api/admin/users/{username}")
def delete_user(
    username: str,
    request: Request,
    _token: str = Depends(verify_admin_token_dep),
):
    ensure_users_file()
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if len(users) <= 1:
        raise HTTPException(
            status_code=400,
            detail="No podés borrar el último usuario del sistema",
        )
    del users[username]
    save_users(users)
    logger.info("user_deleted | username={}", username)
    audit_event(
        actor=settings.admin_user,
        action="user_deleted",
        target=f"user:{username}",
        request=request,
    )
    return {"message": "Usuario eliminado", "username": username}
