"""Tests de las features de seguridad — SSRF, headers, filename, log sanitize, audit."""

from __future__ import annotations


# ── SSRF defense ─────────────────────────────────────────────────────


def test_url_safety_blocks_loopback():
    from app.security.url_safety import is_safe_url

    safe, reason = is_safe_url("http://127.0.0.1/admin")
    assert safe is False
    assert "loopback" in reason.lower()


def test_url_safety_blocks_localhost_name():
    from app.security.url_safety import is_safe_url

    safe, reason = is_safe_url("http://localhost:8000/api/admin/users")
    assert safe is False
    # 'localhost' resuelve a 127.0.0.1 (loopback) o ::1 (loopback IPv6)
    assert "loopback" in reason.lower()


def test_url_safety_blocks_private_ip():
    from app.security.url_safety import is_safe_url

    safe, reason = is_safe_url("http://192.168.1.1/admin")
    assert safe is False
    assert "privada" in reason.lower()


def test_url_safety_blocks_metadata_service():
    from app.security.url_safety import is_safe_url

    safe, reason = is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert safe is False
    # 169.254.x.x es link-local o explícitamente metadata service
    assert "metadata" in reason.lower() or "link-local" in reason.lower()


def test_url_safety_blocks_non_http_scheme():
    from app.security.url_safety import is_safe_url

    safe, reason = is_safe_url("file:///etc/passwd")
    assert safe is False
    assert "scheme" in reason.lower()


def test_url_safety_blocks_empty():
    from app.security.url_safety import is_safe_url

    safe, reason = is_safe_url("")
    assert safe is False


def test_url_safety_blocks_ftp():
    from app.security.url_safety import is_safe_url

    safe, _ = is_safe_url("ftp://example.com/file")
    assert safe is False


def test_url_safety_allows_public_url():
    from app.security.url_safety import is_safe_url

    # google.com es público — debe pasar el filtro SSRF
    safe, reason = is_safe_url("https://www.google.com")
    assert safe is True, f"Expected safe, got: {reason}"


def test_verify_pdf_url_rejects_localhost():
    from app.tools.pdf_verify import verify_pdf_url

    r = verify_pdf_url("http://localhost/secret.pdf")
    assert r["valid"] is False
    assert "seguridad" in r["reason"].lower() or "loopback" in r["reason"].lower()


# ── Filename sanitization ────────────────────────────────────────────


def test_safe_filename_strips_path_traversal():
    from app.security.files import safe_filename

    assert "/" not in safe_filename("../../../etc/passwd")
    assert "\\" not in safe_filename("..\\..\\windows\\system32\\config")
    # Solo se conserva el basename
    assert safe_filename("../../passwd") == "passwd"


def test_safe_filename_replaces_illegal_chars():
    from app.security.files import safe_filename

    out = safe_filename('archivo<>:"|?*.pdf')
    for c in '<>:"|?*':
        assert c not in out


def test_safe_filename_handles_empty():
    from app.security.files import safe_filename

    assert safe_filename("") == "archivo"
    assert safe_filename("   ") == "archivo"


def test_safe_filename_blocks_reserved_names():
    from app.security.files import safe_filename

    # CON, PRN, etc. son reservados en Windows
    out = safe_filename("CON.txt")
    assert out.upper() != "CON.TXT"
    assert out.startswith("_")


def test_safe_filename_truncates_long_names():
    from app.security.files import safe_filename

    long_name = "x" * 300 + ".pdf"
    out = safe_filename(long_name, max_len=120)
    assert len(out) <= 120
    assert out.endswith(".pdf")


# ── Log sanitization ─────────────────────────────────────────────────


def test_sanitize_dict_redacts_password():
    from app.security.log_sanitize import sanitize_dict

    out = sanitize_dict({"username": "alice", "password": "secret123"})
    assert out["username"] == "alice"
    assert out["password"] == "***REDACTED***"


def test_sanitize_dict_redacts_tokens_and_keys():
    from app.security.log_sanitize import sanitize_dict

    inp = {
        "data": "ok",
        "access_token": "eyJxxxx",
        "api_key": "sk-123",
        "client_secret": "xyz",
    }
    out = sanitize_dict(inp)
    assert out["data"] == "ok"
    assert out["access_token"] == "***REDACTED***"
    assert out["api_key"] == "***REDACTED***"
    assert out["client_secret"] == "***REDACTED***"


def test_redact_value_strips_jwts():
    from app.security.log_sanitize import redact_value

    msg = "Error en Authorization: eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiYWxpY2UifQ.abc123XYZ_-456"
    out = redact_value(msg)
    assert "***JWT_REDACTED***" in out
    assert "eyJhbGciOiJIUzI1NiJ9" not in out


def test_sanitize_pydantic_errors_redacts_password_input():
    from app.security.log_sanitize import sanitize_pydantic_errors

    errors = [
        {"loc": ("body", "password"), "msg": "too short", "input": "secret_real"},
        {"loc": ("body", "username"), "msg": "missing"},
    ]
    out = sanitize_pydantic_errors(errors)
    assert out[0]["input"] == "***REDACTED***"
    assert "input" not in out[1]


# ── Security headers ─────────────────────────────────────────────────


def test_security_headers_present(client):
    r = client.get("/api/version")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "strict-origin" in r.headers.get("Referrer-Policy", "")
    assert "camera" in r.headers.get("Permissions-Policy", "")


# ── Audit log ────────────────────────────────────────────────────────


def test_audit_event_writes_to_log(tmp_path, monkeypatch):
    from app.storage import audit as audit_mod

    fake = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit_mod, "AUDIT_LOG_PATH", fake)

    audit_mod.audit_event(
        actor="admin",
        action="user_created",
        target="user:nuevo",
        meta={"role": "regular"},
    )
    audit_mod.audit_event(actor="admin", action="user_deleted", target="user:nuevo")

    events = audit_mod.read_audit_events(limit=10)
    assert len(events) == 2
    # Más reciente primero
    assert events[0]["action"] == "user_deleted"
    assert events[1]["action"] == "user_created"
    assert events[1]["meta"]["role"] == "regular"


def test_audit_event_truncates_long_strings(tmp_path, monkeypatch):
    from app.storage import audit as audit_mod

    fake = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit_mod, "AUDIT_LOG_PATH", fake)

    audit_mod.audit_event(
        actor="x" * 200,
        action="test",
        target="y" * 300,
        meta={"big_val": "z" * 1000},
    )
    events = audit_mod.read_audit_events(limit=1)
    assert len(events[0]["actor"]) <= 64
    assert len(events[0]["target"]) <= 200
    assert len(events[0]["meta"]["big_val"]) <= 500


# ── Body size limits ─────────────────────────────────────────────────


def test_body_size_limit_login_rejects_oversized(client):
    # Login tiene límite de 4KB. Mandamos 100KB.
    big_payload = {"username": "x", "password": "p" * 100_000}
    r = client.post("/api/login", json=big_payload)
    # Cuando Content-Length excede → 413
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


# ── Backups ──────────────────────────────────────────────────────────


def test_backup_run_creates_dated_folder(tmp_path, monkeypatch):
    from app.storage import backups as bk

    # Aislar todas las rutas usadas por backups
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    # Crear archivos de prueba para backupear
    users_file = tmp_path / "users.json"
    users_file.write_text('{"u":"x"}', encoding="utf-8")
    monkeypatch.setattr(bk, "USERS_PATH", users_file)
    # Los demás los apuntamos a paths inexistentes (skipped)
    monkeypatch.setattr(bk, "AGENTS_PATH", tmp_path / "no.json")
    monkeypatch.setattr(bk, "CONVERSATIONS_LOG_PATH", tmp_path / "no.jsonl")
    monkeypatch.setattr(bk, "MEMORY_PATH", tmp_path / "no.json")
    monkeypatch.setattr(bk, "RUNTIME_CONFIG_PATH", tmp_path / "no.json")
    monkeypatch.setattr(bk, "SYSTEM_PROMPT_CUSTOM_PATH", tmp_path / "no.txt")
    monkeypatch.setattr(bk, "AUDIT_LOG_PATH", tmp_path / "no.jsonl")

    stats = bk.run_backup_now()
    assert stats["copied"] == 1
    assert stats["skipped"] == 6
    assert stats["errors"] == 0

    # Verificar que existe la carpeta y el archivo
    today_dir = tmp_path / "backups" / stats["date"]
    assert today_dir.exists()
    assert (today_dir / "users.json").exists()
