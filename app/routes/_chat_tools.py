"""Tool handlers ejecutados desde el chat stream cuando el agente llama tools.

Está separado de la ruta para mantener `chat.py` legible. Cada función:
- recibe los args del modelo
- ejecuta el tool real (catalog_search, verify_pdf_url, etc.)
- devuelve (texto_para_el_modelo, meta_para_thinking_events)
"""

from __future__ import annotations

import asyncio
import json

import datasheet_tools
import office_generators
from loguru import logger

from app.config import DATASHEETS_DIR, DOCUMENTS_DIR, settings
from app.tools.catalog import format_catalog_result
from app.tools.pdf_verify import verify_pdf_url
from app.tools.tavily import format_tavily_results, tavily_search
from search import search_stock


async def handle_catalog_search(args: dict) -> tuple[str, dict]:
    query = str(args.get("query", ""))
    raw_off = args.get("offset", 0)
    try:
        offset = int(raw_off)
    except Exception:
        offset = 0
    data = await asyncio.to_thread(
        search_stock, query, settings.catalog_result_limit, offset
    )
    text = format_catalog_result(query, data)
    return text, {
        "query": query,
        "offset": offset,
        "count": len(data["items"]),
        "total": data["total"],
    }


async def handle_verify_pdf_url(args: dict) -> tuple[str, dict]:
    url = str(args.get("url", ""))
    result = await asyncio.to_thread(verify_pdf_url, url)
    return json.dumps(result, ensure_ascii=False), {
        "url": url,
        "valid": result.get("valid"),
        "reason": result.get("reason"),
        "size_bytes": result.get("size_bytes"),
    }


async def handle_fetch_product_data(args: dict) -> tuple[str, dict]:
    url = str(args.get("url", ""))
    result = await asyncio.to_thread(datasheet_tools.fetch_product_data, url)
    if "text" in result and len(result["text"]) > 6000:
        result["text"] = result["text"][:6000] + "\n[...truncado]"
    return json.dumps(result, ensure_ascii=False), {
        "url": url,
        "title": (result.get("title") or "")[:80],
        "chars": result.get("char_count", 0),
        "tables": result.get("table_count", 0),
        "error": result.get("error"),
    }


async def handle_generate_word(args: dict) -> tuple[str, dict]:
    try:
        result = await asyncio.to_thread(
            office_generators.generate_word_document,
            DOCUMENTS_DIR,
            title=str(args.get("title", "Documento"))[:200],
            subtitle=str(args.get("subtitle", ""))[:200],
            sections=args.get("sections"),
        )
        msg = (
            f"Documento Word generado: {result['url']} ({result['size_bytes']} bytes). "
            "Mostrale al usuario este URL como link descargable."
        )
        return msg, {
            "url": result["url"],
            "filename": result["filename"],
            "size_bytes": result["size_bytes"],
            "generated": True,
            "doc_type": "word",
        }
    except Exception as e:
        logger.error("generate_word_failed | {}", e)
        return f"Error generando Word: {e}", {"error": str(e)[:200]}


async def handle_generate_excel(args: dict) -> tuple[str, dict]:
    try:
        result = await asyncio.to_thread(
            office_generators.generate_excel_spreadsheet,
            DOCUMENTS_DIR,
            title=str(args.get("title", "Planilla"))[:200],
            sheets=args.get("sheets"),
        )
        msg = (
            f"Planilla Excel generada: {result['url']} ({result['size_bytes']} bytes). "
            "Mostrale al usuario este URL como link descargable."
        )
        return msg, {
            "url": result["url"],
            "filename": result["filename"],
            "size_bytes": result["size_bytes"],
            "generated": True,
            "doc_type": "excel",
        }
    except Exception as e:
        logger.error("generate_excel_failed | {}", e)
        return f"Error generando Excel: {e}", {"error": str(e)[:200]}


async def handle_tavily_search(args: dict) -> tuple[str, dict]:
    if not settings.tavily_api_key:
        return "TAVILY_API_KEY no configurada en el servidor.", {"error": "no_key"}
    query = str(args.get("query", ""))
    depth = str(args.get("search_depth", "advanced"))
    try:
        resp = await asyncio.to_thread(tavily_search, query, depth)
        if resp.get("error"):
            return f"Error Tavily: {resp['error']}", {"error": resp["error"][:200]}
        text = format_tavily_results(query, resp)
        return text, {
            "query": query,
            "count": len(resp.get("results", [])),
            "has_answer": bool(resp.get("answer")),
        }
    except Exception as e:
        logger.error("tavily_search_handler_error | {}", e)
        return f"Error en búsqueda Tavily: {e}", {"error": str(e)[:100]}


async def handle_generate_datasheet_pdf(args: dict) -> tuple[str, dict]:
    try:
        raw_spec = args.get("specifications") or {}
        if isinstance(raw_spec, str):
            try:
                raw_spec = json.loads(raw_spec)
            except Exception:
                raw_spec = {"Especificaciones": raw_spec}
        if not isinstance(raw_spec, dict):
            raw_spec = {}

        raw_sources = args.get("source_urls") or []
        if isinstance(raw_sources, str):
            try:
                raw_sources = json.loads(raw_sources)
            except Exception:
                raw_sources = [raw_sources]
        if not isinstance(raw_sources, list):
            raw_sources = []

        result = await asyncio.to_thread(
            datasheet_tools.generate_datasheet_pdf,
            DATASHEETS_DIR,
            title=str(args.get("title", "Ficha técnica"))[:200],
            manufacturer=str(args.get("manufacturer", ""))[:80],
            model=str(args.get("model", ""))[:80],
            description=str(args.get("description", ""))[:3000],
            specifications=raw_spec,
            applications=str(args.get("applications", ""))[:2000],
            source_urls=[str(u) for u in raw_sources[:10]],
        )
        msg = (
            f"PDF generado exitosamente. URL pública: {result['url']} "
            f"({result['size_bytes']} bytes). Mostrale al usuario este URL como link descargable."
        )
        return msg, {
            "url": result["url"],
            "filename": result["filename"],
            "size_bytes": result["size_bytes"],
            "generated": True,
        }
    except Exception as e:
        logger.error("generate_datasheet_pdf_failed | {}", e)
        return f"Error generando PDF: {e}", {"error": str(e)[:200]}


async def dispatch(name: str, args: dict) -> tuple[str, dict]:
    """Router que despacha el tool por nombre."""
    handlers = {
        "catalog_search": handle_catalog_search,
        "verify_pdf_url": handle_verify_pdf_url,
        "fetch_product_data": handle_fetch_product_data,
        "generate_word_document": handle_generate_word,
        "generate_excel_spreadsheet": handle_generate_excel,
        "tavily_search": handle_tavily_search,
        "generate_datasheet_pdf": handle_generate_datasheet_pdf,
    }
    h = handlers.get(name)
    if not h:
        return f"Tool desconocida: {name}", {}
    return await h(args)
