"""Control de acceso a agentes.

Reglas:
- Admin ve y usa TODOS los agentes (sin restricción).
- Usuario regular: solo los `public` + los `users` en cuya lista esté incluido.
- `private` = solo admin.
"""

from __future__ import annotations

from app.agents.base import AgentDefinition


def can_user_access(username: str, is_admin: bool, agent: AgentDefinition) -> bool:
    """¿El usuario tiene permiso para usar este agente?"""
    if is_admin:
        return True
    if agent.visibility == "public":
        return True
    if agent.visibility == "users":
        return username in agent.allowed_users
    # private (o cualquier valor desconocido)
    return False


def filter_visible_agents(
    agents: list[AgentDefinition], username: str, is_admin: bool
) -> list[AgentDefinition]:
    """Filtra la lista de agentes a los que un usuario puede ver/usar."""
    return [a for a in agents if can_user_access(username, is_admin, a)]
