"""Tests del feature v1.5.0 — thoughts persistidos junto al message.

Antes: el panel "Pensando…" aparecía solo durante la generación y se
descartaba al terminar. Ahora los thoughts se guardan junto con el message
(localStorage + state) y se pueden inspeccionar a posteriori en un bloque
colapsible debajo de la respuesta.

Como es un feature 100% frontend, los tests son de verificación de
presencia del componente, lógica de persistencia y CSS.
"""

from __future__ import annotations


# ── streamFromMessages persiste reasoning con el message ──────────────


def test_streamfrommessages_saves_reasoning_in_message():
    """En el handler de evt.type==='done', el message final debe incluir
    el campo `reasoning` con el contenido acumulado del reasoningBuf."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # En el bloque del 'done' debe construirse el message con `reasoning`
    assert "reasoning: savedReasoning" in html, (
        "El message final no incluye el campo `reasoning` para persistencia"
    )
    # Y debe haber cap a 30K caracteres
    assert "REASONING_CAP" in html
    assert "30_000" in html or "30000" in html


def test_reasoning_cap_truncates_long_thoughts():
    """El cap de 30K previene que sesiones largas inflen el localStorage."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # Debe aplicar el cap al guardar (no al mostrar)
    assert "savedReasoning.length > REASONING_CAP" in html


# ── Componente ThoughtsViewer existe y está montado ───────────────────


def test_thoughts_viewer_component_exists():
    """El componente ThoughtsViewer está definido en el HTML."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert "function ThoughtsViewer(" in html, (
        "Falta el componente ThoughtsViewer"
    )


def _extract_thoughts_viewer_body():
    """Devuelve solo el cuerpo del componente ThoughtsViewer.

    Buscamos desde `function ThoughtsViewer(` hasta el siguiente top-level
    `function ` que sigue después (delimitador del próximo componente)."""
    from app.config import BASE_DIR
    import re

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    start = html.find("function ThoughtsViewer(")
    assert start > 0, "No se encontró el componente ThoughtsViewer"
    # Buscar el próximo `function NAME(` (otro componente top-level) o
    # un comentario /* ── que delimita la próxima sección.
    rest = html[start + len("function ThoughtsViewer("):]
    next_fn = re.search(r"\n(function |/\* ── )", rest)
    end = start + len("function ThoughtsViewer(") + (next_fn.start() if next_fn else len(rest))
    return html[start:end]


def test_thoughts_viewer_uses_native_details():
    """Usa `<details>` HTML nativo (no React state) — el browser persiste
    el open/closed por instancia automáticamente."""
    chunk = _extract_thoughts_viewer_body()
    assert "<details" in chunk, "ThoughtsViewer no usa <details> nativo"
    # NO debe tener useState (es estado del browser)
    assert "useState" not in chunk, (
        "ThoughtsViewer no debe usar React useState — el <details> guarda "
        "el estado solo"
    )


def test_thoughts_viewer_closed_by_default():
    """El <details> NO debe tener attr `open` — empieza cerrado para no
    robar atención al lector no técnico."""
    import re

    chunk = _extract_thoughts_viewer_body()
    m = re.search(r"<details[^>]*?>", chunk)
    assert m, "No se encontró el <details> en ThoughtsViewer"
    open_tag = m.group(0)
    assert " open" not in open_tag, (
        f"ThoughtsViewer abre por default — debería empezar cerrado. Tag: {open_tag}"
    )


def test_thoughts_viewer_mounted_in_assistant_render():
    """El componente está montado en el render del assistant message,
    DESPUÉS del AssistantMd y ANTES del aviso de truncated."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert "<ThoughtsViewer" in html, (
        "ThoughtsViewer no está montado en el render del message"
    )
    # Debe usar el campo m.reasoning como prop
    assert "reasoning={m.reasoning}" in html


def test_thoughts_viewer_skipped_during_streaming():
    """Mientras el message se está streameando, NO debe aparecer el bloque
    (el reasoning todavía vive en el ReasoningPanel ephemeral arriba)."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # Verificar el guard: {m.reasoning && !isStreaming && ...}
    assert "m.reasoning && !isStreaming" in html, (
        "ThoughtsViewer no tiene guard !isStreaming"
    )


# ── CSS sutil presente ────────────────────────────────────────────────


def test_thoughts_viewer_has_styling():
    """El CSS de .thoughts-viewer está definido para que no se vea sin
    estilos."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    css_keys = [
        ".thoughts-viewer",
        ".thoughts-viewer-summary",
        ".thoughts-viewer-body",
    ]
    for k in css_keys:
        assert k in html, f"Falta el selector CSS {k}"


# ── SW cache bumped ───────────────────────────────────────────────────


def test_sw_cache_version_at_least_v150():
    """SW bumpeado a v150 para invalidar HTML viejo."""
    from app.config import STATIC_DIR
    import re

    sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"const\s+CACHE_VERSION\s*=\s*['\"]cortex-v(\d+)['\"]", sw)
    assert m
    assert int(m.group(1)) >= 150, (
        f"CACHE_VERSION cortex-v{m.group(1)} es muy vieja, esperado >= 150"
    )
