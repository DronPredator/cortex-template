"""Fixtures compartidas para todos los tests.

Usa un directorio temporal para `users.json` y demás archivos de runtime, así
los tests no contaminan los datos de producción.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Asegurar que el proyecto root está en el sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Env vars de test (override .env vía 12-factor) ──────────────────
os.environ["JWT_SECRET"] = "test_jwt_secret_for_pytest_only_32chars+"
os.environ["CHAT_USER"] = "testuser"
os.environ["CHAT_PASSWORD"] = "testpass"
os.environ["ADMIN_USER"] = "testadmin"
os.environ["ADMIN_PASSWORD"] = "testadminpass"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # desactivar slowapi en tests

# ── Aislar archivos de runtime ──────────────────────────────────────
# Importamos config antes de que se importe el resto del app, y
# redirigimos las rutas a un tmpdir.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="cortex_test_"))

from app import config as _config  # noqa: E402

_config.USERS_PATH = _TMP_DIR / "users.json"
_config.MEMORY_PATH = _TMP_DIR / "memory.json"
_config.CONVERSATIONS_LOG_PATH = _TMP_DIR / "conversations_log.jsonl"
_config.RUNTIME_CONFIG_PATH = _TMP_DIR / "runtime_config.json"
_config.SYSTEM_PROMPT_CUSTOM_PATH = _TMP_DIR / "system_prompt_custom.txt"
_config.AGENTS_PATH = _TMP_DIR / "agents.json"
_config.AUDIT_LOG_PATH = _TMP_DIR / "audit_log.jsonl"

# Propagar los overrides también a los módulos que ya hayan hecho `from
# app.config import ...` (binding por valor).
import app.storage.users as _users_mod  # noqa: E402

_users_mod.USERS_PATH = _config.USERS_PATH

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    """TestClient con la app montada. Lifespan se ejecuta automáticamente."""
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_token(client):
    """Token JWT válido de admin para pruebas."""
    r = client.post(
        "/api/admin/login",
        json={
            "username": os.environ["ADMIN_USER"],
            "password": os.environ["ADMIN_PASSWORD"],
        },
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture
def user_token(client):
    """Token JWT válido de usuario regular para pruebas."""
    r = client.post(
        "/api/login",
        json={
            "username": os.environ["CHAT_USER"],
            "password": os.environ["CHAT_PASSWORD"],
        },
    )
    assert r.status_code == 200, f"user login failed: {r.status_code} {r.text}"
    return r.json()["token"]
