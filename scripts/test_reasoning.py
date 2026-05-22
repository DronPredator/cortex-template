"""Test rápido: ¿Gemini emite thoughts con include_thoughts=True?

Útil para diagnosticar por qué el panel de razonamiento no aparece en
algunos agentes. Prueba contra el modelo activo del settings.

Uso:
    python scripts/test_reasoning.py [modelo]

Sin args: usa MODEL_TIER_FLASH (gemini-3.5-flash).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings, MODEL_TIER_FLASH, MODEL_TIER_PRO, MODEL_TIER_LITE

from google import genai
from google.genai import types


async def run(model: str):
    if not settings.google_api_key:
        print("[X] No GOOGLE_API_KEY en .env")
        return
    print(f"=> Probando modelo: {model}")
    client = genai.Client(api_key=settings.google_api_key)

    # Probamos los 3 escenarios que usa el engine
    configs = {
        "include_thoughts=True (sin budget)": types.ThinkingConfig(include_thoughts=True),
        "include_thoughts=True + budget=4096": types.ThinkingConfig(include_thoughts=True, thinking_budget=4096),
        "include_thoughts=True + thinking_level=high": types.ThinkingConfig(include_thoughts=True, thinking_level="high"),
    }

    prompt = "¿Cuántos litros de vapor saturado a 5 bar produce 1 kg de agua a 20°C? Razoná paso a paso."

    for label, tcfg in configs.items():
        print(f"\n--- {label} ---")
        try:
            cfg = types.GenerateContentConfig(thinking_config=tcfg, max_output_tokens=2048)
            stream = await client.aio.models.generate_content_stream(
                model=model,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=cfg,
            )
            thoughts_seen = 0
            texts_seen = 0
            async for chunk in stream:
                cands = getattr(chunk, "candidates", None) or []
                if not cands:
                    continue
                content = getattr(cands[0], "content", None)
                if not content:
                    continue
                for part in (content.parts or []):
                    is_thought = bool(getattr(part, "thought", False))
                    txt = getattr(part, "text", None) or ""
                    if is_thought and txt:
                        thoughts_seen += 1
                        if thoughts_seen <= 2:
                            print(f"   [THOUGHT #{thoughts_seen}] {txt[:120]}{'…' if len(txt) > 120 else ''}")
                    elif txt:
                        texts_seen += 1
            print(f"   total: thoughts={thoughts_seen}, text_chunks={texts_seen}")
        except Exception as e:
            print(f"   ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else MODEL_TIER_FLASH
    asyncio.run(run(model))
