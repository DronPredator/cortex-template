"""Generación y rotación diaria de ejemplos de consultas por agente.

Combina dos fuentes:
1. `seed_examples` definidos en el AgentDefinition (estáticos, siempre disponibles).
2. Ejemplos generados dinámicamente por Gemini Flash Lite analizando las
   conversaciones reales filtradas por `agent_id`. Se regeneran cada 24h
   (junto con el `memory_refresh_loop`) y se cachean en `memory.json` bajo
   el campo `examples_by_agent`.

Rotación: cada día se muestran 3 ejemplos elegidos con un PRNG cuya seed
es la fecha (YYYY-MM-DD). Todos los users ven los mismos 3 ese día. Al
día siguiente, los 3 son distintos (si hay material para rotar).
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone

from loguru import logger

from app.config import CONVERSATIONS_LOG_PATH, MEMORY_PATH, settings
from app.storage.atomic import atomic_write


_MAX_CONVERSATIONS_PER_AGENT = 80
_MAX_EXAMPLES_PER_AGENT = 7


def _load_memory_raw() -> dict:
    if not MEMORY_PATH.exists():
        return {}
    try:
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_memory_raw(data: dict) -> None:
    atomic_write(MEMORY_PATH, json.dumps(data, ensure_ascii=False, indent=2))


def _cached_examples() -> dict[str, list[str]]:
    """Lee ejemplos cacheados desde memory.json (campo examples_by_agent)."""
    raw = _load_memory_raw()
    out = raw.get("examples_by_agent", {})
    if not isinstance(out, dict):
        return {}
    # Sanity: asegurar que cada valor es lista de strings
    clean: dict[str, list[str]] = {}
    for k, v in out.items():
        if isinstance(v, list):
            clean[str(k)] = [str(x) for x in v if isinstance(x, str) and x.strip()]
    return clean


def _conversations_by_agent() -> dict[str, list[dict]]:
    """Agrupa las últimas conversaciones por agent_id."""
    if not CONVERSATIONS_LOG_PATH.exists():
        return {}
    out: dict[str, list[dict]] = {}
    try:
        lines = CONVERSATIONS_LOG_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):  # más recientes primero
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            aid = entry.get("agent_id") or "fidi"
            bucket = out.setdefault(aid, [])
            if len(bucket) < _MAX_CONVERSATIONS_PER_AGENT:
                bucket.append(entry)
    except Exception as e:
        logger.error("conversations_by_agent_failed | {}", e)
    return out


def _generate_with_gemini(prompt: str) -> str:
    """Llama a Gemini Flash Lite para generar ejemplos. Devuelve '' si falla."""
    if not settings.google_api_key:
        return ""
    try:
        from google import genai as _genai

        client = _genai.Client(api_key=settings.google_api_key)
        # Modelo Flash Lite — el más barato disponible
        for model_id in (
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
        ):
            try:
                resp = client.models.generate_content(model=model_id, contents=prompt)
                text = (resp.text or "").strip()
                if text:
                    return text
            except Exception:
                continue
    except Exception as e:
        logger.warning("examples_gemini_failed | {}", e)
    return ""


def _parse_examples_from_response(text: str) -> list[str]:
    """Extrae ejemplos de la respuesta del LLM.

    Tolerante a varios formatos: lista numerada, viñetas, líneas sueltas.
    Filtra líneas muy cortas o que parecen meta-comentarios.
    """
    if not text:
        return []
    out: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Quitar prefijos comunes: "1.", "1)", "- ", "* ", "•", etc.
        for prefix in ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.",
                       "1)", "2)", "3)", "4)", "5)", "6)", "7)", "8)", "9)", "10)"):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        if line.startswith(("- ", "* ", "•", "·")):
            line = line[2:].strip()
        # Quitar comillas envolventes
        if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
            line = line[1:-1].strip()
        # Filtros básicos
        if len(line) < 15 or len(line) > 200:
            continue
        if line.lower().startswith(("aquí", "estos", "ejemplos", "nota:", "observación")):
            continue
        out.append(line)
        if len(out) >= _MAX_EXAMPLES_PER_AGENT:
            break
    return out


def generate_examples_for_agent(agent_id: str, conversations: list[dict]) -> list[str]:
    """Genera 5-7 ejemplos para un agente analizando sus conversaciones."""
    if not conversations:
        return []

    # Construir contexto de las queries reales del usuario
    queries = []
    for c in conversations:
        q = (c.get("user") or "").strip()
        if 15 <= len(q) <= 250:
            queries.append(q[:200])
    if not queries:
        return []

    sample = "\n".join(f"- {q}" for q in queries[:40])
    prompt = (
        f"Analizá estas consultas reales hechas al agente '{agent_id}' "
        "y generá 5-7 ejemplos representativos de preguntas que un usuario "
        "típico podría hacer.\n\n"
        f"CONSULTAS REALES OBSERVADAS:\n{sample}\n\n"
        "INSTRUCCIONES:\n"
        "- Devolvé UNA pregunta por línea, sin numeración, sin viñetas, sin comillas.\n"
        "- Cada pregunta debe ser entre 30 y 180 caracteres.\n"
        "- Reformulá las consultas para que queden claras y profesionales (no copies literal).\n"
        "- Variá los tipos de pregunta (búsqueda, comparación, asesoramiento, generación).\n"
        "- En español rioplatense, formal pero accesible.\n"
        "- NO incluyas explicaciones, encabezados ni texto adicional.\n"
        "- Devolvé SOLO las preguntas, una por línea."
    )

    raw = _generate_with_gemini(prompt)
    examples = _parse_examples_from_response(raw)
    if examples:
        logger.info(
            "examples_generated | agent={} count={} from_convs={}",
            agent_id, len(examples), len(queries),
        )
    return examples


def generate_all_examples() -> dict[str, list[str]]:
    """Genera ejemplos para todos los agentes con conversaciones suficientes.

    Persiste en memory.json y devuelve el dict.
    """
    grouped = _conversations_by_agent()
    cached_now = _cached_examples()
    out: dict[str, list[str]] = dict(cached_now)  # arrancar con lo que ya hay

    for agent_id, convs in grouped.items():
        if len(convs) < 5:
            # Poco material — preservar lo cacheado si existe, sino skip
            continue
        new_examples = generate_examples_for_agent(agent_id, convs)
        if new_examples:
            out[agent_id] = new_examples

    if out != cached_now:
        raw = _load_memory_raw()
        raw["examples_by_agent"] = out
        raw["examples_generated_at"] = datetime.now(timezone.utc).isoformat()
        _save_memory_raw(raw)
    return out


# ── Lectura: ejemplos del día para un agente ─────────────────────────


def _today_seed() -> int:
    """Seed determinística por día (UTC). Misma respuesta todos los users."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h = hashlib.sha256(today.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _get_seed_examples(agent_id: str) -> list[str]:
    """Lee los seed_examples del AgentDefinition (no del JSON guardado, así
    si actualizamos el código y el cliente todavía no migra el JSON,
    igual ve los seeds nuevos)."""
    try:
        from app.agents.registry import _INITIAL_AGENTS, get_agent

        # 1. Buscar en el JSON persistido
        agent = get_agent(agent_id)
        if agent and agent.seed_examples:
            return list(agent.seed_examples)
        # 2. Fallback al hardcoded en _INITIAL_AGENTS por si el JSON no tiene
        for a in _INITIAL_AGENTS:
            if a.id == agent_id and a.seed_examples:
                return list(a.seed_examples)
    except Exception as e:
        logger.warning("get_seed_examples_failed | agent={} err={}", agent_id, e)
    return []


def get_examples_for_today(agent_id: str, count: int = 3) -> list[str]:
    """Devuelve `count` ejemplos para mostrar al usuario hoy.

    Combina seed_examples (estáticos del AgentDefinition) + cached
    (generados por LLM). Si hay más que `count`, rota con seed = fecha
    UTC. Si no hay material suficiente, devuelve los que haya (puede ser
    menos de `count`).
    """
    seeds = _get_seed_examples(agent_id)
    cached = _cached_examples().get(agent_id, [])

    # Pool combinado, sin duplicados (preservando orden)
    pool: list[str] = []
    seen: set[str] = set()
    for e in seeds + cached:
        key = e.strip().lower()
        if key and key not in seen:
            seen.add(key)
            pool.append(e.strip())

    if not pool:
        return []
    if len(pool) <= count:
        return pool

    # Rotación determinística por día
    rng = random.Random(_today_seed() ^ hash(agent_id))
    return rng.sample(pool, count)
