"""Auto-router de modelos Gemini según complejidad de la consulta.

Heurística simple sin llamada API:
- Documento adjunto → Pro
- Trigger words de análisis (compara, informe, datasheet, etc) → Pro
- Mensaje muy corto → Lite
- Default → Flash

## Routers específicos por agente

Si tu deploy tiene un agente con dominio particular y querés un router
distinto (ej. consultas generales → Flash, formularios certificados → Pro),
podés agregar tu propia función `classify_task_tier_<agent>` y registrarla
en `_AGENT_ROUTERS`. Ver ejemplo comentado al final.
"""

from __future__ import annotations

from app.config import MODEL_TIER_FLASH, MODEL_TIER_LITE, MODEL_TIER_PRO
from app.storage.runtime_config import get_current_model, load_runtime_config


_PRO_KEYWORDS = (
    "compar", "comparativa", "comparación", "comparacion",
    "informe", "reporte", "análisis", "analisis", "analiza",
    "ficha técnica", "ficha tecnica", "datasheet", "manual",
    "generá pdf", "generar pdf", "genera pdf",
    "generame un pdf", "generame el pdf",
    "ingeniería", "ingenieria", "selección", "seleccion",
    "explicame en detalle", "detallado", "exhaustivo",
    "elabora", "elaborame", "elaborá", "elaborar",
)


def classify_task_tier(last_user_message: str, has_documents: bool) -> str:
    """'pro' | 'flash' | 'lite' según heurísticas (router default)."""
    msg = (last_user_message or "").strip().lower()
    if has_documents:
        return "pro"
    if any(k in msg for k in _PRO_KEYWORDS):
        return "pro"
    if 0 < len(msg) < 40:
        return "lite"
    return "flash"


# Registry de routers por agente. La key es el agent.id; el valor es la
# función que clasifica. Si un agente no está acá, usa el router default.
#
# Ejemplo de uso para un agente de dominio específico:
#
#     def classify_task_tier_my_agent(msg: str, has_documents: bool) -> str:
#         m = (msg or "").strip().lower()
#         if has_documents:
#             return "pro"
#         if any(k in m for k in ("auditoría", "norma", "certificación")):
#             return "pro"
#         return "flash"
#
#     _AGENT_ROUTERS = {
#         "my_agent_id": classify_task_tier_my_agent,
#     }
_AGENT_ROUTERS: dict = {}


def tier_to_model(tier: str) -> str:
    return {
        "pro": MODEL_TIER_PRO,
        "flash": MODEL_TIER_FLASH,
        "lite": MODEL_TIER_LITE,
    }.get(tier, MODEL_TIER_FLASH)


def resolve_model_for_request(
    last_user_message: str,
    has_documents: bool,
    agent_id: str | None = None,
) -> tuple[str, str]:
    """Decide qué modelo usar. Respeta override manual del admin.

    Si `agent_id` está en _AGENT_ROUTERS, usa el router específico del
    agente. Si no, usa el router default.

    Returns: (model_id, source) donde source ∈
      {'manual', 'auto:pro', 'auto:flash', 'auto:lite',
       'auto:<agent_id>:pro', 'auto:<agent_id>:flash', ...}
    """
    cfg = load_runtime_config()
    if cfg.get("auto_route") is False:
        return get_current_model(), "manual"
    router = _AGENT_ROUTERS.get(agent_id) if agent_id else None
    if router is not None:
        tier = router(last_user_message, has_documents)
        return tier_to_model(tier), f"auto:{agent_id}:{tier}"
    tier = classify_task_tier(last_user_message, has_documents)
    return tier_to_model(tier), f"auto:{tier}"
