"""Health check endpoints.

Estrategia de exposición:
- `/api/health` — PÚBLICO. Mínimo: status + version + timestamp. Lo justo
  para que un load balancer, uptime check o el script de instalación
  confirme que el server está vivo. NO revela métricas internas.
- `/api/admin/health` — REQUIERE AUTH ADMIN. Detalle profundo: catálogo,
  LLM reachability, disk free, providers configurados. Reservado al panel
  admin para diagnóstico.
- `/api/version` — PÚBLICO. Sólo la versión.

Razón del split (post v1.1.0): el endpoint detallado público revelaba
catalog_size, disk_free_mb y qué LLM provider está activo. Para una app
interna en LAN privada es discovery info útil para un atacante.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from loguru import logger

from app.auth import verify_admin_token_dep
from app.config import (
    BASE_DIR,
    CONVERSATIONS_LOG_PATH,
    DATASHEETS_DIR,
    DOCUMENTS_DIR,
    USERS_PATH,
    settings,
)
from app.llm.providers import anthropic_health_check, gemini_health_check
from app.version import __version__

router = APIRouter(tags=["health"])


def _compute_health_detail() -> dict:
    """Calcula los checks profundos. Llamado desde el endpoint admin."""
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
    return {"checks": checks, "all_critical_ok": all_critical_ok}


@router.get("/api/health")
def health():
    """Endpoint público de liveness. Devuelve sólo status + version + timestamp.

    Diseñado para load balancers, uptime monitoring externos y el script
    de instalación. NO revela métricas internas — para eso está
    `/api/admin/health` (requiere auth admin).
    """
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/admin/health")
def admin_health(_token: str = Depends(verify_admin_token_dep)):
    """Health check profundo — requiere auth admin.

    Devuelve el detalle de TODOS los componentes críticos: catálogo,
    LLM, disk, providers. Es el endpoint que usa el panel admin para
    el diagnóstico del sistema.
    """
    detail = _compute_health_detail()
    return {
        "status": "ok" if detail["all_critical_ok"] else "degraded",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": detail["checks"],
    }


@router.get("/api/version")
def version():
    """Endpoint público mínimo — útil para load balancers."""
    return {"version": __version__, "status": "ok"}
