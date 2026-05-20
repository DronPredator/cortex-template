"""Configuración de logging con loguru.

Reemplaza print() / except:pass por logs estructurados accesibles desde
`logs/cortex.log` (rotado automáticamente). También pinta en consola con colores.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from app.config import BASE_DIR

_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Llamar UNA VEZ al startup. Idempotente."""
    global _configured
    if _configured:
        return

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Sacamos el sink default que loguru agrega solo
    logger.remove()

    # Consola — formato compacto con colores
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    # Archivo — todos los niveles, rotación diaria, retención 14 días
    logger.add(
        log_dir / "cortex.log",
        level="DEBUG",
        rotation="00:00",
        retention="14 days",
        compression="zip",
        enqueue=True,  # thread-safe
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | "
            "{name}:{function}:{line} | {message}"
        ),
    )

    # Archivo separado para errores (más fácil de auditar)
    logger.add(
        log_dir / "cortex_errors.log",
        level="ERROR",
        rotation="1 week",
        retention="30 days",
        compression="zip",
        backtrace=True,
        diagnose=True,  # incluye valores de variables en el stack trace
        enqueue=True,
    )

    _configured = True
    logger.info("logging_initialized", level=level, log_dir=str(log_dir))


def get_logger():
    """Devuelve el logger global de loguru."""
    return logger
