"""Backups automáticos diarios de los archivos críticos del runtime.

Snapshot diario a `backups/YYYY-MM-DD/` con copias de:
- users.json
- agents.json
- conversations_log.jsonl
- memory.json
- runtime_config.json
- system_prompt_custom.txt
- audit_log.jsonl

Política de retención: mantiene los últimos N días (default 14), borra
carpetas más viejas.

Se ejecuta como tarea async en el lifespan del app. Cada 24h.

NOTA: este es un backup LOCAL — no protege contra fallas de disco o
robo del equipo. Para producción crítica, complementarlo con backup
remoto (rsync a otro server, o sync a cloud storage).
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

from app.config import (
    AGENTS_PATH,
    AUDIT_LOG_PATH,
    BACKUP_RETENTION_DAYS,
    BACKUPS_DIR,
    CONVERSATIONS_LOG_PATH,
    MEMORY_PATH,
    RUNTIME_CONFIG_PATH,
    SYSTEM_PROMPT_CUSTOM_PATH,
    USERS_PATH,
)


BACKUP_INTERVAL_SECONDS = 24 * 3600  # 24h


def _files_to_backup() -> list[Path]:
    return [
        USERS_PATH,
        AGENTS_PATH,
        CONVERSATIONS_LOG_PATH,
        MEMORY_PATH,
        RUNTIME_CONFIG_PATH,
        SYSTEM_PROMPT_CUSTOM_PATH,
        AUDIT_LOG_PATH,
    ]


def run_backup_now() -> dict:
    """Hace un backup inmediato. Retorna stats."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_dir = BACKUPS_DIR / today
    target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    errors = 0
    for src in _files_to_backup():
        if not src.exists():
            skipped += 1
            continue
        try:
            dst = target_dir / src.name
            shutil.copy2(src, dst)
            copied += 1
        except Exception as e:
            logger.error("backup_file_failed | src={} err={}", src.name, e)
            errors += 1

    stats = {"date": today, "copied": copied, "skipped": skipped, "errors": errors}
    logger.info(
        "backup_run | date={} copied={} skipped={} errors={}",
        today, copied, skipped, errors,
    )
    return stats


def _prune_old_backups() -> int:
    """Borra carpetas de backup más viejas que BACKUP_RETENTION_DAYS."""
    if not BACKUPS_DIR.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=BACKUP_RETENTION_DAYS)
    removed = 0
    for child in BACKUPS_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            # Carpetas se llaman YYYY-MM-DD
            folder_date = datetime.strptime(child.name, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            if folder_date < cutoff:
                shutil.rmtree(child)
                removed += 1
                logger.info("backup_pruned | folder={}", child.name)
        except (ValueError, Exception) as e:
            logger.warning("backup_prune_skipped | folder={} err={}", child.name, e)
    return removed


async def backup_loop():
    """Loop que corre backup_now() cada 24h. Pensado para asyncio.create_task()."""
    while True:
        try:
            run_backup_now()
            _prune_old_backups()
        except Exception as e:
            logger.exception("backup_loop_error: {}", e)
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
