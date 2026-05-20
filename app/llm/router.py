"""Auto-router de modelos Gemini según complejidad de la consulta.

Heurística simple sin llamada API:
- Documento adjunto → Pro
- Trigger words de análisis (compara, informe, datasheet, etc) → Pro
- Mensaje muy corto → Lite
- Default → Flash
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
    """'pro' | 'flash' | 'lite' según heurísticas."""
    msg = (last_user_message or "").strip().lower()
    if has_documents:
        return "pro"
    if any(k in msg for k in _PRO_KEYWORDS):
        return "pro"
    if 0 < len(msg) < 40:
        return "lite"
    return "flash"


def tier_to_model(tier: str) -> str:
    return {
        "pro": MODEL_TIER_PRO,
        "flash": MODEL_TIER_FLASH,
        "lite": MODEL_TIER_LITE,
    }.get(tier, MODEL_TIER_FLASH)


def resolve_model_for_request(
    last_user_message: str, has_documents: bool
) -> tuple[str, str]:
    """Decide qué modelo usar. Respeta override manual del admin.

    Returns: (model_id, source) donde source ∈ {'manual','auto:pro','auto:flash','auto:lite'}
    """
    cfg = load_runtime_config()
    if cfg.get("auto_route") is False:
        return get_current_model(), "manual"
    tier = classify_task_tier(last_user_message, has_documents)
    return tier_to_model(tier), f"auto:{tier}"
