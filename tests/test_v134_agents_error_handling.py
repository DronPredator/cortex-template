"""Tests del fix de v1.3.4 — error handling visible al cargar agentes.

Antes: si `/api/agents` fallaba (401 por token expirado, 500 por server roto,
etc.), el catch del frontend era silencioso y la app quedaba sin selector
de agentes y sin razón visible. Ahora:
  - 401 → auto-logout (force re-login).
  - Otros errores → toast visible con el mensaje real.
"""

from __future__ import annotations


def test_agents_useeffect_handles_401_with_logout():
    """El useEffect que carga agentes debe llamar onLogout() si recibe 401."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # El effect tiene el comentario "Carga de agentes disponibles"
    idx = html.find("Carga de agentes disponibles")
    assert idx > 0, "No se encontró el effect de carga de agentes"
    chunk = html[idx:idx + 2500]
    # El nuevo handling tiene que tener 401 → onLogout
    assert "r.status === 401" in chunk, (
        "El effect no maneja explícitamente el caso 401"
    )
    assert "onLogout()" in chunk, "El effect no llama onLogout() en caso 401"


def test_agents_useeffect_shows_toast_on_other_errors():
    """En errores que no son 401, debe mostrar toast con mensaje visible."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    idx = html.find("Carga de agentes disponibles")
    assert idx > 0
    chunk = html[idx:idx + 2500]
    # Debe lanzar Error con detalle del HTTP status
    assert "throw new Error" in chunk, (
        "El effect no lanza Error cuando el HTTP status no es ok"
    )
    # Y el catch debe llamar setToast con info útil
    assert "setToast" in chunk, "El catch no muestra toast"
    assert "No se pudieron cargar los asistentes" in chunk, (
        "El mensaje del toast no es claro para el usuario"
    )


def test_agents_useeffect_has_abort_guard():
    """El effect debe tener cleanup que cancele el fetch si el componente
    se desmonta (evita setState en componente unmounted)."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    idx = html.find("Carga de agentes disponibles")
    chunk = html[idx:idx + 2500]
    # Patrón típico: `let aborted = false;` + cleanup que setea aborted = true
    assert "aborted" in chunk, (
        "El effect no tiene guard de aborto — puede setState tras unmount"
    )


def test_sw_cache_version_at_least_v134():
    """SW cache version >= v134 (cada release que toque static/ debe bumpear)."""
    from app.config import STATIC_DIR
    import re

    sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"const\s+CACHE_VERSION\s*=\s*['\"]cortex-v(\d+)['\"]", sw)
    assert m, "No se encontró CACHE_VERSION con formato cortex-vNNN"
    version = int(m.group(1))
    assert version >= 134, (
        f"CACHE_VERSION cortex-v{version} es muy vieja, "
        "debe ser >= cortex-v134"
    )
