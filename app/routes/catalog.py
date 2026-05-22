"""Endpoint para recargar el catálogo en memoria."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from app.auth import verify_admin_token_dep
from search import reload_stock


router = APIRouter(tags=["catalog"])


@router.post("/api/reload-stock")
def reload_stock_endpoint(_token: str = Depends(verify_admin_token_dep)):
    try:
        reload_stock()
        logger.info("catalog_reloaded")
        return {"message": "Catálogo recargado correctamente"}
    except Exception as e:
        logger.exception("catalog_reload_failed")
        raise HTTPException(status_code=500, detail=f"Error al recargar el catálogo: {e}")
