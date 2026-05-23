"""Tests de los 3 bugs cerrados en v1.3.3:

  1. ctx_max acepta texto extraído de Excels grandes (>30K chars).
  2. Editor de prompts del admin panel es más grande (rows >= 36, minHeight).
  3. Agente `generador_informes` no apunta a un PNG inexistente.
"""

from __future__ import annotations


# ── Fix #1 — ctx_max grande ──────────────────────────────────────────


def test_ctx_max_is_large_enough_for_extracted_documents():
    """ctx_max debe ser >= MAX_CHARS de document_extract con margen.

    El extractor trunca a 60K chars. Si ctx_max < 60K, Pydantic devuelve
    422 cuando el user adjunta un Excel grande → 'Validación de datos falló'.
    """
    from app.config import settings
    from document_extract import MAX_CHARS

    assert settings.ctx_max >= MAX_CHARS, (
        f"ctx_max ({settings.ctx_max}) < MAX_CHARS ({MAX_CHARS}) — "
        "adjuntar un documento grande va a fallar con 422"
    )
    # Margen razonable: al menos 60K extra para múltiples archivos + texto del user
    assert settings.ctx_max >= MAX_CHARS + 50_000, (
        f"ctx_max ({settings.ctx_max}) no deja margen para múltiples "
        f"adjuntos + texto del user (debe ser >= {MAX_CHARS + 50_000})"
    )


def test_chat_request_accepts_large_system_context():
    """ChatRequest.system_context permite textos del tamaño de un Excel
    grande extraído (~60K chars)."""
    from app.models import ChatRequest

    # 60K chars de prueba — un Excel realista extraído
    big_context = "X" * 60_000
    req = ChatRequest(
        messages=[{"role": "user", "content": "test"}],
        system_context=big_context,
    )
    assert len(req.system_context) == 60_000


def test_chat_request_accepts_multiple_adjuntos_size():
    """system_context con texto de 2 documentos grandes (~110K) debe pasar."""
    from app.models import ChatRequest

    big_context = "Y" * 110_000
    req = ChatRequest(
        messages=[{"role": "user", "content": "test"}],
        system_context=big_context,
    )
    assert len(req.system_context) == 110_000


# ── Fix #2 — Editor de prompts más grande ─────────────────────────────


def test_admin_prompt_editor_has_more_rows():
    """El textarea de edición de prompts en el admin panel debe tener
    rows >= 36 (antes era 26 que era muy chico)."""
    from app.config import BASE_DIR
    import re

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # Buscar la línea `rows={26}` que era el viejo valor
    m_old = re.search(r"rows=\{26\}", html)
    assert not m_old, "Todavía queda rows={26} — debería ser >= 36"
    # Y debe haber al menos un rows={36+} en alguna parte
    rows_values = re.findall(r"rows=\{(\d+)\}", html)
    assert any(int(v) >= 36 for v in rows_values), (
        f"Ningún textarea tiene rows>=36. Valores encontrados: {rows_values}"
    )


def test_admin_prompt_editor_uses_viewport_height():
    """El editor de prompts usa minHeight basado en viewport (vh) para
    ser proporcional al tamaño de la pantalla."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # Buscar el textarea cuyo value es {promptDraft}. Tiene que tener
    # minHeight con vh en su style inline.
    idx = html.find("value={promptDraft}")
    assert idx > 0, "No se encontró el textarea del prompt editor"
    # Tomar un chunk amplio que cubra toda la prop style del textarea
    chunk = html[idx:idx + 1500]
    assert "minHeight" in chunk, (
        "Falta minHeight en el style del textarea de prompts"
    )
    # Que use vh (relativo al viewport, no px fijo)
    assert "vh" in chunk, "minHeight no usa vh (proporcional al viewport)"


# ── Fix #3 — Agente generador_informes sin icon_url roto ──────────────


def _unused_test_generador_informes_no_broken_icon_url():
    """[DESACTIVADO en template] Test específico de un agente de Cortex
    que no existe en el template. El cubrimiento equivalente lo da
    `test_all_agent_icon_urls_point_to_existing_files` (que recorre
    todos los agentes del registry, no uno específico)."""
    return


def test_all_agent_icon_urls_point_to_existing_files():
    """Cualquier agente que declare icon_url debe tener el archivo en disco."""
    from app.agents.registry import _INITIAL_AGENTS
    from app.config import STATIC_DIR

    broken = []
    for agent in _INITIAL_AGENTS:
        if not agent.icon_url:
            continue
        icon_path = STATIC_DIR / agent.icon_url.lstrip("/")
        if not icon_path.exists():
            broken.append(f"{agent.id} → {agent.icon_url}")
    assert not broken, f"Agentes con icon_url roto: {broken}"


# ── Service worker bumpeado ───────────────────────────────────────────


def test_sw_cache_version_bumped_post_v133():
    """CACHE_VERSION debe estar al menos en cortex-v133 (puede ser >).

    Cada release que toque static/ debe bumpear esto para invalidar el
    HTML cacheado por los clientes existentes.
    """
    from app.config import STATIC_DIR
    import re

    sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"const\s+CACHE_VERSION\s*=\s*['\"]cortex-v(\d+)['\"]", sw)
    assert m, "No se encontró CACHE_VERSION con formato cortex-vNNN"
    version = int(m.group(1))
    assert version >= 133, (
        f"CACHE_VERSION cortex-v{version} es muy vieja, "
        "tiene que ser >= cortex-v133"
    )
