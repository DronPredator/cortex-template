"""Tests de v1.4.1 — sesión persistente + manejo de respuestas truncadas.

Cubre los 3 bugs reportados:
1. JWT expiraba a 8h (jornada laboral > 8h dejaba la app sin sesión).
2. Respuestas largas se cortaban por MAX_TOKENS sin aviso al usuario.
3. Panel admin se quedaba mudo silenciosamente cuando el token expiraba.

Fixes implementados:
- JWT default 8h → 24h.
- POST /api/auth/refresh para renovar tokens.
- max_output_tokens 4096 → 16384 (4x).
- Detección de finish_reason=MAX_TOKENS + evento SSE `truncated`.
- Frontend: refresh automático cada 6h + botón "Continuar generación".
"""

from __future__ import annotations


# ── Bug 1 — JWT 24h ────────────────────────────────────────────────────


def test_jwt_default_is_24_hours():
    """Default subido de 8h → 24h para cubrir jornadas largas."""
    from app.config import Settings

    s = Settings.model_fields["jwt_expire_hours"]
    assert s.default == 24, (
        f"jwt_expire_hours default es {s.default}, esperado 24"
    )


# ── Endpoint /api/auth/refresh ─────────────────────────────────────────


def test_refresh_requires_bearer(client):
    """Sin Authorization header → 401/403."""
    r = client.post("/api/auth/refresh")
    assert r.status_code in (401, 403)


def test_refresh_rejects_invalid_token(client):
    r = client.post(
        "/api/auth/refresh",
        headers={"Authorization": "Bearer not_a_real_jwt"},
    )
    assert r.status_code == 401


def test_refresh_returns_new_token_for_user(client, user_token):
    """Refresh con token válido devuelve uno nuevo, NO el mismo."""
    import time

    # El nuevo token DEBE diferir del original — el `exp` cambia (timestamp),
    # así la firma JWT es diferente aunque el resto del payload coincida.
    time.sleep(1)  # garantizar timestamp distinto en exp
    r = client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data
    assert data["token"] != user_token, (
        "El refresh devolvió el MISMO token — debe ser uno nuevo con exp fresco"
    )
    assert "username" in data


def test_refresh_preserves_admin_role(client, admin_token):
    """Refresh de admin token devuelve uno nuevo CON role=admin."""
    from jose import jwt
    from app.config import settings

    r = client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    new_tok = r.json()["token"]
    payload = jwt.decode(new_tok, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload.get("role") == "admin", "Refresh perdió el role admin"


def test_refresh_new_token_works_for_admin_endpoint(client, admin_token):
    """El token nuevo del refresh es válido para llamar a admin endpoints."""
    r = client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    new_tok = r.json()["token"]
    # Usar el token nuevo en un endpoint admin
    r2 = client.get(
        "/api/admin/agents",
        headers={"Authorization": f"Bearer {new_tok}"},
    )
    assert r2.status_code == 200


# ── Bug 2 — max_output_tokens ──────────────────────────────────────────


def test_max_output_tokens_is_at_least_16k():
    """gemini_engine.py debe usar al menos 16K para max_output_tokens.

    El default viejo (4096) cortaba respuestas largas a mitad de oración.
    Gemini Flash soporta hasta 65K — 16K nos da 4x más espacio sin
    desperdiciar.
    """
    from app.config import BASE_DIR
    import re

    src = (BASE_DIR / "gemini_engine.py").read_text(encoding="utf-8")
    m = re.search(r"max_output_tokens\s*=\s*(\d+)", src)
    assert m, "No se encontró max_output_tokens en gemini_engine.py"
    val = int(m.group(1))
    assert val >= 16_000, (
        f"max_output_tokens = {val}, esperado >= 16000"
    )


def test_gemini_engine_emits_truncated_event_constant():
    """gemini_engine.py debe tener la lógica para emitir evento `truncated`
    cuando finish_reason == MAX_TOKENS."""
    from app.config import BASE_DIR

    src = (BASE_DIR / "gemini_engine.py").read_text(encoding="utf-8")
    # Debe trackear finish_reason
    assert "finish_reason" in src
    # Debe detectar MAX_TOKENS
    assert "MAX_TOKENS" in src
    # Debe emitir evento truncated
    assert '"truncated"' in src or "'truncated'" in src


def test_chat_route_forwards_truncated_event():
    """app/routes/chat.py debe propagar el evento truncated al SSE."""
    from app.config import BASE_DIR

    src = (BASE_DIR / "app" / "routes" / "chat.py").read_text(encoding="utf-8")
    # Debe matchear el etype == "truncated"
    assert '"truncated"' in src or "'truncated'" in src


# ── Frontend tiene UI de "Continuar" ───────────────────────────────────


def test_frontend_has_continue_button():
    """static/index.html debe tener el botón "Continuar generación" + CSS."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert "continueGeneration" in html, (
        "Falta la función continueGeneration en el frontend"
    )
    assert "Continuar generación" in html, (
        "Falta el botón visible 'Continuar generación'"
    )
    # CSS del aviso
    assert "msg-truncated-notice" in html, "Falta el CSS del aviso de truncated"


def test_frontend_handles_truncated_event():
    """Frontend debe manejar el evento SSE 'truncated' en streamFromMessages."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # El handler del SSE
    assert "evt.type === 'truncated'" in html, (
        "streamFromMessages no maneja el evento 'truncated'"
    )
    # El message debe persistir el flag
    assert "truncated: wasTruncated" in html, (
        "El message no persiste el flag `truncated`"
    )


# ── Bug 3 — Refresh automático cubre admin token ──────────────────────


def test_frontend_has_periodic_refresh():
    """App component debe tener setInterval para refresh automático."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert "/api/auth/refresh" in html, (
        "Frontend no invoca /api/auth/refresh"
    )
    # Debe refrescar también el admin token
    assert "getAdminTok()" in html


# ── Mensaje legacy del admin panel quitado ────────────────────────────


def test_legacy_admin_notice_removed():
    """El mensaje 'La creación... llega en próxima fase' debe estar fuera."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert "llega en la próxima fase" not in html, (
        "Todavía está el aviso legacy 'llega en próxima fase' — ya no aplica"
    )
