"""Tests de los endpoints /api/health, /api/admin/health y /api/version.

Política (v1.1.1+):
- /api/health        público, mínimo (status, version, timestamp)
- /api/admin/health  requiere auth admin, devuelve detalle profundo
- /api/version       público, sólo versión
"""

from __future__ import annotations


# ── Endpoint público (mínimo) ─────────────────────────────────────────


def test_version_endpoint(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_endpoint_no_auth_required(client):
    """Health público no requiere token — para load balancers / monitoring externo."""
    r = client.get("/api/health")
    assert r.status_code == 200


def test_health_endpoint_returns_only_minimal_info(client):
    """El endpoint público NO debe revelar discovery info (catálogo, LLM, disk)."""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    # Debe traer status, version, timestamp
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data
    # Y NADA MÁS — específicamente, ningún detalle interno
    forbidden = {
        "checks",
        "catalog_size",
        "catalog_loaded",
        "llm_provider",
        "llm_reachable",
        "disk_free_mb",
        "users_db_readable",
        "tavily_configured",
        "datasheets_dir",
        "documents_dir",
        "conversations_log_writable",
    }
    leaked = forbidden.intersection(data.keys())
    assert not leaked, f"Endpoint público filtra: {leaked}"


# ── Endpoint admin (detallado) ────────────────────────────────────────


def test_admin_health_requires_auth(client):
    r = client.get("/api/admin/health")
    # Sin token → 401 (HTTPBearer no provisto)
    assert r.status_code in (401, 403)


def test_admin_health_rejects_user_token(client, user_token):
    r = client.get(
        "/api/admin/health",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    # Token válido pero sin role=admin → 403
    assert r.status_code == 403


def test_admin_health_returns_all_checks(client, admin_token):
    r = client.get(
        "/api/admin/health",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert "checks" in data
    checks = data["checks"]
    for key in (
        "catalog_loaded",
        "catalog_size",
        "users_db_readable",
        "llm_provider",
        "llm_reachable",
        "tavily_configured",
        "disk_free_mb",
    ):
        assert key in checks, f"missing check: {key}"


# ── Discovery surface cerrada ─────────────────────────────────────────


def test_docs_disabled_by_default(client):
    """Swagger UI no debe estar accesible sin DOCS_ENABLED=true."""
    r = client.get("/docs")
    # Cuando docs_url=None, FastAPI no registra la ruta → cae al StaticFiles
    # mount o devuelve 404. Lo importante es que NO sea 200 con HTML de Swagger.
    if r.status_code == 200:
        body = r.text.lower()
        assert "swagger" not in body, "Swagger UI sigue expuesto sin DOCS_ENABLED"


def test_openapi_schema_disabled_by_default(client):
    """El schema OpenAPI no debe estar público — revela el mapa completo del API."""
    r = client.get("/openapi.json")
    # Tiene que ser 404. Si es 200, validar que NO devuelva un schema OpenAPI.
    if r.status_code == 200:
        try:
            data = r.json()
            assert "openapi" not in data and "paths" not in data, (
                "Schema OpenAPI expuesto sin auth"
            )
        except ValueError:
            # No es JSON → probablemente sirve index.html del SPA, OK
            pass


def test_redoc_disabled_by_default(client):
    r = client.get("/redoc")
    if r.status_code == 200:
        body = r.text.lower()
        assert "redoc" not in body, "ReDoc sigue expuesto sin DOCS_ENABLED"
