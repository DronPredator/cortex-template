"""Tests del feature de upload de iconos custom para agentes (v1.4.0).

Endpoints:
  POST   /api/admin/agents/{id}/icon  (multipart file)
  DELETE /api/admin/agents/{id}/icon

Validaciones:
  - Magic bytes PNG/JPG (no se confía en la extensión declarada).
  - Tamaño <= 2 MB.
  - Solo admin.
  - Agente debe existir.
  - icon_url se actualiza con cache-buster `?v=<ts>`.
"""

from __future__ import annotations

import io
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────


# PNG mínimo válido (1x1 transparente). Cumple los magic bytes \x89PNG...
_MIN_PNG = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
    0x89, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41,
    0x54, 0x78, 0x9C, 0x62, 0x00, 0x01, 0x00, 0x00,
    0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
    0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
    0x42, 0x60, 0x82,
])

# JPG mínimo válido (estructura mínima JFIF que cumple los magic bytes \xff\xd8\xff)
_MIN_JPG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00\x43\x00" + b"\x08" * 64 +
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x14\x00\x01" + b"\x00" * 16 + b"\x00"
    b"\xff\xc4\x00\x14\x10\x01" + b"\x00" * 16 + b"\x00"
    b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
    b"\xfc\xff\xd9"
)


def _icon_dir():
    """Devuelve la carpeta static/agents y la crea si hace falta."""
    from app.config import STATIC_DIR
    d = STATIC_DIR / "agents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clean_test_icons(agent_id="demo_assistant"):
    """Asegurar que no quedan archivos del agente entre tests."""
    d = _icon_dir()
    for ext in (".png", ".jpg", ".jpeg"):
        p = d / f"{agent_id}{ext}"
        if p.exists():
            p.unlink()


import pytest


@pytest.fixture
def icon_sandbox():
    """Fixture que backupea los iconos de los 4 agentes oficiales antes del
    test y los restaura al terminar.

    Los tests modifican `static/agents/<agent>.png` directamente (sube,
    borra, reemplaza) — sin este sandbox, después de correr `pytest tests/`
    quedaría sin `fidi.png`/`steamy_seg.png`/etc en disco, rompiendo el
    branding visual del frontend Y otros tests (ej. el del v1.3.3 que
    verifica que los icon_urls del registry no apunten a archivos
    inexistentes).

    También restaura el `icon_url` de los agentes en `agents.json` por si
    los tests lo modificaron con cache-busters.
    """
    from app.agents.registry import get_agent, upsert_agent

    d = _icon_dir()
    agent_ids = ["demo_assistant", "steamy_seg", "generador_codigos", "generador_informes"]

    # Backup
    saved_files = {}
    saved_icon_urls = {}
    for aid in agent_ids:
        for ext in (".png", ".jpg", ".jpeg"):
            p = d / f"{aid}{ext}"
            if p.exists():
                saved_files[(aid, ext)] = p.read_bytes()
        agent = get_agent(aid)
        if agent is not None:
            saved_icon_urls[aid] = agent.icon_url

    yield

    # Restore: borrar todo lo que dejaron los tests
    for aid in agent_ids:
        for ext in (".png", ".jpg", ".jpeg"):
            p = d / f"{aid}{ext}"
            if p.exists():
                p.unlink()

    # Restaurar archivos originales
    for (aid, ext), data in saved_files.items():
        (d / f"{aid}{ext}").write_bytes(data)

    # Restaurar icon_url en agents.json
    for aid, original_url in saved_icon_urls.items():
        agent = get_agent(aid)
        if agent is not None and agent.icon_url != original_url:
            agent.icon_url = original_url
            upsert_agent(agent)


# ── Magic bytes / sniff ───────────────────────────────────────────────


def test_sniff_image_detects_png():
    from app.routes.admin_agents import _sniff_image_ext

    assert _sniff_image_ext(_MIN_PNG) == ".png"
    # Datos al azar no son imagen
    assert _sniff_image_ext(b"hello world") is None
    # Empty
    assert _sniff_image_ext(b"") is None


def test_sniff_image_detects_jpg():
    from app.routes.admin_agents import _sniff_image_ext

    assert _sniff_image_ext(_MIN_JPG) == ".jpg"


def test_sniff_rejects_renamed_exe():
    """Un EXE renombrado a .png debe ser detectado por magic bytes."""
    from app.routes.admin_agents import _sniff_image_ext

    fake_png = b"MZ\x90\x00" + b"\x00" * 1000  # EXE header (MZ)
    assert _sniff_image_ext(fake_png) is None


# ── POST endpoint ─────────────────────────────────────────────────────


def test_upload_icon_requires_admin(client):
    """Sin token o con token de user normal → 401/403."""
    r = client.post("/api/admin/agents/demo_assistant/icon", files={"file": ("a.png", _MIN_PNG, "image/png")})
    assert r.status_code in (401, 403)


def test_upload_icon_rejects_non_existing_agent(client, admin_token):
    r = client.post(
        "/api/admin/agents/no_existe/icon",
        files={"file": ("a.png", _MIN_PNG, "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404


def test_upload_icon_rejects_invalid_extension(client, admin_token):
    r = client.post(
        "/api/admin/agents/demo_assistant/icon",
        files={"file": ("malicious.exe", _MIN_PNG, "application/octet-stream")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400
    assert "no soportado" in r.json()["detail"].lower() or "exe" in r.json()["detail"].lower()


def test_upload_icon_rejects_fake_png(client, admin_token):
    """Archivo con extensión .png pero contenido no es PNG → rechazado por magic bytes."""
    r = client.post(
        "/api/admin/agents/demo_assistant/icon",
        files={"file": ("fake.png", b"this is not a real png", "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400
    assert "magic" in r.json()["detail"].lower() or "imagen" in r.json()["detail"].lower()


def test_upload_icon_rejects_empty_file(client, admin_token):
    r = client.post(
        "/api/admin/agents/demo_assistant/icon",
        files={"file": ("empty.png", b"", "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400


def test_upload_icon_rejects_too_large(client, admin_token):
    """Archivo > 2MB → 413."""
    # PNG válido al inicio + padding hasta 3MB
    big = _MIN_PNG + b"\x00" * (3 * 1024 * 1024)
    r = client.post(
        "/api/admin/agents/demo_assistant/icon",
        files={"file": ("big.png", big, "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 413


def test_upload_icon_happy_path_png(client, admin_token, icon_sandbox):
    """Upload válido: guarda archivo, actualiza icon_url con cache-buster, audit log."""
    _clean_test_icons("demo_assistant")
    r = client.post(
        "/api/admin/agents/demo_assistant/icon",
        files={"file": ("anything.png", _MIN_PNG, "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["filename"] == "demo_assistant.png"
    assert data["format"] == "png"
    assert data["icon_url"].startswith("/agents/demo_assistant.png?v=")

    # Archivo realmente guardado
    out = _icon_dir() / "demo_assistant.png"
    assert out.exists()
    assert out.read_bytes() == _MIN_PNG

    # agents.json refleja el nuevo icon_url
    from app.agents.registry import get_agent
    agent = get_agent("demo_assistant")
    assert agent.icon_url == data["icon_url"]


def test_upload_icon_replaces_previous(client, admin_token, icon_sandbox):
    """Subir un PNG y después un JPG borra el PNG viejo."""
    _clean_test_icons("demo_assistant")
    # 1. Subir PNG
    r = client.post(
        "/api/admin/agents/demo_assistant/icon",
        files={"file": ("a.png", _MIN_PNG, "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert (_icon_dir() / "demo_assistant.png").exists()

    # 2. Subir JPG (mismo agente) — borra PNG y crea JPG
    r = client.post(
        "/api/admin/agents/demo_assistant/icon",
        files={"file": ("a.jpg", _MIN_JPG, "image/jpeg")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["filename"] == "demo_assistant.jpg"
    assert not (_icon_dir() / "demo_assistant.png").exists(), "PNG viejo no fue borrado"
    assert (_icon_dir() / "demo_assistant.jpg").exists()


# ── DELETE endpoint ───────────────────────────────────────────────────


def test_delete_icon_clears_files_and_url(client, admin_token, icon_sandbox):
    _clean_test_icons("demo_assistant")
    # 1. Subir
    client.post(
        "/api/admin/agents/demo_assistant/icon",
        files={"file": ("a.png", _MIN_PNG, "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert (_icon_dir() / "demo_assistant.png").exists()
    from app.agents.registry import get_agent
    assert get_agent("demo_assistant").icon_url != ""

    # 2. Borrar
    r = client.delete(
        "/api/admin/agents/demo_assistant/icon",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["files_deleted"] >= 1

    # Archivo borrado
    assert not (_icon_dir() / "demo_assistant.png").exists()

    # icon_url limpio
    assert get_agent("demo_assistant").icon_url == ""


def test_delete_icon_idempotent(client, admin_token, icon_sandbox):
    """Borrar cuando no hay icono: igual responde 200."""
    _clean_test_icons("demo_assistant")
    # Sin subir nada antes
    r = client.delete(
        "/api/admin/agents/demo_assistant/icon",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["files_deleted"] == 0


# ── Frontend wiring ───────────────────────────────────────────────────


def test_icon_section_component_exists():
    """El componente IconSection está en el HTML y se referencia en el editor."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert "function IconSection(" in html, "Falta el componente IconSection"
    assert "<IconSection" in html, "IconSection no está montado en el editor de agentes"
    # Que use el endpoint correcto
    assert "/icon" in html
