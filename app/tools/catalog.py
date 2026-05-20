"""Formato de resultados del catálogo para que el LLM los lea."""

from __future__ import annotations


def format_catalog_result(query: str, data: dict) -> str:
    """Convierte el dict de `search_stock()` a texto markdown para el modelo."""
    items = data["items"]
    total = data["total"]
    offset = data.get("offset", 0)

    if not items:
        if offset > 0:
            return f"No hay más resultados a partir del offset {offset}."
        return f"No se encontraron ítems para '{query}'. Probá con otros términos."

    shown = len(items)
    lines = [f"- {r['codigo']} | {r['descripcion']}" for r in items]

    if data["truncated"]:
        next_offset = offset + shown
        header = (
            f"Resultados para '{query}': {total} ítems coincidentes en el catálogo. "
            f"Mostrando ítems {offset + 1}–{offset + shown} (ranqueados por relevancia). "
            f"Para ver los siguientes, llamá de nuevo con offset={next_offset}.\n"
        )
    elif offset > 0:
        header = (
            f"Resultados para '{query}' (página final): {total} totales, "
            f"mostrando ítems {offset + 1}–{offset + shown}.\n"
        )
    else:
        header = f"Resultados para '{query}': {total} ítem(s) coincidente(s):\n"
    return header + "\n".join(lines)
