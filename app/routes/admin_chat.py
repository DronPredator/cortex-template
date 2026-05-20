"""Chat especial admin → agente, donde el agente puede modificar su propio prompt."""

from __future__ import annotations

import json

import anthropic
import gemini_engine
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger

from app.auth import verify_admin_token_dep
from app.config import SYSTEM_PROMPT_CUSTOM_PATH, settings
from app.llm.providers import async_anthropic_client
from app.llm.tool_specs import ADMIN_CHAT_TOOLS, SAVE_BEHAVIOR_TOOL
from app.models import AdminChatRequest
from app.prompts.loader import admin_prompt
from app.storage.atomic import atomic_write
from app.storage.memory import load_custom_prompt, load_memory_summary
from app.storage.runtime_config import get_current_model
from search import catalog_size


router = APIRouter(tags=["admin-chat"])


@router.post("/api/admin/chat/stream")
async def admin_chat_stream(
    req: AdminChatRequest, _token: str = Depends(verify_admin_token_dep)
):
    async def generate():
        system = admin_prompt(
            admin_name=settings.admin_user,
            n_items=catalog_size(),
            custom_prompt=load_custom_prompt(),
            memory_summary=load_memory_summary(),
        )

        # ── Gemini ────────────────────────────────────────────────
        if settings.llm_uses_gemini:
            async def gemini_admin_tool_handler(name: str, args: dict) -> tuple[str, dict]:
                if name == "save_behavior":
                    new_prompt = str(args.get("new_custom_prompt", ""))[:settings.custom_prompt_max]
                    atomic_write(SYSTEM_PROMPT_CUSTOM_PATH, new_prompt)
                    logger.info("save_behavior_called | chars={}", len(new_prompt))
                    return "Comportamiento guardado exitosamente.", {
                        "new_prompt": new_prompt,
                        "saved": True,
                    }
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
                        yield f"data: {json.dumps({'type': 'behavior_saved', 'new_prompt': meta.get('new_prompt', '')})}\n\n"
                elif etype == "done":
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                elif etype == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': evt.get('message', 'Error desconocido')})}\n\n"
            return

        # ── Anthropic ─────────────────────────────────────────────
        messages = list(req.messages)
        client = async_anthropic_client()
        tools = [SAVE_BEHAVIOR_TOOL]
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
                        if block.name == "save_behavior":
                            new_prompt = (
                                block.input.get("new_custom_prompt", "")
                                if isinstance(block.input, dict) else ""
                            )
                            new_prompt = new_prompt[:settings.custom_prompt_max]
                            atomic_write(SYSTEM_PROMPT_CUSTOM_PATH, new_prompt)
                            yield f"data: {json.dumps({'type': 'behavior_saved', 'new_prompt': new_prompt})}\n\n"
                            result_text = "Comportamiento guardado exitosamente."
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
