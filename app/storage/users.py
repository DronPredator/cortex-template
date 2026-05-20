"""Gestión de usuarios — archivo `users.json` con hashes PBKDF2."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from loguru import logger

from app.config import USERS_PATH, settings
from app.storage.atomic import atomic_write


def hash_password(pw: str, salt: bytes | None = None) -> str:
    """PBKDF2-SHA256 con 100K iteraciones. Devuelve 'salt_hex:hash_hex'."""
    if salt is None:
        salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 100_000)
    return salt.hex() + ":" + h.hex()


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 100_000)
        return secrets.compare_digest(expected.hex(), h_hex)
    except Exception:
        return False


def load_users() -> dict:
    if not USERS_PATH.exists():
        return {}
    try:
        return json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("load_users_failed | {}", e)
        return {}


def save_users(users: dict) -> None:
    atomic_write(USERS_PATH, json.dumps(users, ensure_ascii=False, indent=2))


def ensure_users_file() -> None:
    """En el primer arranque, migra el usuario del .env al `users.json`."""
    if USERS_PATH.exists():
        return
    users: dict = {}
    if settings.chat_user and settings.chat_password:
        users[settings.chat_user] = {
            "password_hash": hash_password(settings.chat_password),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_active": None,
        }
        logger.info("users_file_migrated | initial_user={}", settings.chat_user)
    save_users(users)


def touch_last_active(username: str) -> None:
    users = load_users()
    if username in users:
        users[username]["last_active"] = datetime.now(timezone.utc).isoformat()
        save_users(users)


def authenticate(username: str, password: str) -> bool:
    users = load_users()
    user = users.get(username)
    if not user:
        # Hash dummy para tiempo constante
        verify_password(password, hash_password("dummy"))
        return False
    return verify_password(password, user.get("password_hash", ""))


def count_conversations_by_user() -> dict:
    """{username: count} desde el log de conversaciones."""
    from app.config import CONVERSATIONS_LOG_PATH

    counts: dict = {}
    if not CONVERSATIONS_LOG_PATH.exists():
        return counts
    try:
        for line in CONVERSATIONS_LOG_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                u = entry.get("username") or "(desconocido)"
                counts[u] = counts.get(u, 0) + 1
            except Exception:
                pass
    except Exception as e:
        logger.error("count_conversations_by_user_failed | {}", e)
    return counts
