"""Gemini provider — streams text + function calls compatible con SSE del frontend.

Eventos que yieldea:
    {"type": "text", "text": "..."}
    {"type": "tool_start", "name": "...", "args": {...}, "id": "..."}
    {"type": "tool_done",  "name": "...", "args": {...}, "id": "...", "meta": {...}}
    {"type": "done"}
    {"type": "error", "message": "..."}
"""

from typing import Any, AsyncGenerator, Awaitable, Callable

from google import genai
from google.genai import types


# ── Conversión de formatos Anthropic ↔ Gemini ─────────────────────────────────

def _thinking_budget(level: str) -> int | None:
    """Convierte el env var GEMINI_THINKING a thinking_budget."""
    level = (level or "").lower().strip()
    if level == "off":
        return 0
    if level == "high":
        return 8192
    # auto / dinámico → None (default del modelo)
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
        # Si tiene `properties`, convertimos recursivo. Si no, downgrade a STRING
        # (Gemini exige al menos un propertie en OBJECT).
        props = defn.get("properties") or {}
        if not props:
            return types.Schema(
                type="STRING",
                description=(desc + " (formato: JSON-encoded string)").strip(),
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
    """Lista de mensajes estilo Anthropic → list[types.Content] de Gemini."""
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
                        # Anthropic puede mandar listas de blocks; tomamos el texto
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


# ── Streaming principal ───────────────────────────────────────────────────────

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

    # NOTA — Idioma de los thoughts:
    # Gemini con include_thoughts=True razona en inglés por default. Si
    # tu despliegue necesita forzar otro idioma (ej. español), prepend
    # la directiva al `system` ANTES de llamar a esta función — desde
    # `app/routes/chat.py` que ya tiene acceso a `settings`. Acá no
    # acoplamos el engine a un idioma específico para que el template
    # sea reusable.
    #
    # Ejemplo de uso desde chat.py:
    #   if settings.language_directive:
    #       system_str = settings.language_directive + "\n\n" + system_str

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
    # include_thoughts=True hace que Gemini devuelva los "thoughts" (razonamiento
    # del modelo) como parts separados con .thought=True. Los streameamos al
    # frontend como evento "reasoning" para mostrarlos en vivo en el panel.
    # Solo tiene sentido si el thinking está habilitado (budget != 0).
    if budget == 0:
        thinking_cfg = types.ThinkingConfig(thinking_budget=0)
    elif budget is not None:
        thinking_cfg = types.ThinkingConfig(thinking_budget=budget, include_thoughts=True)
    else:
        thinking_cfg = types.ThinkingConfig(include_thoughts=True)

    # Cuando combinamos function_declarations + google_search,
    # Gemini 3.x exige este flag para devolver las invocaciones de tools server-side.
    tool_config = None
    if has_functions and enable_search:
        tool_config = types.ToolConfig(include_server_side_tool_invocations=True)

    config = types.GenerateContentConfig(
        system_instruction=system or None,
        tools=gemini_tools or None,
        tool_config=tool_config,
        thinking_config=thinking_cfg,
        max_output_tokens=4096,
    )

    # Solo las tools que declaramos client-side se ejecutan vía tool_handler.
    # Las built-in de Gemini (google_search, etc.) las maneja el servidor.
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
            async for chunk in stream:
                cands = getattr(chunk, "candidates", None) or []
                if not cands:
                    continue
                # Surface Google Search queries del grounding_metadata
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
                    # Si el part es un "thought" (razonamiento interno del modelo),
                    # lo emitimos como evento "reasoning" para que el frontend
                    # lo muestre en el panel colapsible — NO va al cuerpo de la
                    # respuesta visible.
                    is_thought = bool(getattr(part, "thought", False))
                    if text:
                        if is_thought:
                            yield {"type": "reasoning", "text": text}
                        else:
                            yield {"type": "text", "text": text}
                    fc = getattr(part, "function_call", None)
                    if fc and fc.name and fc.name in client_tool_names:
                        # Tool declarada por nosotros → ejecutamos client-side
                        pending_calls.append(fc)
                    elif fc and fc.name:
                        # Tool built-in de Gemini (google_search). Avisamos al frontend.
                        args = dict(fc.args) if fc.args else {}
                        q = args.get("query", args.get("queries", str(args))) if args else ""
                        if isinstance(q, list): q = ", ".join(map(str, q))
                        yield {"type": "thinking", "tool": "web_search", "query": str(q)[:120], "status": "done"}
                    # Preservamos el part original (con su thought_signature si aplica)
                    # para mandárselo a Gemini en el próximo turno.
                    assistant_parts.append(part)

            if not pending_calls:
                yield {"type": "done"}
                return

            # Procesar todas las function calls de este turno
            tool_response_parts: list[types.Part] = []
            for idx, fc in enumerate(pending_calls):
                args = dict(fc.args) if fc.args else {}
                call_id = f"call_{iterations}_{idx}_{fc.name}"
                yield {"type": "tool_start", "name": fc.name, "args": args, "id": call_id}

                if tool_handler:
                    try:
                        result_text, meta = await tool_handler(fc.name, args)
                    except Exception as e:
                        result_text, meta = f"Error ejecutando {fc.name}: {e}", {"error": str(e)}
                else:
                    result_text, meta = "OK", {}

                yield {"type": "tool_done", "name": fc.name, "args": args, "id": call_id, "meta": meta}

                tool_response_parts.append(types.Part(function_response=types.FunctionResponse(
                    name=fc.name,
                    response={"result": str(result_text)},
                )))

            # Append turno del modelo (con sus function_calls) + nuestras respuestas
            if assistant_parts:
                contents.append(types.Content(role="model", parts=assistant_parts))
            contents.append(types.Content(role="user", parts=tool_response_parts))
            # Continuar loop

        yield {"type": "error", "message": "Máximo de iteraciones alcanzado en el agente."}

    except Exception as e:
        yield {"type": "error", "message": f"Error de Gemini: {e}"}
