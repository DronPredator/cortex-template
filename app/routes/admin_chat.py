"""Chat especial admin → agente meta-editor.

El "agente meta-editor" tiene memoria/conocimiento de los agentes
existentes. Cuando el admin le pide modificar el comportamiento de un
agente, le pregunta cuál y después llama `save_agent_prompt(agent_id,
new_prompt)` para guardar el prompt completo del agente seleccionado.
"""

from __future__ import annotations

import json

import anthropic
import gemini_engine
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger

from app.agents.registry import (
    get_agent,
    list_agents,
    load_agent_prompt,
    save_agent_prompt,
)
from app.auth import verify_admin_token_dep
from app.config import settings
from app.llm.providers import async_anthropic_client
from app.llm.tool_specs import ADMIN_CHAT_TOOLS, SAVE_AGENT_PROMPT_TOOL
from app.models import AdminChatRequest
from app.prompts.loader import admin_prompt
from app.storage.audit import audit_event
from app.storage.memory import load_memory_summary
from app.storage.runtime_config import get_current_model
from search import catalog_size


router = APIRouter(tags=["admin-chat"])


_MAX_PROMPT_BYTES = 50_000


def _agents_summary_for_admin() -> str:
    """Texto markdown con la lista de agentes activos para inyectar al system
    prompt del admin chat. Le permite saber qué agentes existen sin tener que
    llamar una tool de listado."""
    agents = list_agents()
    if not agents:
        return "(No hay agentes configurados aún.)"
    lines = ["| ID | Nombre | Visibilidad | Tools |", "|---|---|---|---|"]
    for a in agents:
        tools = ", ".join(a.allowed_tools) if a.allowed_tools else "(ninguna)"
        lines.append(f"| `{a.id}` | {a.icon} {a.name} | {a.visibility} | {tools[:80]} |")
    return "\n".join(lines)


def _apply_save_agent_prompt(args: dict) -> tuple[str, dict]:
    """Validación + escritura del prompt. Retorna (mensaje_para_modelo, meta)."""
    agent_id = str(args.get("agent_id", "")).strip()
    new_prompt = str(args.get("new_prompt", ""))

    if not agent_id:
        return "ERROR: falta agent_id.", {"saved": False, "error": "missing_agent_id"}
    if len(new_prompt) > _MAX_PROMPT_BYTES:
        return (
            f"ERROR: el prompt excede {_MAX_PROMPT_BYTES} caracteres. "
            "Resumí o dividí en partes.",
            {"saved": False, "error": "too_long"},
        )
    if not new_prompt.strip():
        return "ERROR: el prompt está vacío. Para borrarlo, dejar al menos una línea.", {
            "saved": False, "error": "empty",
        }

    agent = get_agent(agent_id)
    if agent is None:
        ids = ", ".join(a.id for a in list_agents())
        return (
            f"ERROR: no existe el agente '{agent_id}'. Agentes disponibles: {ids}.",
            {"saved": False, "error": "unknown_agent"},
        )

    save_agent_prompt(agent, new_prompt)
    audit_event(
        actor=settings.admin_user,
        action="agent_prompt_saved",
        target=f"agent:{agent_id}",
        meta={"bytes": len(new_prompt), "via": "admin_chat"},
    )
    logger.info("admin_chat_save_agent_prompt | id={} bytes={}", agent_id, len(new_prompt))
    return f"Prompt del agente '{agent.name}' guardado ({len(new_prompt)} caracteres).", {
        "saved": True,
        "agent_id": agent_id,
        "agent_name": agent.name,
        "bytes": len(new_prompt),
    }


@router.post("/api/admin/chat/stream")
async def admin_chat_stream(
    req: AdminChatRequest, _token: str = Depends(verify_admin_token_dep)
):
    async def generate():
        # `custom_prompt` ya no se usa (deprecado). Pasamos string vacío para
        # backward compat con la firma de admin_prompt().
        system = admin_prompt(
            admin_name=settings.admin_user,
            n_items=catalog_size(),
            custom_prompt="",
            memory_summary=load_memory_summary(),
        )
        # Inyectar lista de agentes disponibles para que el meta-editor sepa
        # qué puede editar sin pedir info al usuario.
        system += "\n\n## AGENTES ACTIVOS\n\n" + _agents_summary_for_admin()
        system += (
            "\n\nCuando el admin pida modificar el comportamiento de un agente:\n"
            "1. Si no especificó cuál, preguntale explícitamente. Ofrecé un selector.\n"
            "2. Una vez identificado, leé el prompt actual con `get_agent_prompt` "
            "(no existe esa tool — pedile que copie el prompt actual o cargalo de "
            "memoria si lo recordás).\n"
            "3. Componé el prompt completo modificado (no parches, no diffs — el "
            "texto entero).\n"
            "4. Antes de guardar, mostrá un resumen de los cambios y pedí confirmación.\n"
            "5. Si confirma, llamá `save_agent_prompt(agent_id, new_prompt)`."
        )

        # ── Gemini ────────────────────────────────────────────────
        if settings.llm_uses_gemini:
            async def gemini_admin_tool_handler(name: str, args: dict) -> tuple[str, dict]:
                if name == "save_agent_prompt":
                    return _apply_save_agent_prompt(args)
                return "Tool desconocida", {}

            async for evt in gemini_engine.stream_chat(
                api_key=settings.google_api_key,
                model=get_current_model(),
                system=system,
                messages=list(req.messages),
                tools=ADMIN_CHAT_TOOLS,
                enable_search=False,
                thinking=settings.gemini_thinking,
                tool_handler=gemini_admin_tool_handler,
                max_iterations=settings.max_agent_iterations,
            ):
                etype = evt["type"]
                if etype == "text":
                    yield f"data: {json.dumps({'type': 'text', 'text': evt['text']})}\n\n"
                elif etype == "tool_done":
                    meta = evt.get("meta", {})
                    if meta.get("saved"):
                        yield (
                            f"data: {json.dumps({'type': 'agent_prompt_saved', 'agent_id': meta.get('agent_id', ''), 'agent_name': meta.get('agent_name', ''), 'bytes': meta.get('bytes', 0)})}\n\n"
                        )
                elif etype == "done":
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                elif etype == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': evt.get('message', 'Error desconocido')})}\n\n"
            return

        # ── Anthropic ─────────────────────────────────────────────
        messages = list(req.messages)
        client = async_anthropic_client()
        tools = [SAVE_AGENT_PROMPT_TOOL]
        iterations = 0

        try:
            while iterations < settings.max_agent_iterations:
                iterations += 1
                async with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    system=system,
                    tools=tools,
                    messages=messages,
                ) as stream:
                    async for event in stream:
                        if event.type == "content_block_delta":
                            delta = event.delta
                            if getattr(delta, "type", "") == "text_delta":
                                yield f"data: {json.dumps({'type': 'text', 'text': delta.text})}\n\n"
                    final_message = await stream.get_final_message()

                if final_message.stop_reason == "end_turn":
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

                if final_message.stop_reason == "tool_use":
                    tool_results = []
                    for block in final_message.content:
                        if block.type != "tool_use":
                            continue
                        if block.name == "save_agent_prompt":
                            args = block.input if isinstance(block.input, dict) else {}
                            msg, meta = _apply_save_agent_prompt(args)
                            if meta.get("saved"):
                                yield (
                                    f"data: {json.dumps({'type': 'agent_prompt_saved', 'agent_id': meta.get('agent_id', ''), 'agent_name': meta.get('agent_name', ''), 'bytes': meta.get('bytes', 0)})}\n\n"
                                )
                            result_text = msg
                        else:
                            result_text = "OK"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        })
                    messages.append({"role": "assistant", "content": final_message.content})
                    messages.append({"role": "user", "content": tool_results})
                    continue

                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'error', 'message': 'Máximo de iteraciones alcanzado.'})}\n\n"

        except anthropic.APIError as e:
            logger.error("admin_chat_anthropic_error | {}", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            logger.exception("admin_chat_unexpected_error")
            yield f"data: {json.dumps({'type': 'error', 'message': f'Error interno: {e}'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
