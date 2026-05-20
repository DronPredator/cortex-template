"""Endpoint público (auth required) para listar agentes visibles al usuario.

Endpoints admin-only para CRUD viven en `app/routes/admin_agents.py` (fase B.4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.permissions import filter_visible_agents
from app.agents.registry import list_agents
from app.auth import verify_token_with_role_dep


router = APIRouter(tags=["agents"])


@router.get("/api/agents")
def get_agents(auth: dict = Depends(verify_token_with_role_dep)):
    """Lista agentes que el usuario actual puede ver/usar.

    Admin ve todos. Usuario regular ve solo los `public` + los `users` en cuya
    lista esté.
    """
    visible = filter_visible_agents(
        list_agents(),
        username=auth["user"],
        is_admin=auth["is_admin"],
    )
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "icon": a.icon,
                "default_tier": a.default_tier,
                "is_default": a.is_default,
            }
            for a in visible
        ],
        "default_agent_id": next((a.id for a in visible if a.is_default), None),
    }
