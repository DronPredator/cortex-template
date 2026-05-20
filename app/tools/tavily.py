"""Wrapper de Tavily Search API.

Tavily devuelve resultados con título, URL y un extracto de contenido.
Esta función los formatea como texto para que el LLM pueda leerlos directo.
"""

from __future__ import annotations

from loguru import logger

from app.config import settings


def format_tavily_results(query: str, response: dict) -> str:
    lines = [f'Resultados Tavily para: "{query}"']

    answer = response.get("answer", "")
    if answer:
        lines.append(f"\nResumen: {answer}")

    results = response.get("results", [])
    if not results:
        lines.append("\nNo se encontraron resultados.")
        return "\n".join(lines)

    lines.append(f"\n{len(results)} resultado(s):")
    for i, r in enumerate(results, 1):
        title = r.get("title", "Sin título")
        url = r.get("url", "")
        content = (r.get("content") or "")[:500]
        lines.append(f"\n{i}. {title}\n   URL: {url}\n   {content}")
    return "\n".join(lines)


def tavily_search(query: str, depth: str = "advanced", max_results: int = 6) -> dict:
    """Llama a Tavily. Returns dict con results/answer o error."""
    if not settings.tavily_api_key:
        return {"error": "TAVILY_API_KEY no configurada en el servidor", "results": []}
    if depth not in ("basic", "advanced"):
        depth = "advanced"
    try:
        from tavily import TavilyClient

        tc = TavilyClient(api_key=settings.tavily_api_key)
        resp = tc.search(
            query,
            search_depth=depth,
            max_results=max_results,
            include_answer=True,
        )
        return resp
    except Exception as e:
        logger.error("tavily_search_failed | query={} err={}", query, e)
        return {"error": str(e)[:200], "results": []}
