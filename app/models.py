"""Modelos Pydantic para request bodies de los endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.config import settings


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]]
    system_context: str = Field(default="", max_length=settings.ctx_max)
    # `agent_id` opcional → si no se manda, el server usa DEFAULT_AGENT_ID
    # (backward compat con frontend viejo que no conoce agentes)
    agent_id: str | None = Field(default=None, max_length=64)


class AgentUpsertRequest(BaseModel):
    id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    icon: str = Field(default="🤖", max_length=8)
    allowed_tools: list[str] = Field(default_factory=list, max_length=20)
    default_tier: str = Field(default="auto", pattern=r"^(auto|pro|flash|lite)$")
    visibility: str = Field(default="public", pattern=r"^(public|private|users)$")
    allowed_users: list[str] = Field(default_factory=list, max_length=100)
    is_default: bool = False


class AdminChatRequest(BaseModel):
    messages: list[dict[str, Any]]


class SystemPromptRequest(BaseModel):
    custom_prompt: str = Field(default="", max_length=settings.custom_prompt_max)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    # Política de password: mínimo 8 caracteres (anti brute-force práctico).
    # Solo aplica a usuarios NUEVOS. Los existentes mantienen su password actual.
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Mínimo 8 caracteres",
    )


class ModelRequest(BaseModel):
    model: str = Field(min_length=3, max_length=100)


class AutoRouteRequest(BaseModel):
    enabled: bool
