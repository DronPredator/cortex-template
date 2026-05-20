"""Handlers globales de excepciones para FastAPI.

Cuando se rompe algo no esperado, en vez de un stack trace al usuario:
  1. Lo loguemos con full context (request_id, path, traceback)
  2. Devolvemos JSON estructurado al cliente con un `request_id` para soporte
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from app.security.log_sanitize import sanitize_pydantic_errors


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def register_error_handlers(app: FastAPI) -> None:
    """Conectar todos los handlers al app. Llamar en startup."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # 401/403/404/etc esperados: log a INFO, no contaminamos errors.log
        rid = _request_id()
        logger.info(
            "http_exception | rid={} status={} path={} detail={}",
            rid, exc.status_code, request.url.path, exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": rid},
            headers=getattr(exc, "headers", None) or {},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        rid = _request_id()
        # Sanitizar campos sensibles (password, token, etc.) antes de loguear/devolver
        clean_errors = sanitize_pydantic_errors(exc.errors())
        logger.warning(
            "validation_error | rid={} path={} errors={}",
            rid, request.url.path, clean_errors,
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validación de datos falló",
                "errors": clean_errors,
                "request_id": rid,
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        rid = _request_id()
        logger.exception(
            "unhandled_exception | rid={} path={} method={} exc_type={}",
            rid, request.url.path, request.method, type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Error interno del servidor",
                "error_type": type(exc).__name__,
                "request_id": rid,
            },
        )
