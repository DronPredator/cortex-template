"""Endpoints admin-only para gestión de agentes (CRUD + edición de prompts)."""

from __future__ import annotations

import asyncio

import document_extract
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from loguru import logger
from pydantic import BaseModel, Field

from app.agents.base import AgentDefinition
from app.agents.knowledge import (
    delete_knowledge_file,
    list_knowledge_files_meta,
    read_knowledge_file,
    save_knowledge_file,
)
from app.agents.registry import (
    delete_agent,
    get_agent,
    list_agents,
    load_agent_prompt,
    save_agent_prompt,
    upsert_agent,
)
from app.auth import verify_admin_token_dep
from app.config import settings
from app.models import AgentUpsertRequest
from app.security.files import safe_filename
from app.security.rate_limit import ADMIN_ACTION_LIMIT, limiter
from app.storage.audit import audit_event


router = APIRouter(tags=["admin-agents"])


class AgentPromptRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)


class KnowledgeFileRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500_000)


# ── Lista completa (incluye privados, con detalle) ────────────────────


@router.get("/api/admin/agents")
def admin_list_agents(_admin: str = Depends(verify_admin_token_dep)):
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "icon": a.icon,
                "icon_url": a.icon_url,
                "allowed_tools": a.allowed_tools,
                "default_tier": a.default_tier,
                "visibility": a.visibility,
                "allowed_users": a.allowed_users,
                "is_default": a.is_default,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            }
            for a in list_agents()
        ]
    }


# ── CRUD ──────────────────────────────────────────────────────────────


@router.post("/api/admin/agents")
@limiter.limit(ADMIN_ACTION_LIMIT)
def admin_upsert_agent(
    req: AgentUpsertRequest,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    """Crea o actualiza un agente. Si `is_default=True`, des-marca el actual default."""
    pre_existing = get_agent(req.id) is not None

    # Resetear is_default en los demás si este es default
    if req.is_default:
        for a in list_agents():
            if a.id != req.id and a.is_default:
                a.is_default = False
                upsert_agent(a)

    agent = AgentDefinition(
        id=req.id,
        name=req.name,
        description=req.description,
        icon=req.icon,
        icon_url=req.icon_url,
        allowed_tools=list(req.allowed_tools),
        default_tier=req.default_tier,
        visibility=req.visibility,
        allowed_users=list(req.allowed_users),
        is_default=req.is_default,
    )
    saved = upsert_agent(agent)

    # Si no existe el prompt en disco aún, crear uno mínimo placeholder
    try:
        load_agent_prompt(saved)
    except Exception:
        pass

    audit_event(
        actor=settings.admin_user,
        action="agent_updated" if pre_existing else "agent_created",
        target=f"agent:{req.id}",
        request=request,
        meta={"visibility": req.visibility, "default_tier": req.default_tier},
    )
    return {"agent": saved.to_dict(), "ok": True}


@router.delete("/api/admin/agents/{agent_id}")
@limiter.limit(ADMIN_ACTION_LIMIT)
def admin_delete_agent(
    agent_id: str,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    try:
        deleted = delete_agent(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    audit_event(
        actor=settings.admin_user,
        action="agent_deleted",
        target=f"agent:{agent_id}",
        request=request,
    )
    return {"ok": True}


# ── Edición de prompts (.md) ──────────────────────────────────────────


@router.get("/api/admin/agents/{agent_id}/prompt")
def admin_get_agent_prompt(
    agent_id: str, _admin: str = Depends(verify_admin_token_dep)
):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    content = load_agent_prompt(agent)
    return {"agent_id": agent_id, "content": content}


@router.put("/api/admin/agents/{agent_id}/prompt")
@limiter.limit(ADMIN_ACTION_LIMIT)
def admin_save_agent_prompt(
    agent_id: str,
    req: AgentPromptRequest,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    save_agent_prompt(agent, req.content)
    logger.info("admin_saved_agent_prompt | id={} bytes={}", agent_id, len(req.content))
    audit_event(
        actor=settings.admin_user,
        action="agent_prompt_saved",
        target=f"agent:{agent_id}",
        request=request,
        meta={"bytes": len(req.content)},
    )
    return {"ok": True, "bytes": len(req.content)}


# ── Knowledge base por agente ─────────────────────────────────────────


@router.get("/api/admin/agents/{agent_id}/knowledge")
def admin_list_knowledge(
    agent_id: str, _admin: str = Depends(verify_admin_token_dep)
):
    """Lista archivos de knowledge del agente con metadata."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return {"agent_id": agent_id, "files": list_knowledge_files_meta(agent_id)}


@router.get("/api/admin/agents/{agent_id}/knowledge/{filename}")
def admin_read_knowledge(
    agent_id: str, filename: str, _admin: str = Depends(verify_admin_token_dep)
):
    """Lee el contenido de un knowledge file (para edición)."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    content = read_knowledge_file(agent_id, filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return {"agent_id": agent_id, "filename": filename, "content": content}


@router.post("/api/admin/agents/{agent_id}/knowledge")
@limiter.limit(ADMIN_ACTION_LIMIT)
def admin_save_knowledge(
    agent_id: str,
    req: KnowledgeFileRequest,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    """Crea o sobrescribe un knowledge file (solo .md). Sanitiza el filename."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")

    saved = save_knowledge_file(agent_id, req.filename, req.content)
    if not saved:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido o no permitido")

    # El filename real puede haber sido sanitizado/normalizado
    clean = safe_filename(req.filename, default="documento.md")
    if not clean.lower().endswith(".md"):
        clean += ".md"

    audit_event(
        actor=settings.admin_user,
        action="agent_knowledge_saved",
        target=f"agent:{agent_id}",
        request=request,
        meta={"filename": clean, "bytes": len(req.content)},
    )
    return {"ok": True, "filename": clean, "bytes": len(req.content)}


@router.delete("/api/admin/agents/{agent_id}/knowledge/{filename}")
@limiter.limit(ADMIN_ACTION_LIMIT)
def admin_delete_knowledge(
    agent_id: str,
    filename: str,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    """Borra un knowledge file."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    ok = delete_knowledge_file(agent_id, filename)
    if not ok:
        raise HTTPException(status_code=404, detail="Archivo no encontrado o nombre inválido")
    audit_event(
        actor=settings.admin_user,
        action="agent_knowledge_deleted",
        target=f"agent:{agent_id}",
        request=request,
        meta={"filename": filename},
    )
    return {"ok": True}


# ── Extracción de texto desde PDF/Word/Excel/PowerPoint/TXT ──────────


_KNOWLEDGE_UPLOAD_MAX_BYTES = 15 * 1024 * 1024  # 15 MB por archivo de conocimiento
_KNOWLEDGE_ACCEPTED_EXT = {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md"}


@router.post("/api/admin/agents/{agent_id}/knowledge/extract")
@limiter.limit(ADMIN_ACTION_LIMIT)
async def admin_extract_knowledge(
    agent_id: str,
    request: Request,
    file: UploadFile = File(...),
    _admin: str = Depends(verify_admin_token_dep),
):
    """Extrae texto de un archivo (PDF/Word/Excel/PowerPoint/TXT/MD) SIN guardarlo.

    Devuelve `{filename_suggested, content}` para que el admin lo revise en el
    frontend y después llame al endpoint POST normal para guardarlo como `.md`.
    Este flujo evita archivos huérfanos en disco si la extracción no sirvió.
    """
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")

    original_name = file.filename or "documento"
    from pathlib import Path as _Path

    ext = _Path(original_name).suffix.lower()
    if ext not in _KNOWLEDGE_ACCEPTED_EXT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato no soportado: {ext or '(sin extensión)'}. "
                "Aceptados: PDF, DOCX, PPTX, XLSX, CSV, TXT, MD."
            ),
        )

    # Lectura en chunks con check de tamaño durante la lectura (anti OOM)
    buf = bytearray()
    chunk_size = 1024 * 1024  # 1 MB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        if len(buf) + len(chunk) > _KNOWLEDGE_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Archivo demasiado grande (máx {_KNOWLEDGE_UPLOAD_MAX_BYTES // 1024 // 1024} MB)",
            )
        buf.extend(chunk)
    data = bytes(buf)

    # MD: no se extrae, se devuelve tal cual
    if ext == ".md":
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
        return {
            "filename_suggested": safe_filename(original_name, default="documento.md"),
            "content": text,
            "char_count": len(text),
        }

    # PDF/DOCX/PPTX/XLSX/CSV/TXT: extracción
    result = await asyncio.to_thread(document_extract.extract, original_name, data)
    if result.get("error"):
        logger.warning(
            "knowledge_extract_failed | agent={} file={} err={}",
            agent_id, original_name, result["error"],
        )
        raise HTTPException(status_code=400, detail=result["error"])

    text = (result.get("text") or "").strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="No se pudo extraer texto del archivo (puede estar escaneado o vacío).",
        )

    # Sugerir nombre .md basado en el original
    base = _Path(original_name).stem
    suggested = safe_filename(base + ".md", default="documento.md")

    # Wrap el texto con un header markdown que cite el archivo original
    md_content = (
        f"# {base}\n\n"
        f"_Extraído de `{original_name}` ({result.get('char_count', len(text))} caracteres)._\n\n"
        f"{text}"
    )

    logger.info(
        "knowledge_extracted | agent={} file={} chars={}",
        agent_id, original_name, len(md_content),
    )
    return {
        "filename_suggested": suggested,
        "content": md_content,
        "char_count": len(md_content),
        "original_filename": original_name,
    }


# ── Upload de icono custom por agente (v1.4.0) ────────────────────────
#
# El admin puede subir un PNG/JPG por agente desde el panel. Se guarda
# en `static/agents/<agent_id>.<ext>` y se actualiza `icon_url` en el
# agents.json con un cache-buster (`?v=<epoch>`) para forzar fetch fresco
# en clientes que tenían un 404 cacheado.
#
# Antes había que dejar los PNGs en disco manualmente; eso causaba el
# bug de "a veces se cargan, a veces no" cuando el archivo no existía
# y el browser cacheaba el 404 negativo.

import time as _time
from pathlib import Path as _PathLib

from app.config import STATIC_DIR as _STATIC_DIR

_ICON_DIR = _STATIC_DIR / "agents"
_ICON_MAX_BYTES = 2 * 1024 * 1024  # 2 MB — los logos no necesitan ser enormes
_ICON_ALLOWED_EXTS = (".png", ".jpg", ".jpeg")
# Magic bytes para validar que el archivo es REALMENTE una imagen, no algo
# renombrado. PNG empieza con \x89PNG\r\n\x1a\n. JPG empieza con \xff\xd8\xff.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPG_MAGIC = b"\xff\xd8\xff"


def _sniff_image_ext(data: bytes) -> str | None:
    """Devuelve '.png' / '.jpg' o None según los magic bytes del archivo.

    No confiamos en la extensión del filename ni el content-type del header —
    un atacante puede mandar un .exe renombrado a .png.
    """
    if data.startswith(_PNG_MAGIC):
        return ".png"
    if data.startswith(_JPG_MAGIC):
        return ".jpg"
    return None


def _clear_existing_icons(agent_id: str) -> int:
    """Borra todos los archivos `<agent_id>.<ext>` existentes en /agents/.
    Devuelve cuántos archivos borró. Idempotente."""
    if not _ICON_DIR.exists():
        return 0
    count = 0
    for ext in _ICON_ALLOWED_EXTS:
        p = _ICON_DIR / f"{agent_id}{ext}"
        if p.exists():
            try:
                p.unlink()
                count += 1
            except OSError as e:
                logger.warning("icon_delete_failed | path={} err={}", p, e)
    return count


@router.post("/api/admin/agents/{agent_id}/icon")
@limiter.limit(ADMIN_ACTION_LIMIT)
async def admin_upload_agent_icon(
    agent_id: str,
    request: Request,
    file: UploadFile = File(...),
    _admin: str = Depends(verify_admin_token_dep),
):
    """Sube un PNG/JPG como icono custom del agente.

    Valida: extensión whitelist, magic bytes reales, tamaño <=2MB, agente
    existe. Borra logos previos del mismo agente (cualquier ext). Actualiza
    `icon_url` con cache-buster `?v=<epoch>` para invalidar el cache viejo
    en los browsers de los usuarios.
    """
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente no encontrado: {agent_id}")

    # Sanity de la extensión declarada (rápido, antes de leer todo el archivo)
    raw_name = file.filename or ""
    declared_ext = _PathLib(raw_name).suffix.lower()
    if declared_ext not in _ICON_ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato no soportado: {declared_ext or '(sin extensión)'}. "
                "Aceptados: PNG, JPG."
            ),
        )

    # Lectura en chunks con límite estricto
    buf = bytearray()
    chunk_size = 256 * 1024  # 256 KB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        if len(buf) + len(chunk) > _ICON_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Icono demasiado grande (máx {_ICON_MAX_BYTES // 1024 // 1024} MB)",
            )
        buf.extend(chunk)
    data = bytes(buf)

    if not data:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    # Validación real por magic bytes — la extensión sola se puede mentir
    real_ext = _sniff_image_ext(data)
    if real_ext is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "El archivo no parece ser una imagen PNG ni JPG válida "
                "(magic bytes no coinciden)."
            ),
        )
    # Aceptamos discrepancia entre extensión declarada y real solo si ambas
    # son PNG/JPG family — pero forzamos guardarlo con la real.
    if declared_ext == ".jpeg":
        declared_ext = ".jpg"

    _ICON_DIR.mkdir(parents=True, exist_ok=True)

    # Borrar versiones anteriores (cualquier ext) para que no quede uno
    # huérfano de cuando subieron PNG y ahora suben JPG.
    _clear_existing_icons(agent_id)

    # Guardar archivo nuevo con la extensión REAL detectada
    filename = f"{agent_id}{real_ext}"
    out_path = _ICON_DIR / filename
    try:
        out_path.write_bytes(data)
    except OSError as e:
        logger.error("icon_write_failed | agent={} err={}", agent_id, e)
        raise HTTPException(status_code=500, detail="No se pudo guardar el icono")

    # Actualizar `icon_url` en agents.json con cache-buster
    cache_buster = int(_time.time())
    new_icon_url = f"/agents/{filename}?v={cache_buster}"
    agent.icon_url = new_icon_url
    upsert_agent(agent)

    audit_event(
        actor=settings.admin_user,
        action="agent_icon_uploaded",
        target=f"agent:{agent_id}",
        meta={
            "filename": filename,
            "size_bytes": len(data),
            "format": real_ext.lstrip("."),
        },
        request=request,
    )
    logger.info(
        "agent_icon_uploaded | agent={} format={} bytes={}",
        agent_id, real_ext, len(data),
    )
    return {
        "ok": True,
        "icon_url": new_icon_url,
        "filename": filename,
        "size_bytes": len(data),
        "format": real_ext.lstrip("."),
    }


@router.delete("/api/admin/agents/{agent_id}/icon")
@limiter.limit(ADMIN_ACTION_LIMIT)
def admin_delete_agent_icon(
    agent_id: str,
    request: Request,
    _admin: str = Depends(verify_admin_token_dep),
):
    """Borra el icono custom del agente. Vuelve al emoji default.

    Idempotente: si no hay icono, igual responde 200 ok=true.
    """
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente no encontrado: {agent_id}")

    deleted = _clear_existing_icons(agent_id)

    if agent.icon_url:
        agent.icon_url = ""
        upsert_agent(agent)

    audit_event(
        actor=settings.admin_user,
        action="agent_icon_deleted",
        target=f"agent:{agent_id}",
        meta={"files_deleted": deleted},
        request=request,
    )
    logger.info("agent_icon_deleted | agent={} files={}", agent_id, deleted)
    return {"ok": True, "files_deleted": deleted}
