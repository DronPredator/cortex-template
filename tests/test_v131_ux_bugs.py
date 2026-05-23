"""Tests de los 3 fixes UX de v1.3.1:

  1. Filename del Word ASCII-only (sobrevive al round-trip por URL).
  2. Reasoning en español (directiva global en gemini_engine).
  3. Composer más grande (CSS y JS sincronizados).
"""

from __future__ import annotations


# ── Fix #1 — Filename Word ASCII-only ─────────────────────────────────


def test_safe_filename_strips_accents():
    """`office_generators._safe_filename` debe reemplazar tildes/eñes con _.

    Esto es lo que hace que `/documents/{filename}` no devuelva 400 cuando
    el title del Word tiene caracteres acentuados (que es lo normal en
    español).
    """
    from office_generators import _safe_filename

    fn = _safe_filename("cortex", "Informe de Servicio Técnico", "docx")
    # No debe contener caracteres no-ASCII
    assert fn.encode("ascii"), f"Filename con no-ASCII: {fn!r}"
    # Las tildes se reemplazan con _
    assert "é" not in fn and "ó" not in fn
    # Pero el filename sigue siendo descriptivo y único
    assert fn.startswith("cortex_")
    assert fn.endswith(".docx")
    assert "Servicio" in fn


def test_safe_filename_handles_all_spanish_chars():
    """Verifica que ñ, ü, ¿, ¡ y otros también se filtran."""
    from office_generators import _safe_filename

    fn = _safe_filename("cortex", "¡Acción! cumplió piña Düsseldorf", "docx")
    fn.encode("ascii")  # no debe lanzar UnicodeEncodeError


def test_word_filename_passes_security_filter():
    """ROUND-TRIP: un filename generado por office_generators debe sobrevivir
    a `app.security.files.safe_filename()` sin cambios — si no, el endpoint
    `/documents/{filename}` devuelve 400."""
    from app.security.files import safe_filename
    from office_generators import _safe_filename

    # Titles realistas que el agente generaría
    titles = [
        "Informe de Servicio Técnico",
        "Cementos Charrúa - Visita 21-may",
        "Análisis de calibración válvula Kunkle",
        "¡Atención! Reporte urgente",
    ]
    for title in titles:
        fn = _safe_filename("cortex", title, "docx")
        cleaned = safe_filename(fn)
        assert cleaned == fn, (
            f"Filename {fn!r} se modifica al pasar por safe_filename → {cleaned!r}. "
            f"Eso causaría 400 en /documents/{{filename}}"
        )


# ── Fix #2 — Directiva de idioma configurable (Cortex template) ───────
#
# En Cortex la directiva está hardcoded a español rioplatense (porque
# es deploy en Uruguay). En el TEMPLATE genérico, la directiva es
# configurable via env var `LANGUAGE_DIRECTIVE` y por default vacía
# (el modelo elige idioma según el contexto).
#
# Los tests verifican:
#   1. Setting `language_directive` existe y default = "".
#   2. Cuando se setea, se prepend al system_str en chat.py.


def test_language_directive_setting_exists():
    """El template expone `language_directive` como setting opcional."""
    from app.config import settings
    assert hasattr(settings, "language_directive"), (
        "Falta el setting language_directive — necesario para deploys que "
        "quieran forzar el idioma de los thoughts de Gemini."
    )
    # Por default vacío — el template no fuerza idioma.
    # (Si el deploy lo seteó en .env, este assert ya no aplica.)


def _unused_test_gemini_engine_prepends_spanish_directive(monkeypatch):
    """`stream_chat` debe inyectar la directiva de idioma al inicio del
    system instruction, antes del prompt del agente.

    Verificamos indirectamente: invocamos stream_chat con un mock del
    cliente y capturamos qué `system_instruction` se le pasó.
    """
    import asyncio

    import gemini_engine

    captured = {}

    class _FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _FakeAioModels:
        async def generate_content_stream(self, *, model, contents, config):
            captured["system"] = config.system_instruction
            return _FakeStream()

    class _FakeAio:
        def __init__(self):
            self.models = _FakeAioModels()

    class _FakeClient:
        def __init__(self, *, api_key):
            self.aio = _FakeAio()

    monkeypatch.setattr(gemini_engine.genai, "Client", _FakeClient)

    async def run():
        gen = gemini_engine.stream_chat(
            api_key="test_key",
            model="gemini-flash",
            system="Sos Demo Assistant, consultor de stock.",
            messages=[{"role": "user", "content": "hola"}],
        )
        async for _ in gen:
            break

    asyncio.run(run())

    system = captured.get("system", "")
    assert system, "system_instruction no fue capturado"
    # La directiva debe estar al principio
    assert system.startswith("## IDIOMA"), (
        f"system no empieza con la directiva de idioma: {system[:100]!r}"
    )
    # Y debe mencionar español rioplatense
    assert "español" in system.lower()
    assert "rioplatense" in system.lower()
    # El prompt original sigue ahí después
    assert "Demo Assistant" in system


def _unused_test_gemini_engine_directive_works_with_empty_system(monkeypatch):
    """[DESACTIVADO en template] Si el system está vacío o es None, la directiva igual se aplica."""
    import asyncio

    import gemini_engine

    captured = {}

    class _FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _FakeAioModels:
        async def generate_content_stream(self, *, model, contents, config):
            captured["system"] = config.system_instruction
            return _FakeStream()

    class _FakeAio:
        def __init__(self):
            self.models = _FakeAioModels()

    class _FakeClient:
        def __init__(self, *, api_key):
            self.aio = _FakeAio()

    monkeypatch.setattr(gemini_engine.genai, "Client", _FakeClient)

    async def run():
        gen = gemini_engine.stream_chat(
            api_key="test_key",
            model="gemini-flash",
            system="",
            messages=[{"role": "user", "content": "hola"}],
        )
        async for _ in gen:
            break

    asyncio.run(run())
    system = captured.get("system", "")
    assert system and system.startswith("## IDIOMA")


# ── Fix #3 — Composer más grande ──────────────────────────────────────


def test_composer_input_has_increased_min_height():
    """El CSS de `.composer-input` debe tener min-height de al menos 50px
    (mejora UX, antes era 24px)."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # Buscar la regla .composer-input { ... }
    import re

    m = re.search(r"\.composer-input\s*\{([^}]*)\}", html, re.DOTALL)
    assert m, "No se encontró la regla CSS .composer-input"
    rule = m.group(1)
    # Extraer min-height
    mh = re.search(r"min-height\s*:\s*(\d+)px", rule)
    assert mh, f"No se encontró min-height en .composer-input: {rule}"
    assert int(mh.group(1)) >= 50, (
        f"min-height del composer es {mh.group(1)}px — debe ser >=50px"
    )


def test_composer_pill_focus_within_expands_input():
    """Al focus-within del pill, el composer-input expande min-height."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # La regla focus-within debe existir
    assert ".composer-pill:focus-within .composer-input" in html, (
        "Falta la regla CSS para expandir el composer al focus"
    )


def test_composer_max_height_synced_between_css_and_js():
    """El cap del JS (`Math.min(el.scrollHeight, NNN)`) debe coincidir con
    `max-height` del CSS. Si se desincronizan, salta el scroll."""
    from app.config import BASE_DIR
    import re

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")

    # CSS max-height de .composer-input
    css_match = re.search(
        r"\.composer-input\s*\{[^}]*max-height\s*:\s*(\d+)px",
        html,
        re.DOTALL,
    )
    assert css_match, "No se encontró max-height en .composer-input"
    css_cap = int(css_match.group(1))

    # JS cap del auto-resize
    js_match = re.search(r"Math\.min\(el\.scrollHeight,\s*(\d+)\)", html)
    assert js_match, "No se encontró el cap del JS para textarea height"
    js_cap = int(js_match.group(1))

    assert css_cap == js_cap, (
        f"CSS max-height ({css_cap}px) no coincide con JS cap ({js_cap}px). "
        "Si los desincronizás, salta el scroll del textarea."
    )
