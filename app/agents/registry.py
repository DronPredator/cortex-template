"""Registry de agentes — load, save, get, list, ensure.

Los agentes viven en dos lugares:
- `agents.json` (raíz del proyecto): metadata + permisos + tools permitidas
- `app/agents/definitions/<id>.md`: el system prompt de cada uno

Esta separación permite editar prompts en un editor decente (.md con syntax
highlighting) sin tener que pelearse con escape de JSON.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from loguru import logger

from app.agents.base import AgentDefinition
from app.config import AGENT_DEFINITIONS_DIR, AGENTS_PATH, DEFAULT_AGENT_ID
from app.storage.atomic import atomic_write


_lock = threading.Lock()
_prompt_cache: dict[str, tuple[float, str]] = {}  # id → (mtime, content)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Persistencia ─────────────────────────────────────────────────────


def load_agents() -> dict[str, AgentDefinition]:
    """Lee `agents.json` y devuelve {id: AgentDefinition}."""
    if not AGENTS_PATH.exists():
        return {}
    try:
        raw = json.loads(AGENTS_PATH.read_text(encoding="utf-8"))
        return {aid: AgentDefinition.from_dict({**a, "id": aid}) for aid, a in raw.items()}
    except Exception as e:
        logger.error("load_agents_failed | {}", e)
        return {}


def save_agents(agents: dict[str, AgentDefinition]) -> None:
    """Guarda atómicamente."""
    with _lock:
        data = {aid: a.to_dict() for aid, a in agents.items()}
        atomic_write(AGENTS_PATH, json.dumps(data, ensure_ascii=False, indent=2))


def get_agent(agent_id: str) -> AgentDefinition | None:
    """Devuelve el agente o None si no existe."""
    return load_agents().get(agent_id)


def get_agent_or_default(agent_id: str | None) -> AgentDefinition:
    """Resuelve el agente a usar. Si no se especifica o no existe, cae al default.

    Si tampoco hay default (caso inicialización rota), levanta error claro.
    """
    agents = load_agents()
    if agent_id and agent_id in agents:
        return agents[agent_id]
    if DEFAULT_AGENT_ID in agents:
        return agents[DEFAULT_AGENT_ID]
    # Fallback: cualquiera marcado como default
    for a in agents.values():
        if a.is_default:
            return a
    raise RuntimeError(
        "No hay agentes configurados. Llamá a ensure_agents_file() en startup."
    )


def list_agents() -> list[AgentDefinition]:
    """Lista todos los agentes ordenados por nombre."""
    return sorted(load_agents().values(), key=lambda a: a.name.lower())


def upsert_agent(agent: AgentDefinition) -> AgentDefinition:
    """Crea o actualiza un agente. Setea timestamps."""
    agents = load_agents()
    now = _now()
    if agent.id not in agents:
        agent.created_at = now
    agent.updated_at = now
    agents[agent.id] = agent
    save_agents(agents)
    logger.info("agent_upserted | id={} name={}", agent.id, agent.name)
    return agent


def delete_agent(agent_id: str) -> bool:
    """Elimina un agente. NO permite borrar el default."""
    agents = load_agents()
    if agent_id not in agents:
        return False
    if agents[agent_id].is_default:
        raise ValueError("No se puede eliminar el agente default")
    del agents[agent_id]
    save_agents(agents)
    # Invalidar cache de prompt
    _prompt_cache.pop(agent_id, None)
    logger.info("agent_deleted | id={}", agent_id)
    return True


# ── System prompts en disco (.md) ────────────────────────────────────


def load_agent_prompt(agent: AgentDefinition) -> str:
    """Carga el system prompt del agente desde su archivo .md.

    Cachea por mtime — si el archivo cambia, recarga sin reiniciar el server.
    """
    path = AGENT_DEFINITIONS_DIR / agent.prompt_filename()
    if not path.exists():
        logger.warning("agent_prompt_missing | id={} path={}", agent.id, path)
        return f"Sos el asistente '{agent.name}' de esta instancia de Cortex."
    mtime = path.stat().st_mtime
    cached = _prompt_cache.get(agent.id)
    if cached and cached[0] == mtime:
        return cached[1]
    content = path.read_text(encoding="utf-8")
    _prompt_cache[agent.id] = (mtime, content)
    return content


def save_agent_prompt(agent: AgentDefinition, content: str) -> None:
    """Guarda el system prompt del agente al disco. Invalida el cache."""
    path = AGENT_DEFINITIONS_DIR / agent.prompt_filename()
    AGENT_DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(path, content)
    _prompt_cache.pop(agent.id, None)
    logger.info("agent_prompt_saved | id={} bytes={}", agent.id, len(content))


# ── Inicialización ───────────────────────────────────────────────────


_INITIAL_AGENTS: list[AgentDefinition] = [
    # Agente de demostración del template. Reemplazar con los agentes
    # reales de la instancia (ver README del template).
    AgentDefinition(
        id="demo_assistant",
        name="Demo Assistant",
        description="Asistente de demostración. Reemplazá este agente con el flagship de tu instancia.",
        icon="🤖",
        allowed_tools=[
            "catalog_search",
            "verify_pdf_url",
            "tavily_search",
        ],
        default_tier="auto",
        visibility="public",
        is_default=True,
    ),
]


def ensure_agents_file() -> None:
    """En el primer arranque, crea `agents.json` con los agentes iniciales
    definidos en `_INITIAL_AGENTS`.

    Si el archivo ya existe, NO lo modifica — respeta lo que está. El admin
    es responsable de su configuración a partir de ese momento.
    """
    if AGENTS_PATH.exists():
        return
    agents = {}
    now = _now()
    for a in _INITIAL_AGENTS:
        a.created_at = now
        a.updated_at = now
        agents[a.id] = a
    save_agents(agents)
    logger.info("agents_file_initialized | count={}", len(agents))
