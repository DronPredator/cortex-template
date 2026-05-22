"""Tests del paquete de hardening v1.2.1 — backlog de seguridad post-chequeo.

Cubre:
  - M1 zip-bomb protection en document_extract
  - B2 audit log de user login failed
  - B3 .gitignore con claves criptográficas
  - B4 defusedxml activado en main
  - M2 pin de versión exacta en CDN scripts
  - M3 SRI hashes en CDN scripts
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path


# ── M1 — Zip-bomb protection ──────────────────────────────────────────


def _build_zip_with_payload(payload: bytes, name: str = "doc.xml") -> bytes:
    """Construye un .zip en memoria con un único archivo de bytes `payload`."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr(name, payload)
    return buf.getvalue()


def test_zip_bomb_high_ratio_rejected():
    """ZIP con ratio de compresión >1000:1 debe ser rechazado."""
    from document_extract import ZipBombError, _check_zip_safety

    # 5 MB de ceros comprimen muy bien (~5 KB) → ratio ~1000:1
    bomb = _build_zip_with_payload(b"\x00" * (5 * 1024 * 1024))
    try:
        _check_zip_safety(bomb)
    except ZipBombError as e:
        msg = str(e).lower()
        assert "ratio" in msg or "compresión" in msg or "compresion" in msg
    else:
        raise AssertionError("Zip-bomb con ratio alto debería rechazarse")


def test_zip_bomb_huge_uncompressed_rejected():
    """ZIP cuya descompresión total supera 200MB debe ser rechazado."""
    from document_extract import ZipBombError, _check_zip_safety

    # Construir un ZIP donde la suma de file_size declarados supera 200MB.
    # Truco: el ZipFile guarda file_size en el header; un atacante podría
    # mentir en el header (DEFLATE no garantiza el tamaño anunciado), pero
    # el `infolist()` lee del header anyway — así detectamos la intención
    # antes de descomprimir.
    bomb = _build_zip_with_payload(b"\x00" * (250 * 1024 * 1024))
    try:
        _check_zip_safety(bomb)
    except ZipBombError as e:
        assert "MB" in str(e) or "ratio" in str(e).lower()
    else:
        raise AssertionError("ZIP de 250MB descomprimido debería rechazarse")


def test_zip_bomb_too_many_entries_rejected():
    """ZIP con >5000 archivos internos debe ser rechazado."""
    from document_extract import ZipBombError, _check_zip_safety

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(6_000):
            zf.writestr(f"f{i}.xml", b"x")
    try:
        _check_zip_safety(buf.getvalue())
    except ZipBombError as e:
        assert "archivos" in str(e).lower() or "entries" in str(e).lower()
    else:
        raise AssertionError("ZIP con 6000 entries debería rechazarse")


def test_legitimate_zip_passes():
    """ZIP normal (poca data, ratio razonable) debe pasar."""
    from document_extract import _check_zip_safety

    # ~100 KB de texto random — ratio ~1:1 con DEFLATE
    import os
    payload = os.urandom(100 * 1024)
    benign = _build_zip_with_payload(payload)
    # No debe levantar
    _check_zip_safety(benign)


def test_non_zip_data_returns_silently():
    """Bytes que no son ZIP no levantan error (upstream lib se encargará)."""
    from document_extract import _check_zip_safety

    # Texto plano — no es ZIP
    _check_zip_safety(b"hello world not a zip")
    # PDF magic bytes pero estructura inválida — tampoco es ZIP
    _check_zip_safety(b"%PDF-1.4 fake")


def test_extract_returns_clear_error_on_zip_bomb():
    """extract() captura ZipBombError y devuelve mensaje específico."""
    from document_extract import extract

    bomb = _build_zip_with_payload(b"\x00" * (5 * 1024 * 1024))
    result = extract("malicious.docx", bomb)
    assert result.get("error"), "Debería tener error"
    assert "zip-bomb" in result["error"].lower(), (
        f"Mensaje de error debe mencionar zip-bomb, vino: {result['error']!r}"
    )


# ── B2 — Audit log de user login failed ───────────────────────────────


def test_user_login_failed_writes_audit_entry(client, tmp_path, monkeypatch):
    """Un intento de login fallido debe escribir entrada en el audit log."""
    from app import config
    from app.storage import audit

    # Aislar audit_log a un tmpfile específico de este test
    audit_path = tmp_path / "audit_test.jsonl"
    monkeypatch.setattr(config, "AUDIT_LOG_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_LOG_PATH", audit_path)

    # Trigger: login con credenciales malas
    r = client.post(
        "/api/login",
        json={"username": "atacante_inventado", "password": "wrong"},
    )
    assert r.status_code == 401

    # Audit log debe haber registrado
    assert audit_path.exists(), "audit_log.jsonl debería haberse creado"
    content = audit_path.read_text(encoding="utf-8")
    assert "user_login_failed" in content
    assert "atacante_inventado" in content


# ── B3 — .gitignore con claves criptográficas ─────────────────────────


def test_gitignore_includes_crypto_keys():
    """El .gitignore debe excluir tipos comunes de archivos de claves."""
    from app.config import BASE_DIR

    gi = (BASE_DIR / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.key", "*.pem", "id_rsa", "id_ed25519", "*.p12", "*.pfx"):
        assert pattern in gi, f"Falta '{pattern}' en .gitignore"


# ── B4 — defusedxml activado ──────────────────────────────────────────


def test_defusedxml_stdlib_defused():
    """Importar app.main debe haber llamado defusedxml.defuse_stdlib().

    Cuando defuse_stdlib() fue invocado, el parser de xml.etree queda
    monkey-patched para usar el de defusedxml. Verificamos por la API
    pública: parsear XML con external entity debe levantar error.
    """
    import app.main  # noqa: F401 — solo el import activa defuse_stdlib

    # Después del import, el XMLParser de xml.etree NO debe resolver
    # external entities. Probamos con un payload billion-laughs simplificado:
    import xml.etree.ElementTree as ET

    billion_laughs = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    ]>
    <lolz>&lol2;</lolz>"""

    # defusedxml lanza EntitiesForbidden (subclase de DefusedXmlException
    # que a su vez extiende ValueError). En etree post-defuse, el parser
    # de stdlib levanta error en lugar de expandir.
    try:
        ET.fromstring(billion_laughs)
    except Exception as e:
        # Aceptamos cualquier error — el punto es que NO lo procese.
        name = type(e).__name__
        msg = str(e).lower()
        assert "entit" in msg or "forbidden" in name.lower() or "defused" in name.lower(), (
            f"Excepción inesperada al parsear XML con entity: {name}: {e}"
        )
    else:
        raise AssertionError(
            "billion-laughs XML no levantó error → defusedxml NO está activo"
        )


# ── M2 — Pin de versiones exactas en CDN ──────────────────────────────


def test_cdn_scripts_pinned_to_exact_version():
    """Los <script> de unpkg deben tener versión exacta (X.Y.Z), no
    @latest ni rangos genéricos."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # Capturamos todos los src="https://unpkg.com/<paquete>@<algo>/<resto>"
    pattern = re.compile(
        r'src="https://unpkg\.com/(@?[\w./-]+)@([^/"]+)/'
    )
    matches = pattern.findall(html)
    assert matches, "No se encontraron scripts de unpkg en index.html"
    for pkg, version in matches:
        # Versión exacta: X.Y.Z (3 partes numéricas con punto)
        assert re.match(r"^\d+\.\d+\.\d+$", version), (
            f"Script {pkg} usa versión '{version}' — debe ser X.Y.Z exacto, "
            f"no rangos ni @latest"
        )


# ── M3 — SRI hashes en CDN scripts ────────────────────────────────────


def test_cdn_scripts_have_sri_integrity():
    """Todos los <script src="https://unpkg.com/..."> deben tener
    integrity= sha384-XXX y crossorigin=anonymous."""
    from app.config import BASE_DIR

    html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    # Cada bloque de <script ...></script> que tenga unpkg.com en el src
    # debe tener un integrity con sha384- en el mismo tag.
    # Aceptamos saltos de línea entre atributos.
    script_pattern = re.compile(
        r"<script[^>]*?src=\"https://unpkg\.com[^\"]+\"[^>]*?>",
        re.IGNORECASE | re.DOTALL,
    )
    scripts = script_pattern.findall(html)
    assert scripts, "No se encontraron <script src=unpkg> en index.html"
    for s in scripts:
        assert 'integrity="sha384-' in s, (
            f"<script> de unpkg sin integrity sha384:\n{s[:200]}"
        )
        assert 'crossorigin="anonymous"' in s, (
            f"<script> de unpkg con integrity pero sin crossorigin=anonymous:\n{s[:200]}"
        )
