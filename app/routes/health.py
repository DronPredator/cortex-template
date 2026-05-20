"""Health check endpoint con verificación profunda de dependencias."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone

from fastapi import APIRouter
from loguru import logger

from app.config import (
    BASE_DIR,
    CONVERSATIONS_LOG_PATH,
    DATASHEETS_DIR,
    DOCUMENTS_DIR,
    USERS_PATH,
    settings,
)
from app.llm.providers import anthropic_health_check, gemini_health_check


__version__ = "2.1.0"

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    """Devuelve el estado de cada componente crítico. Usado por monitoring."""
    try:
        from search import catalog_size

        cat_size = catalog_size()
    except Exception as e:
        logger.error("health_catalog_check_failed | {}", e)
        cat_size = -1

    try:
        disk = shutil.disk_usage(BASE_DIR)
        disk_free_mb = disk.free // (1024 * 1024)
    except Exception:
        disk_free_mb = -1

    checks = {
        "catalog_loaded": cat_size > 0,
        "catalog_size": cat_size,
        "users_db_readable": USERS_PATH.exists(),
        "conversations_log_writable": (
            CONVERSATIONS_LOG_PATH.exists() or CONVERSATIONS_LOG_PATH.parent.exists()
        ),
        "datasheets_dir": DATASHEETS_DIR.exists(),
        "documents_dir": DOCUMENTS_DIR.exists(),
        "disk_free_mb": disk_free_mb,
        "llm_provider": settings.llm_provider,
        "llm_reachable": (
            gemini_health_check()
            if settings.llm_uses_gemini
            else anthropic_health_check()
        ),
        "tavily_configured": bool(settings.tavily_api_key),
    }

    all_critical_ok = (
        checks["catalog_loaded"]
        and checks["users_db_readable"]
        and checks["llm_reachable"]
        and disk_free_mb > 100  # 100 MB mínimo
    )

    return {
        "status": "ok" if all_critical_ok else "degraded",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@router.get("/api/version")
def version():
    """Endpoint público mínimo — útil para load balancers."""
    return {"version": __version__, "status": "ok"}
