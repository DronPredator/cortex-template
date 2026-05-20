"""Memoria del agente — leer + regenerar."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from app.auth import verify_admin_token_dep
from app.storage.memory import generate_memory, load_memory


router = APIRouter(tags=["admin-memory"])


@router.get("/api/admin/memory")
def get_memory(_token: str = Depends(verify_admin_token_dep)):
    data = load_memory()
    if not data:
        return {"content": None, "generated_at": None, "conversations_analyzed": 0}
    return data


@router.post("/api/admin/memory/refresh")
async def refresh_memory(_token: str = Depends(verify_admin_token_dep)):
    return await asyncio.to_thread(generate_memory)
