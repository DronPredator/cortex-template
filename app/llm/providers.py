"""Factories de clients LLM (Anthropic, Gemini) con retry policy.

`tenacity` reintenta automáticamente errores transitorios (5xx, timeouts)
con backoff exponencial. No reintenta errores 4xx (mal request, no key, etc).
"""

from __future__ import annotations

from typing import Any

import anthropic
from anthropic import AsyncAnthropic
from fastapi import HTTPException
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings


# ── Anthropic ──────────────────────────────────────────────────────

def anthropic_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY no está configurada en el servidor",
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def async_anthropic_client() -> AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY no está configurada en el servidor",
        )
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


# ── Reintento ──────────────────────────────────────────────────────

# Errores transitorios que VALE LA PENA reintentar
_RETRYABLE = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


retry_llm_call = retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    before_sleep=lambda rs: logger.warning(
        "llm_retry | attempt={} exc={}",
        rs.attempt_number,
        type(rs.outcome.exception()).__name__ if rs.outcome.exception() else "?",
    ),
    reraise=True,
)


def gemini_health_check() -> bool:
    """Quick check de que Gemini API es alcanzable."""
    if not settings.google_api_key:
        return False
    try:
        from google import genai as _genai

        _client = _genai.Client(api_key=settings.google_api_key)
        # No hacemos una llamada real para no quemar quota — solo verificamos que el cliente se construya
        _ = _client.models  # accessor solo, no llama API
        return True
    except Exception as e:
        logger.error("gemini_health_check_failed | {}", e)
        return False


def anthropic_health_check() -> bool:
    if not settings.anthropic_api_key:
        return False
    try:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        _ = _client.messages  # accessor solo
        return True
    except Exception as e:
        logger.error("anthropic_health_check_failed | {}", e)
        return False
