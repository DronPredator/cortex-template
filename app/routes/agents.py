"""Endpoint público (auth required) para listar agentes visibles al usuario.

Endpoints admin-only para CRUD viven en `app/routes/admin_agents.py` (fase B.4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fastapi import HTTPException

from app.agents.permissions import can_user_access, filter_visible_agents
from app.agents.registry import get_agent, list_agents
from app.auth import verify_token_with_role_dep
from app.storage.examples import get_examples_for_today


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
                "icon_url": a.icon_url,
                "default_tier": a.default_tier,
                "is_default": a.is_default,
            }
            for a in visible
        ],
        "default_agent_id": next((a.id for a in visible if a.is_default), None),
    }


@router.get("/api/agents/{agent_id}/examples")
def get_agent_examples(
    agent_id: str,
    auth: dict = Depends(verify_token_with_role_dep),
    count: int = 3,
):
    """Devuelve hasta `count` ejemplos de consultas para mostrar en el welcome
    screen del agente. Rotación diaria determinística por fecha UTC."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    if not can_user_access(auth["user"], auth["is_admin"], agent):
        raise HTTPException(status_code=403, detail="Sin acceso al agente")

    # Cap defensivo de count
    count = max(1, min(int(count), 6))
    examples = get_examples_for_today(agent_id, count=count)
    return {"agent_id": agent_id, "examples": examples}
