"""Endpoint de subida de documentos (PDF/DOCX/PPTX/XLSX/CSV/TXT).

Extrae el texto y lo devuelve al frontend, que lo pasa como system_context
en el siguiente mensaje del chat.
"""

from __future__ import annotations

import asyncio

import document_extract
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger

from app.auth import verify_token_dep
from app.config import settings
from app.security.files import safe_filename


router = APIRouter(tags=["upload"])

_UPLOAD_CHUNK_SIZE = 1024 * 1024


@router.post("/api/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    username: str = Depends(verify_token_dep),
):
    # Sanitizar filename — evita path traversal, caracteres ilegales, hidden files
    fn = safe_filename(file.filename or "documento")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            max_mb = settings.max_upload_bytes // 1024 // 1024
            raise HTTPException(
                status_code=413,
                detail=f"Archivo demasiado grande (máx {max_mb} MB)",
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    result = await asyncio.to_thread(document_extract.extract, fn, data)
    if result.get("error"):
        logger.warning(
            "upload_document_error | user={} file={} err={}",
            username, fn, result["error"],
        )
        raise HTTPException(status_code=400, detail=result["error"])

    logger.info(
        "upload_document_ok | user={} file={} chars={}",
        username, fn, result["char_count"],
    )
    return {
        "filename": result["filename"],
        "char_count": result["char_count"],
        "text": result["text"],
    }
