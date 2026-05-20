"""Log append-only de conversaciones. Rota automáticamente a 5MB."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from loguru import logger

from app.config import CONVERSATIONS_LOG_PATH, settings

_log_lock = threading.Lock()


def log_conversation(
    username: str,
    user_text: str,
    assistant_text: str,
    agent_id: str | None = None,
) -> None:
    """Append una entrada al log de conversaciones. Rota si el archivo es muy grande."""
    entry: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "username": username or "(anónimo)",
        "user": user_text[:600],
        "assistant": assistant_text[:1200],
    }
    if agent_id:
        entry["agent_id"] = agent_id
    try:
        with _log_lock:
            if (
                CONVERSATIONS_LOG_PATH.exists()
                and CONVERSATIONS_LOG_PATH.stat().st_size > settings.log_rotate_size
            ):
                lines = CONVERSATIONS_LOG_PATH.read_text(encoding="utf-8").splitlines()
                keep = lines[len(lines) // 2:]
                CONVERSATIONS_LOG_PATH.write_text("\n".join(keep) + "\n", encoding="utf-8")
                logger.info("conversations_log_rotated | kept_lines={}", len(keep))
            with open(CONVERSATIONS_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("log_conversation_failed | {}", e)


def read_conversations(user: str | None = None, limit: int = 50) -> list[dict]:
    """Lee las últimas `limit` conversaciones, opcionalmente filtradas por usuario."""
    if not CONVERSATIONS_LOG_PATH.exists():
        return []
    limit = max(1, min(int(limit), 500))
    entries: list[dict] = []
    try:
        lines = CONVERSATIONS_LOG_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if user is not None and entry.get("username", "") != user:
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
            except Exception:
                pass
    except Exception as e:
        logger.error("read_conversations_failed | {}", e)
    return entries
