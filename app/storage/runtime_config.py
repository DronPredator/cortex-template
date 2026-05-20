"""Configuración runtime overrideable desde el panel admin.

Persiste en `runtime_config.json` y tiene prioridad sobre los valores
del .env. Útil para cambiar el modelo Gemini sin reiniciar el server.
"""

from __future__ import annotations

import json

from loguru import logger

from app.config import RUNTIME_CONFIG_PATH, settings
from app.storage.atomic import atomic_write


def load_runtime_config() -> dict:
    if not RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("load_runtime_config_failed | {}", e)
        return {}


def save_runtime_config(cfg: dict) -> None:
    atomic_write(RUNTIME_CONFIG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2))


def get_current_model() -> str:
    """Modelo Gemini activo manual. Runtime config tiene prioridad sobre env."""
    cfg = load_runtime_config()
    return cfg.get("gemini_model") or settings.gemini_model
