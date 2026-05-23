"""Gemini provider — streams text + function calls compatible with the frontend SSE protocol.

Events yielded:
    {"type": "text", "text": "..."}
    {"type": "reasoning", "text": "..."}                    # model's thoughts
    {"type": "truncated", "reason": "max_tokens"}           # response cut off
    {"type": "tool_start", "name": "...", "args": {...}, "id": "..."}
    {"type": "tool_done",  "name": "...", "args": {...}, "id": "...", "meta": {...}}
    {"type": "done"}
    {"type": "error", "message": "..."}
"""

from typing import Any, AsyncGenerator, Awaitable, Callable

from google import genai
from google.genai import types


# ── Anthropic ↔ Gemini format conversion ─────────────────────────────────────

def _thinking_budget(level: str) -> int | None:
    """Convert the GEMINI_THINKING env var to a thinking_budget value."""
    level = (level or "").lower().strip()
    if level == "off":
        return 0
    if level == "high":
        return 8192
    # auto / dynamic → None (model default)
    return None


_GEMINI_TYPE_MAP = {
    "string":  "STRING",
    "integer": "INTEGER",
    "number":  "NUMBER",
    "boolean": "BOOLEAN",
    "object":  "OBJECT",
    "array":   "ARRAY",
}


def _anth_schema_to_gemini(defn: dict) -> types.Schema:
    """Recursively convert an Anthropic JSON-schema dict to Gemini Schema."""
    t = _GEMINI_TYPE_MAP.get(str(defn.get("type", "string")).lower(), "STRING")
    desc = defn.get("description", "")

    if t == "ARRAY":
        items_def = defn.get("items") or {"type": "string"}
        return types.Schema(
            type="ARRAY",
            description=desc,
            items=_anth_schema_to_gemini(items_def),
        )

    if t == "OBJECT":
        # If `properties` exists, convert recursively. Otherwise downgrade
        # to STRING (Gemini requires at least one property in OBJECT).
        props = defn.get("properties") or {}
        if not props:
            return types.Schema(
                type="STRING",
                description=(desc + " (format: JSON-encoded string)").strip(),
            )
        gprops = {k: _anth_schema_to_gemini(v) for k, v in props.items()}
        return types.Schema(
            type="OBJECT",
            description=desc,
            properties=gprops,
            required=list(defn.get("required", []) or []),
        )

    return types.Schema(type=t, description=desc)


def _convert_tool(tool: dict) -> types.FunctionDeclaration:
    """Anthropic tool dict → Gemini FunctionDeclaration."""
    schema = tool.get("input_schema", {})
    props_anth = schema.get("properties", {})
    required   = schema.get("required", []) or []

    props_gemini = {k: _anth_schema_to_gemini(v) for k, v in props_anth.items()}

    return types.FunctionDeclaration(
        name=tool["name"],
        description=tool.get("description", ""),
        parameters=types.Schema(
            type="OBJECT",
            properties=props_gemini,
            required=list(required),
        ),
    )


def _convert_messages(messages: list[dict]) -> list[types.Content]:
    """Anthropic-style message list → Gemini list[types.Content]."""
    result: list[types.Content] = []
    for msg in messages:
        role = msg.get("role", "user")
        gemini_role = "model" if role == "assistant" else "user"
        content = msg.get("content")
        parts: list[types.Part] = []

        if isinstance(content, str):
            if content:
                parts.append(types.Part(text=content))
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    txt = block.get("text", "")
                    if txt:
                        parts.append(types.Part(text=txt))
                elif btype == "image":
                    src = block.get("source", {})
                    if src.get("type") == "base64":
                        try:
                            import base64
                            raw = base64.b64decode(src.get("data", ""))
                            parts.append(types.Part.from_bytes(
                                data=raw,
                                mime_type=src.get("media_type", "image/png"),
                            ))
                        except Exception:
                            pass
                elif btype == "tool_use":
                    parts.append(types.Part(function_call=types.FunctionCall(
                        name=block.get("name", ""),
                        args=block.get("input", {}) or {},
                    )))
                elif btype == "tool_result":
                    raw_content = block.get("content", "")
                    if isinstance(raw_content, list):
                        # Anthropic may send a list of blocks; pull out the text
                        raw_content = " ".join(
                            b.get("text", "") for b in raw_content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    parts.append(types.Part(function_response=types.FunctionResponse(
                        name=block.get("name", "tool"),
                        response={"result": str(raw_content)},
                    )))

        if parts:
            result.append(types.Content(role=gemini_role, parts=parts))
    return result


# ── Main streaming loop ───────────────────────────────────────────────────────

ToolHandler = Callable[[str, dict], Awaitable[tuple[str, dict]]]


async def stream_chat(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    enable_search: bool = False,
    thinking: str = "auto",
    tool_handler: ToolHandler | None = None,
    max_iterations: int = 12,
) -> AsyncGenerator[dict, None]:
    """Stream un chat con Gemini, con loop agéntico para function calling."""
    if not api_key:
        yield {"type": "error", "message": "GOOGLE_API_KEY no está configurada"}
        return

    client = genai.Client(api_key=api_key)
    contents = _convert_messages(messages)

    # NOTE — Language of model thoughts:
    # Gemini with `include_thoughts=True` reasons in English by default.
    # If your deployment needs to force a specific language (e.g. Spanish),
    # prepend the directive to `system` BEFORE calling this function —
    # from `app/routes/chat.py` which has access to `settings`. We do not
    # couple the engine to a specific language here, to keep the template
    # reusable across deployments.
    #
    # Example usage from chat.py:
    #     if settings.language_directive:
    #         system_str = settings.language_directive + "\n\n" + system_str

    # Tools
    gemini_tools: list[types.Tool] = []
    has_functions = bool(tools)
    if has_functions:
        gemini_tools.append(types.Tool(function_declarations=[_convert_tool(t) for t in tools]))
    # Gemini 3.x permite combinar google_search + function_declarations.
    # En generaciones previas estaba bloqueado — si el modelo lo rechaza, el error sale al stream.
    if enable_search:
        try:
            gemini_tools.append(types.Tool(google_search=types.GoogleSearch()))
        except Exception:
            pass

    budget = _thinking_budget(thinking)
    # include_thoughts=True makes Gemini return the model's thoughts as
    # separate parts with .thought=True. We stream them to the frontend as
    # "reasoning" events to show them live in the collapsible panel.
    # Only makes sense when thinking is enabled (budget != 0).
    if budget == 0:
        thinking_cfg = types.ThinkingConfig(thinking_budget=0)
    elif budget is not None:
        thinking_cfg = types.ThinkingConfig(thinking_budget=budget, include_thoughts=True)
    else:
        thinking_cfg = types.ThinkingConfig(include_thoughts=True)

    # When combining function_declarations + google_search, Gemini 3.x
    # requires this flag to return server-side tool invocations.
    tool_config = None
    if has_functions and enable_search:
        tool_config = types.ToolConfig(include_server_side_tool_invocations=True)

    # max_output_tokens=16384 — large enough for detailed technical
    # responses without forcing the user to type "continue" mid-answer.
    # Gemini 3.5 Flash supports up to 65,536 output tokens; 16K is a
    # safe default (the limit is a cap, not a target — short answers
    # stay short).
    config = types.GenerateContentConfig(
        system_instruction=system or None,
        tools=gemini_tools or None,
        tool_config=tool_config,
        thinking_config=thinking_cfg,
        max_output_tokens=16384,
    )

    # Only the tools we declared client-side run via tool_handler.
    # Gemini's built-in tools (google_search, etc.) are handled server-side.
    client_tool_names = {t["name"] for t in (tools or [])}

    iterations = 0

    try:
        while iterations < max_iterations:
            iterations += 1
            pending_calls: list[types.FunctionCall] = []
            assistant_parts: list[types.Part] = []

            stream = await client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )

            emitted_search_queries: set[str] = set()
            last_finish_reason: str = ""  # Track to detect MAX_TOKENS truncation
            async for chunk in stream:
                cands = getattr(chunk, "candidates", None) or []
                if not cands:
                    continue
                # Track finish_reason from the latest chunk. If it ended with
                # MAX_TOKENS, the response was truncated and the frontend
                # should show a "Continue" button instead of cutting off
                # silently.
                fr = getattr(cands[0], "finish_reason", None)
                if fr is not None:
                    last_finish_reason = str(fr).split(".")[-1]  # "MAX_TOKENS" / "STOP" / etc.
                # Surface Google Search queries from grounding_metadata
                gm = getattr(cands[0], "grounding_metadata", None)
                if gm:
                    queries = getattr(gm, "web_search_queries", None) or []
                    for q in queries:
                        if q and q not in emitted_search_queries:
                            emitted_search_queries.add(q)
                            yield {"type": "thinking", "tool": "web_search", "query": str(q)[:120], "status": "done"}
                content = getattr(cands[0], "content", None)
                if not content:
                    continue
                for part in (content.parts or []):
                    text = getattr(part, "text", None)
                    # If the part is a "thought" (model's internal reasoning),
                    # emit it as a "reasoning" event so the frontend shows it
                    # in the collapsible panel — does NOT go into the visible
                    # response body.
                    is_thought = bool(getattr(part, "thought", False))
                    if text:
                        if is_thought:
                            yield {"type": "reasoning", "text": text}
                        else:
                            yield {"type": "text", "text": text}
                    fc = getattr(part, "function_call", None)
                    if fc and fc.name and fc.name in client_tool_names:
                        # Client-declared tool → we run it via tool_handler
                        pending_calls.append(fc)
                    elif fc and fc.name:
                        # Gemini built-in tool (google_search). Notify frontend.
                        args = dict(fc.args) if fc.args else {}
                        q = args.get("query", args.get("queries", str(args))) if args else ""
                        if isinstance(q, list): q = ", ".join(map(str, q))
                        yield {"type": "thinking", "tool": "web_search", "query": str(q)[:120], "status": "done"}
                    # Preserve the original part (with its thought_signature
                    # if applicable) to send back to Gemini in the next turn.
                    assistant_parts.append(part)

            if not pending_calls:
                # If the model was cut off by MAX_TOKENS, notify the frontend
                # BEFORE done so it can render a "Continue" button.
                if last_finish_reason == "MAX_TOKENS":
                    yield {"type": "truncated", "reason": "max_tokens"}
                yield {"type": "done"}
                return

            # Process all function calls from this turn
            tool_response_parts: list[types.Part] = []
            for idx, fc in enumerate(pending_calls):
                args = dict(fc.args) if fc.args else {}
                call_id = f"call_{iterations}_{idx}_{fc.name}"
                yield {"type": "tool_start", "name": fc.name, "args": args, "id": call_id}

                if tool_handler:
                    try:
                        result_text, meta = await tool_handler(fc.name, args)
                    except Exception as e:
                        result_text, meta = f"Error running {fc.name}: {e}", {"error": str(e)}
                else:
                    result_text, meta = "OK", {}

                yield {"type": "tool_done", "name": fc.name, "args": args, "id": call_id, "meta": meta}

                tool_response_parts.append(types.Part(function_response=types.FunctionResponse(
                    name=fc.name,
                    response={"result": str(result_text)},
                )))

            # Append the model's turn (with its function_calls) + our responses
            if assistant_parts:
                contents.append(types.Content(role="model", parts=assistant_parts))
            contents.append(types.Content(role="user", parts=tool_response_parts))
            # Continue the loop

        yield {"type": "error", "message": "Max agent iterations reached."}

    except Exception as e:
        yield {"type": "error", "message": f"Gemini error: {e}"}
