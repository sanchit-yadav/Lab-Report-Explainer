"""Tests for authentication, JWT lifecycle, password hashing, and multi-user isolation."""

from datetime import timedelta

import pytest
from starlette.testclient import TestClient

from src.api.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.api.main import app
from src.db.models import User
from src.db.session import SessionLocal
from src.workers.job_manager import JobManager


@pytest.fixture
def client():
    """TestClient fixture for FastAPI application."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    """Clean database and job manager before and after tests."""
    jm = JobManager.get_instance()
    jm.clear()
    with SessionLocal() as db:
        db.query(User).delete()
        db.commit()
    yield
    jm.clear()
    with SessionLocal() as db:
        db.query(User).delete()
        db.commit()


def test_password_hashing():
    """Bcrypt password hashing and constant-time verification."""
    password = "StrongPassword#2026"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False
    assert verify_password(password, "invalid_hash_format") is False


def test_jwt_token_creation_and_decoding():
    """Valid token encoding and payload claims extraction."""
    user_id = "test-uuid-1234"
    token = create_access_token(subject=user_id, expires_delta=timedelta(minutes=15))

    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_token_expiration():
    """Expired token raises 401 Unauthorized exception."""
    from fastapi import HTTPException

    user_id = "test-uuid-expired"
    token = create_access_token(subject=user_id, expires_delta=timedelta(seconds=-10))

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_jwt_token_invalid():
    """Malformed token raises 401 Unauthorized exception."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not.a.valid.jwt.token")
    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


def test_user_registration_success(client):
    """Registering a new account returns 201 Created and JWT bearer token."""
    payload = {
        "email": "clinical.user@example.com",
        "password": "SecurePassword123!",
        "full_name": "Alice Smith",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    user_info = data["user"]
    assert user_info["email"] == "clinical.user@example.com"
    assert user_info["full_name"] == "Alice Smith"
    assert user_info["is_active"] is True
    assert "id" in user_info


def test_user_registration_duplicate_email(client):
    """Registering with an already existing email returns 409 Conflict."""
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!",
        "full_name": "User One",
    }
    resp1 = client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]


def test_user_registration_short_password(client):
    """Registering with password under 8 characters returns 422 Unprocessable Entity."""
    payload = {
        "email": "short@example.com",
        "password": "short",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_user_login_success(client):
    """Authenticating with correct credentials returns 200 OK and JWT."""
    # Register first
    client.post(
        "/api/v1/auth/register",
        json={"email": "login.test@example.com", "password": "Password123!", "full_name": "Bob"},
    )

    # Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "login.test@example.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "login.test@example.com"


def test_user_login_invalid_password(client):
    """Authenticating with wrong password returns 401 Unauthorized."""
    client.post(
        "/api/v1/auth/register",
        json={"email": "wrongpw@example.com", "password": "CorrectPassword123!"},
    )

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "WrongPassword!"},
    )
    assert login_resp.status_code == 401
    assert "Invalid email or password" in login_resp.json()["detail"]


def test_user_login_nonexistent_email(client):
    """Authenticating with non-existent email returns 401 Unauthorized."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 401
    assert "Invalid email or password" in login_resp.json()["detail"]


def test_user_login_deactivated_account(client):
    """Deactivated accounts cannot authenticate and receive 403 Forbidden."""
    # Register user
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "deactivated@example.com", "password": "Password123!"},
    )
    user_id = reg_resp.json()["user"]["id"]

    # Deactivate in database
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        user.is_active = False
        db.commit()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "deactivated@example.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 403
    assert "deactivated" in login_resp.json()["detail"]


def test_get_me_authenticated(client):
    """GET /api/v1/auth/me returns current user profile when Bearer token is provided."""
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "me.test@example.com", "password": "Password123!", "full_name": "Me Tester"},
    )
    token = reg_resp.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me.test@example.com"
    assert data["full_name"] == "Me Tester"


def test_get_me_unauthorized(client):
    """GET /api/v1/auth/me returns 401 Unauthorized without token or with invalid token."""
    # Missing token
    resp1 = client.get("/api/v1/auth/me")
    assert resp1.status_code == 401

    # Invalid token
    resp2 = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.value"})
    assert resp2.status_code == 401


def test_multi_user_report_isolation(client, tmp_path):
    """Reports uploaded by User A are not visible in User B's list."""
    from unittest.mock import patch

    # Register User A and User B
    resp_a = client.post(
        "/api/v1/auth/register",
        json={"email": "userA@example.com", "password": "Password123!"},
    )
    token_a = resp_a.json()["access_token"]

    resp_b = client.post(
        "/api/v1/auth/register",
        json={"email": "userB@example.com", "password": "Password123!"},
    )
    token_b = resp_b.json()["access_token"]

    # User A uploads a report
    content = b"%PDF-1.4 User A clinical report data"
    files = {"file": ("report_user_a.pdf", content, "application/pdf")}
    with patch("src.workers.job_manager.JobManager.run_pipeline_job"):
        upload_resp = client.post(
            "/api/v1/reports/upload",
            files=files,
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert upload_resp.status_code == 202

    # User A lists reports -> sees 1 report
    list_a = client.get("/api/v1/reports", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    data_a = list_a.json()
    assert len(data_a) == 1
    assert data_a[0]["filename"] == "report_user_a.pdf"

    # User B lists reports -> sees 0 reports (isolated)
    list_b = client.get("/api/v1/reports", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    data_b = list_b.json()
    assert len(data_b) == 0
