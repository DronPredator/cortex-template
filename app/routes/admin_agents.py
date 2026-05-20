"""Endpoints admin-only para gestión de agentes (CRUD + edición de prompts)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from app.agents.base import AgentDefinition
from app.agents.registry import (
    delete_agent,
    get_agent,
    list_agents,
    load_agent_prompt,
    save_agent_prompt,
    upsert_agent,
)
from app.auth import verify_admin_token_dep
from app.config import settings
from app.models import AgentUpsertRequest
from app.storage.audit import audit_event


router = APIRouter(tags=["admin-agents"])


class AgentPromptRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)


# ── Lista completa (incluye privados, con detalle) ────────────────────


@router.get("/api/admin/agents")
def admin_list_agents(_admin: str = Depends(verify_admin_token_dep)):
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "icon": a.icon,
                "allowed_tools": a.allowed_tools,
                "default_tier": a.default_tier,
                "visibility": a.visibility,
                "allowed_users": a.allowed_users,
                "is_default": a.is_default,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            }
            for a in list_agents()
        ]
    }


# ── CRUD ──────────────────────────────────────────────────────────────


@router.post("/api/admin/agents")
def admin_upsert_agent(
    req: AgentUpsertRequest,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    """Crea o actualiza un agente. Si `is_default=True`, des-marca el actual default."""
    pre_existing = get_agent(req.id) is not None

    # Resetear is_default en los demás si este es default
    if req.is_default:
        for a in list_agents():
            if a.id != req.id and a.is_default:
                a.is_default = False
                upsert_agent(a)

    agent = AgentDefinition(
        id=req.id,
        name=req.name,
        description=req.description,
        icon=req.icon,
        allowed_tools=list(req.allowed_tools),
        default_tier=req.default_tier,
        visibility=req.visibility,
        allowed_users=list(req.allowed_users),
        is_default=req.is_default,
    )
    saved = upsert_agent(agent)

    # Si no existe el prompt en disco aún, crear uno mínimo placeholder
    try:
        load_agent_prompt(saved)
    except Exception:
        pass

    audit_event(
        actor=settings.admin_user,
        action="agent_updated" if pre_existing else "agent_created",
        target=f"agent:{req.id}",
        request=request,
        meta={"visibility": req.visibility, "default_tier": req.default_tier},
    )
    return {"agent": saved.to_dict(), "ok": True}


@router.delete("/api/admin/agents/{agent_id}")
def admin_delete_agent(
    agent_id: str,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    try:
        deleted = delete_agent(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    audit_event(
        actor=settings.admin_user,
        action="agent_deleted",
        target=f"agent:{agent_id}",
        request=request,
    )
    return {"ok": True}


# ── Edición de prompts (.md) ──────────────────────────────────────────


@router.get("/api/admin/agents/{agent_id}/prompt")
def admin_get_agent_prompt(
    agent_id: str, _admin: str = Depends(verify_admin_token_dep)
):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    content = load_agent_prompt(agent)
    return {"agent_id": agent_id, "content": content}


@router.put("/api/admin/agents/{agent_id}/prompt")
def admin_save_agent_prompt(
    agent_id: str,
    req: AgentPromptRequest,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    save_agent_prompt(agent, req.content)
    logger.info("admin_saved_agent_prompt | id={} bytes={}", agent_id, len(req.content))
    audit_event(
        actor=settings.admin_user,
        action="agent_prompt_saved",
        target=f"agent:{agent_id}",
        request=request,
        meta={"bytes": len(req.content)},
    )
    return {"ok": True, "bytes": len(req.content)}
