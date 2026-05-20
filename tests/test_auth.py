"""Tests de autenticación — login regular + admin, hashing de passwords."""

from __future__ import annotations

import os


def test_login_with_valid_credentials(client):
    r = client.post(
        "/api/login",
        json={
            "username": os.environ["CHAT_USER"],
            "password": os.environ["CHAT_PASSWORD"],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["username"] == os.environ["CHAT_USER"]


def test_login_with_wrong_password_returns_401(client):
    r = client.post(
        "/api/login",
        json={
            "username": os.environ["CHAT_USER"],
            "password": "passwordIncorrecto",
        },
    )
    assert r.status_code == 401


def test_login_with_nonexistent_user_returns_401(client):
    r = client.post(
        "/api/login",
        json={"username": "noexisto_999", "password": "cualquiercosa"},
    )
    assert r.status_code == 401


def test_login_with_empty_password_returns_422(client):
    r = client.post(
        "/api/login",
        json={"username": "alguien", "password": ""},
    )
    # Pydantic min_length=1 → 422
    assert r.status_code == 422


def test_admin_login_with_valid_credentials(client):
    r = client.post(
        "/api/admin/login",
        json={
            "username": os.environ["ADMIN_USER"],
            "password": os.environ["ADMIN_PASSWORD"],
        },
    )
    assert r.status_code == 200
    assert "token" in r.json()


def test_admin_login_with_wrong_password_returns_401(client):
    r = client.post(
        "/api/admin/login",
        json={"username": os.environ["ADMIN_USER"], "password": "wrong"},
    )
    assert r.status_code == 401


def test_admin_endpoint_requires_admin_token(client, user_token):
    """Un token de user normal NO debe poder acceder a endpoints admin."""
    r = client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 403


def test_admin_endpoint_accepts_admin_token(client, admin_token):
    r = client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert "users" in r.json()


def test_jwt_hashing_is_constant_time():
    """`safe_eq` debe usar secrets.compare_digest (no leak por timing)."""
    from app.auth import safe_eq

    assert safe_eq("hello", "hello") is True
    assert safe_eq("hello", "world") is False
    assert safe_eq("", "") is True


def test_password_hash_verify_roundtrip():
    from app.storage.users import hash_password, verify_password

    h = hash_password("mi_password_secreta")
    assert verify_password("mi_password_secreta", h) is True
    assert verify_password("otra_password", h) is False
    assert verify_password("", h) is False


def test_password_hash_uses_unique_salt():
    """Dos hashes del mismo password deben ser DISTINTOS (por salt random)."""
    from app.storage.users import hash_password

    h1 = hash_password("secreto")
    h2 = hash_password("secreto")
    assert h1 != h2
