"""Configuración centralizada del app.

Lee variables de entorno desde `.env` (o env reales del sistema) y las valida
en startup. Si algo crítico falta, la app falla rápido con un error claro
en lugar de explotar a mitad de un request.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationError


# ── Paths absolutos (relativos a la carpeta del proyecto, NO al cwd) ──
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
STATIC_DIR = BASE_DIR / "static"
DATASHEETS_DIR = STATIC_DIR / "datasheets"
DOCUMENTS_DIR = STATIC_DIR / "documents"

# Archivos de datos
USERS_PATH = BASE_DIR / "users.json"
MEMORY_PATH = BASE_DIR / "memory.json"
CONVERSATIONS_LOG_PATH = BASE_DIR / "conversations_log.jsonl"
AUDIT_LOG_PATH = BASE_DIR / "audit_log.jsonl"
RUNTIME_CONFIG_PATH = BASE_DIR / "runtime_config.json"
SYSTEM_PROMPT_CUSTOM_PATH = BASE_DIR / "system_prompt_custom.txt"
AGENTS_PATH = BASE_DIR / "agents.json"

# Prompts
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
AGENT_DEFINITIONS_DIR = Path(__file__).resolve().parent / "agents" / "definitions"
AGENT_KNOWLEDGE_DIR = Path(__file__).resolve().parent / "agents" / "knowledge"

# Backups automáticos diarios (se rotan, manteniendo los últimos N días)
BACKUPS_DIR = BASE_DIR / "backups"
BACKUP_RETENTION_DAYS = 14

# Agente default — se usa si el cliente no manda agent_id (backward compat).
# Personalizar al nombre del agente flagship de la instancia.
DEFAULT_AGENT_ID = "demo_assistant"


def _load_env() -> dict:
    """Combina .env (si existe) con variables del SO. Las del SO tienen
    prioridad (12-factor app standard — el .env actúa como defaults)."""
    env_vars = dict(dotenv_values(ENV_PATH) or {})
    env_vars.update(os.environ)
    return env_vars


def _csv_list(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


class Settings(BaseModel):
    """Toda la configuración del runtime. Validada al startup."""

    # ── Identidad del cliente (rebrandable por instancia) ─────────
    company_name: str = Field(default="Demo Company")  # nombre corto, ej: "Acme"
    company_full_name: str = Field(default="Demo Company S.A.")  # razón social
    company_industry: str = Field(default="generic")  # libre, para clasificación
    cortex_instance_id: str = Field(default="demo_cortex")  # id único de instancia

    # ── LLM provider ──────────────────────────────────────────────
    llm_provider: str = Field(default="gemini")
    google_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    tavily_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3-flash-preview")
    gemini_enable_search: bool = Field(default=True)
    gemini_thinking: str = Field(default="auto")

    # ── Auth ──────────────────────────────────────────────────────
    chat_user: str = Field(default="demo")
    chat_password: str = Field(default="")
    admin_user: str = Field(default="admin")
    admin_password: str = Field(default="")
    jwt_secret: str = Field(min_length=16, description="JWT signing secret (>=16 chars)")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_hours: int = Field(default=8, ge=1, le=168)

    # ── Operacional ───────────────────────────────────────────────
    mock_mode: bool = Field(default=False)
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    # ── Límites de comportamiento del agente ──────────────────────
    max_agent_iterations: int = Field(default=12, ge=1, le=50)
    catalog_result_limit: int = Field(default=200, ge=10, le=1000)
    log_rotate_size: int = Field(default=5 * 1024 * 1024)  # 5 MB
    custom_prompt_max: int = Field(default=20_000)
    ctx_max: int = Field(default=30_000)
    max_upload_bytes: int = Field(default=25 * 1024 * 1024)  # 25 MB

    @classmethod
    def from_env(cls) -> "Settings":
        env = _load_env()

        def _get(key: str, default: str = "") -> str:
            return (env.get(key) or default).strip()

        try:
            return cls(
                company_name=_get("COMPANY_NAME", "Demo Company"),
                company_full_name=_get("COMPANY_FULL_NAME", "Demo Company S.A."),
                company_industry=_get("COMPANY_INDUSTRY", "generic"),
                cortex_instance_id=_get("CORTEX_INSTANCE_ID", "demo_cortex"),
                llm_provider=_get("LLM_PROVIDER", "gemini").lower(),
                google_api_key=_get("GOOGLE_API_KEY"),
                anthropic_api_key=_get("ANTHROPIC_API_KEY"),
                tavily_api_key=_get("TAVILY_API_KEY"),
                gemini_model=_get("GEMINI_MODEL", "gemini-3-flash-preview"),
                gemini_enable_search=_get("GEMINI_ENABLE_SEARCH", "true").lower() == "true",
                gemini_thinking=_get("GEMINI_THINKING", "auto"),
                chat_user=_get("CHAT_USER", "demo"),
                chat_password=_get("CHAT_PASSWORD"),
                admin_user=_get("ADMIN_USER", "admin"),
                admin_password=_get("ADMIN_PASSWORD"),
                jwt_secret=_get("JWT_SECRET"),
                jwt_algorithm=_get("JWT_ALGORITHM", "HS256"),
                jwt_expire_hours=int(_get("JWT_EXPIRE_HOURS", "8") or 8),
                mock_mode=_get("MOCK_MODE", "false").lower() == "true",
                cors_origins=_csv_list(
                    _get("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
                ),
            )
        except ValidationError as e:
            # Reformatear el error para que sea claro qué falta
            issues = []
            for err in e.errors():
                loc = ".".join(str(p) for p in err["loc"])
                issues.append(f"  - {loc}: {err['msg']}")
            raise RuntimeError(
                "Configuración inválida en .env:\n"
                + "\n".join(issues)
                + "\n\nRevisá tu .env y volvé a arrancar."
            ) from e

    # Helpers derivados
    @property
    def llm_uses_gemini(self) -> bool:
        return self.llm_provider == "gemini"

    def validate_for_provider(self) -> List[str]:
        """Devuelve lista de warnings (no fail) si faltan keys del provider activo."""
        warnings = []
        if self.llm_uses_gemini and not self.google_api_key:
            warnings.append("LLM_PROVIDER=gemini pero GOOGLE_API_KEY está vacío")
        if not self.llm_uses_gemini and not self.anthropic_api_key:
            warnings.append("LLM_PROVIDER=anthropic pero ANTHROPIC_API_KEY está vacío")
        if not self.tavily_api_key:
            warnings.append("TAVILY_API_KEY vacío — búsqueda web Tavily desactivada")
        return warnings


# Singleton — se carga UNA VEZ al importar este módulo
settings = Settings.from_env()


# Catálogo de modelos Gemini disponibles (para el selector del admin panel)
AVAILABLE_GEMINI_MODELS = [
    {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro", "desc": "Máxima calidad. $2/$12 por M tokens. Para consultas complejas.", "tier": "pro"},
    {"id": "gemini-3-flash-preview", "name": "Gemini 3 Flash", "desc": "Balance recomendado. $0.50/$3 por M tokens. Contexto de 2M tokens.", "tier": "balanced"},
    {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash-Lite", "desc": "Económico. $0.25/$1.50 por M tokens. Rápido para consultas simples.", "tier": "lite"},
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "desc": "Estable, generación anterior. $0.30/$2.50 por M tokens.", "tier": "balanced"},
    {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash-Lite", "desc": "Estable. $0.10/$0.40 por M tokens.", "tier": "lite"},
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "desc": "Más estable, generación previa. $0.10/$0.40 por M tokens.", "tier": "lite"},
]

# Modelos por tier para el auto-router
MODEL_TIER_PRO = "gemini-3.1-pro-preview"
MODEL_TIER_FLASH = "gemini-3-flash-preview"
MODEL_TIER_LITE = "gemini-3.1-flash-lite"
