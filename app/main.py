"""Entry point del FastAPI app.

Solo se encarga de: armar la app, registrar middlewares, montar routers
y servir el frontend estático. NO contiene lógica de negocio.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

# B4: defusa los parsers XML de la stdlib (xml.etree, xml.sax, xml.dom,
# minidom, pulldom, expat). Hardening defensivo contra entity expansion,
# external entity reference, decompression bomb. lxml 6.x ya tiene
# defaults seguros, pero esto cubre toda la stack incluyendo libs
# transitivas que puedan caer en stdlib XML.
# Tiene que estar ANTES de cualquier import que use parsers XML.
import defusedxml
defusedxml.defuse_stdlib()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.security.body_limit import BodySizeLimitMiddleware
from app.security.headers import SecurityHeadersMiddleware
from app.security.rate_limit import limiter

from app.config import DATASHEETS_DIR, DOCUMENTS_DIR, STATIC_DIR, settings
from app.errors import register_error_handlers
from app.version import __version__
from app.logging_config import setup_logging
from app.agents.registry import ensure_agents_file
from app.routes import (
    admin_agents,
    admin_chat,
    admin_conversations,
    admin_memory,
    admin_system,
    admin_users,
    agents,
    auth,
    catalog,
    chat,
    downloads,
    health,
    upload,
)
from app.storage.backups import backup_loop
from app.storage.memory import memory_refresh_loop
from app.storage.users import ensure_users_file


# Swagger UI y OpenAPI schema desactivados por default — exponen el mapa
# completo del API sin auth. Activar SOLO en dev/staging con DOCS_ENABLED=true.
_DOCS_ENABLED = os.environ.get("DOCS_ENABLED", "false").lower() == "true"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()

    # Warnings del provider activo
    for w in settings.validate_for_provider():
        logger.warning("config_warning | {}", w)

    ensure_users_file()
    ensure_agents_file()
    DATASHEETS_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    mem_task = asyncio.create_task(memory_refresh_loop())
    bk_task = asyncio.create_task(backup_loop())
    logger.info(
        "app_startup_complete | provider={} model={}",
        settings.llm_provider, settings.gemini_model,
    )
    yield
    mem_task.cancel()
    bk_task.cancel()
    logger.info("app_shutdown")


app = FastAPI(
    title="Cortex API",
    version=__version__,
    lifespan=lifespan,
    # Discovery surface mínima en producción. /docs y /openapi.json revelan
    # la lista completa de endpoints, body schemas y validation errors —
    # útil para devs, peligroso para atacantes. Se reactiva con DOCS_ENABLED=true.
    docs_url="/docs" if _DOCS_ENABLED else None,
    redoc_url="/redoc" if _DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _DOCS_ENABLED else None,
)

# Rate limiting (slowapi) — anti brute-force y anti abuse
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Headers HTTP de seguridad (mitigan clickjacking, MIME-sniff, leak de referer)
app.add_middleware(SecurityHeadersMiddleware)

# Límite de tamaño de body por endpoint (anti DoS de payload gigante)
app.add_middleware(BodySizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)

# Handlers globales de excepciones (logging estructurado + JSON responses)
register_error_handlers(app)

# Rutas
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(admin_chat.router)
app.include_router(admin_agents.router)
app.include_router(admin_users.router)
app.include_router(admin_system.router)
app.include_router(admin_memory.router)
app.include_router(admin_conversations.router)
app.include_router(upload.router)
app.include_router(catalog.router)
app.include_router(downloads.router)

# Frontend estático (debe ir al final — captura todo lo que no matcheó arriba)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
