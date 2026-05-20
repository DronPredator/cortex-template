"""Endpoint para que el admin lea el historial de conversaciones."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import verify_admin_token_dep
from app.storage.conversations import read_conversations


router = APIRouter(tags=["admin-conversations"])


@router.get("/api/admin/conversations")
def get_conversations(
    user: str | None = None,
    limit: int = 50,
    _token: str = Depends(verify_admin_token_dep),
):
    entries = read_conversations(user=user, limit=limit)
    return {"conversations": entries, "count": len(entries)}
