"""Centralized app configuration.

Reads env vars from `.env` (or the real OS env) and validates them at
startup. If something critical is missing, the app fails fast with a clear
error instead of blowing up mid-request.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationError


# ── Absolute paths (relative to the project root, NOT the cwd) ──
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
STATIC_DIR = BASE_DIR / "static"
DATASHEETS_DIR = STATIC_DIR / "datasheets"
DOCUMENTS_DIR = STATIC_DIR / "documents"

# Runtime data files
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

# Daily automatic backups (rotated, keeping the last N days)
BACKUPS_DIR = BASE_DIR / "backups"
BACKUP_RETENTION_DAYS = 14

# Default agent — used when the client does not send agent_id (backward compat)
DEFAULT_AGENT_ID = "demo_assistant"


def _load_env() -> dict:
    """Merge .env (if present) with OS env vars. OS env wins (12-factor
    convention — .env acts as defaults)."""
    env_vars = dict(dotenv_values(ENV_PATH) or {})
    env_vars.update(os.environ)
    return env_vars


def _csv_list(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


class Settings(BaseModel):
    """All runtime configuration. Validated at startup."""

    # ── LLM provider ──────────────────────────────────────────────
    llm_provider: str = Field(default="gemini")
    google_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    tavily_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3.5-flash")
    gemini_enable_search: bool = Field(default=True)
    gemini_thinking: str = Field(default="auto")

    # ── Auth ──────────────────────────────────────────────────────
    chat_user: str = Field(default="user")
    chat_password: str = Field(default="")
    admin_user: str = Field(default="admin")
    admin_password: str = Field(default="")
    jwt_secret: str = Field(min_length=32, description="JWT signing secret (>=32 chars)")
    jwt_algorithm: str = Field(default="HS256")
    # JWT expires in 24h by default. 8h used to force re-login mid-workday
    # (>9h shifts). 24h covers any normal workday without sacrificing much
    # security — the LAN deployment is private and the audit log captures
    # intrusions. For longer-lived sessions, see POST /api/auth/refresh which
    # silently renews the token while the tab is open.
    jwt_expire_hours: int = Field(default=24, ge=1, le=168)

    # ── Operational ───────────────────────────────────────────────
    mock_mode: bool = Field(default=False)
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    # ── Agent behavior limits ─────────────────────────────────────
    max_agent_iterations: int = Field(default=12, ge=1, le=50)
    catalog_result_limit: int = Field(default=200, ge=10, le=1000)
    log_rotate_size: int = Field(default=5 * 1024 * 1024)  # 5 MB
    custom_prompt_max: int = Field(default=20_000)

    # Optional language directive prepended to the system prompt of every
    # agent. Useful when the deployment serves a non-English audience and
    # you want Gemini's thoughts (with `include_thoughts=True`) to come back
    # in the user's language instead of English. Empty by default — the
    # template does NOT force any language.
    # Example for a Spanish (Latin American) deployment:
    #   LANGUAGE_DIRECTIVE="## LANGUAGE\nAlways respond in Spanish
    #   (Latin American Spanish). Your internal thoughts must also be in
    #   Spanish, not English."
    language_directive: str = Field(default="")

    # ctx_max — cap on the chat `system_context` (includes text extracted
    # from uploaded files). Must be >= MAX_CHARS from document_extract
    # (60K) plus headroom for multiple files attached in the same turn.
    # Previously 30K caused Pydantic 422 errors when uploading large
    # Excel/PDF files (the extractor truncated at 60K, but the request
    # cap was half of that). Now 120K (~30K tokens — Gemini Flash has
    # 1M context, plenty of room).
    ctx_max: int = Field(default=120_000)
    max_upload_bytes: int = Field(default=25 * 1024 * 1024)  # 25 MB

    @classmethod
    def from_env(cls) -> "Settings":
        env = _load_env()

        def _get(key: str, default: str = "") -> str:
            return (env.get(key) or default).strip()

        try:
            return cls(
                llm_provider=_get("LLM_PROVIDER", "gemini").lower(),
                google_api_key=_get("GOOGLE_API_KEY"),
                anthropic_api_key=_get("ANTHROPIC_API_KEY"),
                tavily_api_key=_get("TAVILY_API_KEY"),
                gemini_model=_get("GEMINI_MODEL", "gemini-3.5-flash"),
                gemini_enable_search=_get("GEMINI_ENABLE_SEARCH", "true").lower() == "true",
                gemini_thinking=_get("GEMINI_THINKING", "auto"),
                chat_user=_get("CHAT_USER", "user"),
                chat_password=_get("CHAT_PASSWORD"),
                admin_user=_get("ADMIN_USER", "admin"),
                admin_password=_get("ADMIN_PASSWORD"),
                jwt_secret=_get("JWT_SECRET"),
                jwt_algorithm=_get("JWT_ALGORITHM", "HS256"),
                jwt_expire_hours=int(_get("JWT_EXPIRE_HOURS", "24") or 24),
                mock_mode=_get("MOCK_MODE", "false").lower() == "true",
                cors_origins=_csv_list(
                    _get("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
                ),
                language_directive=_get("LANGUAGE_DIRECTIVE", ""),
            )
        except ValidationError as e:
            # Reformat the error so it's clear which key is missing
            issues = []
            for err in e.errors():
                loc = ".".join(str(p) for p in err["loc"])
                issues.append(f"  - {loc}: {err['msg']}")
            raise RuntimeError(
                "Invalid configuration in .env:\n"
                + "\n".join(issues)
                + "\n\nReview your .env and try again."
            ) from e

    # Derived helpers
    @property
    def llm_uses_gemini(self) -> bool:
        return self.llm_provider == "gemini"

    def validate_for_provider(self) -> List[str]:
        """Returns a list of warnings (not fatal) if the active provider
        is missing keys."""
        warnings = []
        if self.llm_uses_gemini and not self.google_api_key:
            warnings.append("LLM_PROVIDER=gemini but GOOGLE_API_KEY is empty")
        if not self.llm_uses_gemini and not self.anthropic_api_key:
            warnings.append("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty")
        if not self.tavily_api_key:
            warnings.append("TAVILY_API_KEY is empty — Tavily web search disabled")
        return warnings


# Singleton — loaded ONCE when this module is imported
settings = Settings.from_env()


# Catalog of available Gemini models (used by the admin panel selector).
# Order: newest first. The first entry per tier is the default.
AVAILABLE_GEMINI_MODELS = [
    {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro", "desc": "Top quality. For complex analysis and technical queries.", "tier": "pro"},
    {"id": "gemini-3.5-flash", "name": "Gemini 3.5 Flash", "desc": "Recommended balance. Stable, no 'preview' tag. 1M token context.", "tier": "balanced"},
    {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash-Lite", "desc": "Economical. Fast for simple queries and internal tasks.", "tier": "lite"},
    # ── Stable fallbacks (previous generations) — available from admin ──
    {"id": "gemini-3-flash-preview", "name": "Gemini 3 Flash (preview)", "desc": "Previous Flash version. Keep as rollback if 3.5 misbehaves.", "tier": "balanced"},
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "desc": "Previous stable gen (June 2025). Reliable fallback.", "tier": "balanced"},
    {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash-Lite", "desc": "Previous stable Lite. Cheaper fallback.", "tier": "lite"},
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "desc": "Stable, gen 2.0. Last fallback option.", "tier": "lite"},
]

# Models per tier for the auto-router. If Google breaks any preview, you
# can switch these defaults to one of the stable versions in the catalog above.
MODEL_TIER_PRO = "gemini-3.1-pro-preview"
MODEL_TIER_FLASH = "gemini-3.5-flash"
MODEL_TIER_LITE = "gemini-3.1-flash-lite"
