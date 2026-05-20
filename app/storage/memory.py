"""Memoria del agente — análisis recurrente del log de conversaciones."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from loguru import logger

from app.config import CONVERSATIONS_LOG_PATH, MEMORY_PATH, settings
from app.storage.atomic import atomic_write
from app.storage.runtime_config import get_current_model


def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return {}
    try:
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("load_memory_failed | {}", e)
        return {}


def load_memory_summary() -> str:
    """Resumen breve de la memoria — primeras 12 líneas con timestamp."""
    data = load_memory()
    content = data.get("content", "")
    if not content:
        return "(sin memoria generada aún)"
    gen_at = data.get("generated_at", "")[:10]
    brief = "\n".join(content.split("\n")[:12])
    return f"[Generada: {gen_at}]\n{brief}"


def load_custom_prompt() -> str:
    from app.config import SYSTEM_PROMPT_CUSTOM_PATH

    if SYSTEM_PROMPT_CUSTOM_PATH.exists():
        return SYSTEM_PROMPT_CUSTOM_PATH.read_text(encoding="utf-8").strip()
    return ""


def generate_memory() -> dict:
    """Analiza las últimas 200 conversaciones y produce un resumen markdown."""
    try:
        if not CONVERSATIONS_LOG_PATH.exists():
            return {"error": "No hay conversaciones registradas aún."}

        lines = CONVERSATIONS_LOG_PATH.read_text(encoding="utf-8").splitlines()
        recent = [l for l in lines[-200:] if l.strip()]
        entries: list[dict] = []
        for line in recent:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

        if not entries:
            return {"error": "No hay conversaciones suficientes para analizar."}

        convs_text = "\n\n".join(
            [
                f"[{e.get('ts','')[:10]}] Usuario: {e.get('user','')}\nAgente: {e.get('assistant','')[:300]}"
                for e in entries
            ]
        )

        analysis_prompt = (
            f"Analizá estas {len(entries)} conversaciones recientes del chatbot del cliente "
            "y generá un resumen de memoria estructurado en español:\n\n"
            f"{convs_text}\n\n"
            "Generá un análisis con estas secciones:\n"
            "## Temas más consultados\n"
            "## Marcas y productos más buscados\n"
            "## Patrones de uso detectados\n"
            "## Observaciones del período\n"
            "## Sugerencias para mejorar el agente\n\n"
            "Sé conciso, directo y útil. Formato markdown."
        )

        content = ""
        last_err: Exception | None = None

        if settings.llm_uses_gemini:
            if not settings.google_api_key:
                return {"error": "GOOGLE_API_KEY no configurada."}
            from google import genai as _genai

            _client = _genai.Client(api_key=settings.google_api_key)
            _candidates = [
                get_current_model(),
                "gemini-2.0-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash-lite",
            ]
            for _model in _candidates:
                try:
                    _resp = _client.models.generate_content(
                        model=_model, contents=analysis_prompt
                    )
                    content = _resp.text or ""
                    break
                except Exception as _e:
                    last_err = _e
                    continue
            if not content:
                return {
                    "error": f"Todos los modelos de Gemini fallaron. Último error: {last_err}"
                }
        else:
            if not settings.anthropic_api_key:
                return {"error": "ANTHROPIC_API_KEY no configurada."}
            import anthropic

            _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            _resp = _client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                messages=[{"role": "user", "content": analysis_prompt}],
            )
            content = _resp.content[0].text if _resp.content else ""

        data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "conversations_analyzed": len(entries),
            "content": content,
        }
        atomic_write(MEMORY_PATH, json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("memory_generated | conversations={} chars={}", len(entries), len(content))
        return data

    except Exception as e:
        logger.exception("generate_memory_failed")
        return {"error": str(e)}


async def memory_refresh_loop() -> None:
    """Tarea de fondo que regenera memoria cada 24 horas."""
    while True:
        try:
            await asyncio.sleep(24 * 3600)
            await asyncio.to_thread(generate_memory)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("memory_refresh_loop_error | {}", e)
