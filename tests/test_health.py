"""Tests del endpoint /api/health."""

from __future__ import annotations


def test_version_endpoint(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_endpoint_returns_all_checks(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert "checks" in data
    checks = data["checks"]
    # Critical checks must be present
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


def test_health_endpoint_no_auth_required(client):
    """Health debe ser público para que monitoring lo lea sin token."""
    r = client.get("/api/health")
    assert r.status_code == 200
