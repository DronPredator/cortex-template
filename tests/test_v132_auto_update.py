"""Tests del sistema de auto-update v1.3.2:
  - UpdateBanner component existe en el frontend.
  - SW excluye /reset-cache de su intercepción.
  - /reset-cache.html existe y tiene el script de limpieza.
  - SW CACHE_VERSION se bumpea.
"""

from __future__ import annotations


# ── UpdateBanner ──────────────────────────────────────────────────────


def test_update_banner_component_exists():
    """El componente React `UpdateBanner` debe estar definido en el frontend."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert "function UpdateBanner(" in html, (
        "Falta la definición del componente UpdateBanner"
    )


def test_update_banner_polls_version_endpoint():
    """El polling debe ir a /api/version (público, no requiere auth)."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # Busca la lógica de polling en UpdateBanner
    # Tiene que hacer fetch('/api/version', ...) dentro del componente
    banner_start = html.find("function UpdateBanner(")
    # Próximo componente top-level (sé que ThinkingIndicator viene después).
    banner_end = html.find("function ThinkingIndicator(", banner_start)
    if banner_end == -1:
        banner_end = banner_start + 4000  # fallback: ~4 KB de contexto
    banner_code = html[banner_start:banner_end]
    assert "/api/version" in banner_code, (
        "UpdateBanner debe polling /api/version (endpoint público)"
    )
    assert "setInterval" in banner_code, "UpdateBanner debe usar setInterval"


def test_update_banner_rendered_in_app():
    """El componente debe estar montado en <App />, no solo definido."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert "<UpdateBanner />" in html, (
        "UpdateBanner no está montado en App — el banner nunca va a aparecer"
    )


def test_update_banner_unregisters_sw_on_reload():
    """Al recargar, el banner debe desregistrar SWs y limpiar caches."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    banner_start = html.find("function UpdateBanner(")
    # Próximo componente top-level (sé que ThinkingIndicator viene después).
    banner_end = html.find("function ThinkingIndicator(", banner_start)
    if banner_end == -1:
        banner_end = banner_start + 4000  # fallback: ~4 KB de contexto
    banner_code = html[banner_start:banner_end]
    assert "unregister" in banner_code, "UpdateBanner debe unregister SWs"
    assert "caches.delete" in banner_code or "caches.keys" in banner_code, (
        "UpdateBanner debe limpiar caches"
    )
    assert "location.reload" in banner_code, "UpdateBanner debe hacer reload"


# ── Página /reset-cache.html ──────────────────────────────────────────


def test_reset_cache_page_exists():
    """Página de reset manual existe."""
    from app.config import STATIC_DIR

    p = STATIC_DIR / "reset-cache.html"
    assert p.exists(), f"Falta {p}"


def test_reset_cache_page_has_clean_script():
    """La página debe ejecutar limpieza al cargar (sin requerir click)."""
    from app.config import STATIC_DIR

    html = (STATIC_DIR / "reset-cache.html").read_text(encoding="utf-8")
    # Debe llamar a unregister y caches.delete
    assert "unregister" in html
    assert "caches.delete" in html or "caches.keys" in html
    # Y redirigir a la raíz al terminar
    assert "location.replace" in html or "location.href" in html


def test_reset_cache_page_servible(client):
    """La página debe ser servida por StaticFiles (sin auth)."""
    r = client.get("/reset-cache.html")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Reseteando Cortex" in r.text


# ── Service Worker ────────────────────────────────────────────────────


def test_sw_excludes_reset_cache_path():
    """El SW NO debe interceptar /reset-cache.html, sino el script de
    limpieza nunca corre (el SW devuelve cache viejo)."""
    from app.config import STATIC_DIR

    sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    assert "/reset-cache.html" in sw or "/reset-cache" in sw
    # Debe estar en una condición que hace `return` (early exit)
    # → no que la cachee
    assert "reset-cache" in sw
    # Heurística: la línea de reset-cache debe estar cerca de un `return`
    idx = sw.find("reset-cache")
    near = sw[idx:idx + 100]
    assert "return" in near, (
        f"El SW menciona reset-cache pero no parece hacer early-return: {near}"
    )


def test_sw_cache_version_bumped():
    """CACHE_VERSION debe haber sido bumpeada (no quedó en v1)."""
    from app.config import STATIC_DIR
    import re

    sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"const\s+CACHE_VERSION\s*=\s*['\"]([^'\"]+)['\"]", sw)
    assert m, "No se encontró CACHE_VERSION en sw.js"
    version = m.group(1)
    # Algo más nuevo que cortex-v1 (cortex-v131, cortex-v132, etc.)
    assert version != "cortex-v1", (
        f"CACHE_VERSION sigue en 'cortex-v1' — hay que bumpearla "
        f"en cada release que cambie static/"
    )
