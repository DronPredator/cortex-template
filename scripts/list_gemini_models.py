"""Lista los modelos Gemini disponibles en tu cuenta Google.

Uso:
    python scripts/list_gemini_models.py

Lee la GOOGLE_API_KEY del .env del proyecto. Devuelve la lista oficial
de modelos disponibles HOY en la API, ordenados, con su context window
y los métodos soportados (generateContent, streaming, etc.).

Útil cuando Google saca un modelo nuevo y queremos saber si está
disponible para nuestra API key antes de cambiar la config.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cargar settings (lee .env)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings


def main():
    if not settings.google_api_key:
        print("[X] No hay GOOGLE_API_KEY en .env")
        sys.exit(1)

    try:
        from google import genai as _genai
    except ImportError:
        print("[X] Falta google-genai. Instalar con: pip install google-genai")
        sys.exit(1)

    client = _genai.Client(api_key=settings.google_api_key)

    print("Consultando modelos disponibles en tu cuenta Google...")
    print("=" * 80)

    try:
        models = list(client.models.list())
    except Exception as e:
        print(f"[X] Error al listar modelos: {e}")
        sys.exit(1)

    # Filtrar solo los Gemini que soportan generateContent (chat)
    gemini_chat_models = []
    for m in models:
        name = getattr(m, "name", "") or ""
        if not name.startswith("models/gemini"):
            continue
        actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", []) or []
        if not actions or "generateContent" in actions or "generate_content" in actions:
            gemini_chat_models.append(m)

    # Ordenar por nombre
    gemini_chat_models.sort(key=lambda m: getattr(m, "name", ""))

    print(f"\n{len(gemini_chat_models)} modelo(s) Gemini disponibles para chat:\n")
    for m in gemini_chat_models:
        name = (getattr(m, "name", "") or "").replace("models/", "")
        display = getattr(m, "display_name", "") or ""
        ctx_in = getattr(m, "input_token_limit", "?") or "?"
        ctx_out = getattr(m, "output_token_limit", "?") or "?"
        desc = (getattr(m, "description", "") or "").strip()
        if len(desc) > 120:
            desc = desc[:120] + "..."

        print(f"  {name}")
        if display and display != name:
            print(f"      Display: {display}")
        print(f"      Context: {ctx_in:,} in / {ctx_out:,} out tokens")
        if desc:
            print(f"      {desc}")
        print()

    print("=" * 80)
    print("\nPara usar uno de estos en Cortex:")
    print("  1. Editar app/config.py")
    print("  2. Cambiar MODEL_TIER_PRO / MODEL_TIER_FLASH / MODEL_TIER_LITE")
    print("  3. Actualizar AVAILABLE_GEMINI_MODELS con el nuevo entry")
    print("  4. nssm restart CortexChat  (o restart manual del server)")


if __name__ == "__main__":
    main()
