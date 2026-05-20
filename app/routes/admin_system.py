"""Configuración del agente desde el panel admin — system prompt, modelo, auto-route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from app.auth import verify_admin_token_dep
from app.storage.audit import audit_event
from app.config import (
    AVAILABLE_GEMINI_MODELS,
    MODEL_TIER_FLASH,
    MODEL_TIER_LITE,
    MODEL_TIER_PRO,
    SYSTEM_PROMPT_CUSTOM_PATH,
    settings,
)
from app.models import AutoRouteRequest, ModelRequest, SystemPromptRequest
from app.prompts.loader import _load as load_prompt_file
from app.storage.atomic import atomic_write
from app.storage.memory import load_custom_prompt
from app.storage.runtime_config import (
    get_current_model,
    load_runtime_config,
    save_runtime_config,
)
from search import catalog_size


router = APIRouter(tags=["admin-system"])


@router.get("/api/admin/system-prompt")
def get_system_prompt(_token: str = Depends(verify_admin_token_dep)):
    base = load_prompt_file("system").format(n_items=catalog_size())
    return {
        "base_prompt": base,
        "custom_prompt": load_custom_prompt(),
    }


@router.post("/api/admin/system-prompt")
def update_system_prompt(
    req: SystemPromptRequest,
    request: Request,
    _token: str = Depends(verify_admin_token_dep),
):
    atomic_write(SYSTEM_PROMPT_CUSTOM_PATH, req.custom_prompt)
    logger.info("system_prompt_updated | chars={}", len(req.custom_prompt))
    audit_event(
        actor=settings.admin_user,
        action="system_prompt_updated",
        target="prompt:custom_global",
        request=request,
        meta={"chars": len(req.custom_prompt)},
    )
    return {"message": "Comportamiento del agente actualizado correctamente"}


@router.get("/api/admin/model")
def get_model_endpoint(_token: str = Depends(verify_admin_token_dep)):
    cfg = load_runtime_config()
    return {
        "provider": settings.llm_provider,
        "current": get_current_model(),
        "default_from_env": settings.gemini_model,
        "available": AVAILABLE_GEMINI_MODELS,
        "auto_route": cfg.get("auto_route", True),
        "tier_models": {
            "pro": MODEL_TIER_PRO,
            "flash": MODEL_TIER_FLASH,
            "lite": MODEL_TIER_LITE,
        },
    }


@router.post("/api/admin/model")
def set_model_endpoint(
    req: ModelRequest,
    request: Request,
    _token: str = Depends(verify_admin_token_dep),
):
    valid_ids = {m["id"] for m in AVAILABLE_GEMINI_MODELS}
    if req.model not in valid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Modelo '{req.model}' no está en la lista permitida",
        )
    cfg = load_runtime_config()
    prev = cfg.get("gemini_model")
    cfg["gemini_model"] = req.model
    save_runtime_config(cfg)
    logger.info("model_updated | model={}", req.model)
    audit_event(
        actor=settings.admin_user,
        action="model_changed",
        target=f"model:{req.model}",
        request=request,
        meta={"previous": prev},
    )
    return {"message": "Modelo actualizado", "current": req.model}


@router.post("/api/admin/auto-route")
def set_auto_route(
    req: AutoRouteRequest,
    request: Request,
    _token: str = Depends(verify_admin_token_dep),
):
    cfg = load_runtime_config()
    cfg["auto_route"] = bool(req.enabled)
    save_runtime_config(cfg)
    logger.info("auto_route_updated | enabled={}", req.enabled)
    audit_event(
        actor=settings.admin_user,
        action="auto_route_toggled",
        target="config:auto_route",
        request=request,
        meta={"enabled": bool(req.enabled)},
    )
    return {"message": "Router automático actualizado", "auto_route": cfg["auto_route"]}
