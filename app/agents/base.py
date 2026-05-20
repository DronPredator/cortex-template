"""Definición de un Agente (asistente especializado).

Cada agente tiene:
- Un system prompt propio (archivo .md en `definitions/`)
- Un set de tools que puede invocar (subconjunto de los disponibles)
- Un tier de modelo recomendado (`pro`/`flash`/`lite`/`auto`)
- Visibilidad (público / privado / lista de usuarios)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal


Visibility = Literal["public", "private", "users"]
DefaultTier = Literal["auto", "pro", "flash", "lite"]


@dataclass
class AgentDefinition:
    """Definición de un agente. Persiste como entrada en `agents.json`."""

    # Identidad
    id: str
    name: str
    description: str = ""
    icon: str = "🤖"

    # Prompt: el contenido vive en `app/agents/definitions/<id>.md`.
    # Acá guardamos solo el id; el contenido se carga on-demand vía registry.
    prompt_file: str = ""  # default: "<id>.md"

    # Comportamiento
    allowed_tools: list[str] = field(default_factory=list)
    default_tier: DefaultTier = "auto"

    # Permisos
    visibility: Visibility = "public"
    allowed_users: list[str] = field(default_factory=list)  # solo si visibility="users"

    # Metadata
    is_default: bool = False  # cuál se usa si el cliente no manda agent_id
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentDefinition":
        # Filtra keys desconocidas para forward-compatibility
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        clean = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**clean)

    def prompt_filename(self) -> str:
        return self.prompt_file or f"{self.id}.md"
