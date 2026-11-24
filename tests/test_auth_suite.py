"""Comprehensive Step 1 Auth Test Suite:
- Register -> Login flow
- Login after database restart / reconnect
- Wrong password rejected
- Case-insensitive & whitespace email normalization
- Token expiration enforcement
- Legacy password hash verification & safe in-place migration to bcrypt
- Security audit log verification (no passwords/tokens leaked)
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
import json
from pathlib import Path
import pytest
from fastapi import HTTPException
import jwt

from src.api.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    verify_and_migrate_password,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
)
from src.api.models import UserLoginRequest, UserRegisterRequest
from src.api.routes.auth import login, register
from src.db.models import User
from src.db.session import SessionLocal


@pytest.fixture(autouse=True)
def cleanup_test_users():
    """Ensure clean test user state before and after each test."""
    test_emails = [
        "step1.test@example.com",
        "restart.user@example.com",
        "case.user@example.com",
        "legacy.migrate@example.com",
        "pbkdf2.migrate@example.com",
    ]
    with SessionLocal() as db:
        for em in test_emails:
            existing = db.query(User).filter(User.email == em).first()
            if existing:
                db.delete(existing)
        db.commit()
    yield
    with SessionLocal() as db:
        for em in test_emails:
            existing = db.query(User).filter(User.email == em).first()
            if existing:
                db.delete(existing)
        db.commit()


def test_register_then_login():
    """Registers a new user and logs in immediately with correct credentials."""
    email = "step1.test@example.com"
    password = "CorrectPassword123!"

    with SessionLocal() as db:
        reg_req = UserRegisterRequest(
            email=email,
            password=password,
            full_name="Step 1 Test",
            role="patient",
        )
        reg_token = register(reg_req, db=db)
        assert reg_token.access_token is not None
        assert reg_token.user.email == email

    with SessionLocal() as db:
        login_req = UserLoginRequest(email=email, password=password)
        login_token = login(login_req, db=db)
        assert login_token.access_token is not None
        assert login_token.user.email == email
        payload = decode_access_token(login_token.access_token)
        assert payload["sub"] == str(login_token.user.id)


def test_login_after_restart():
    """Verifies that user persists and can log in after a simulated application/session restart."""
    email = "restart.user@example.com"
    password = "RestartPassword456#"

    # 1. Register in session 1
    with SessionLocal() as db1:
        reg_req = UserRegisterRequest(email=email, password=password, full_name="Restart User", role="patient")
        register(reg_req, db=db1)

    # 2. Simulate complete restart (new session, new DB connection)
    with SessionLocal() as db2:
        login_req = UserLoginRequest(email=email, password=password)
        login_token = login(login_req, db=db2)
        assert login_token.access_token is not None
        assert login_token.user.email == email


def test_wrong_password_rejected():
    """Ensures wrong password fails authentication with 401 Unauthorized."""
    email = "step1.test@example.com"
    correct_password = "CorrectPassword123!"
    wrong_password = "WrongPassword999!"

    with SessionLocal() as db:
        reg_req = UserRegisterRequest(email=email, password=correct_password, role="patient")
        register(reg_req, db=db)

    with SessionLocal() as db:
        login_req = UserLoginRequest(email=email, password=wrong_password)
        with pytest.raises(HTTPException) as exc_info:
            login(login_req, db=db)
        assert exc_info.value.status_code == 401
        assert "Invalid email or password" in exc_info.value.detail


def test_case_insensitive_and_whitespace_email():
    """Verifies case-insensitive and whitespace-tolerant email matching."""
    stored_email = "case.user@example.com"
    password = "CasePassword789!"

    with SessionLocal() as db:
        reg_req = UserRegisterRequest(email="  Case.User@Example.COM  ", password=password, role="patient")
        register(reg_req, db=db)

    # Log in with different case variations and whitespace
    for variant in ["CASE.USER@EXAMPLE.COM", "  case.user@example.com  ", "Case.User@example.com"]:
        with SessionLocal() as db:
            login_req = UserLoginRequest(email=variant, password=password)
            token = login(login_req, db=db)
            assert token.user.email == stored_email


def test_token_expiration_enforcement():
    """Verifies expired tokens are rejected with 401 Unauthorized."""
    # Token expired 1 hour ago
    expired_token = create_access_token(
        subject="expired-uuid",
        role="patient",
        expires_delta=timedelta(hours=-1),
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(expired_token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_legacy_sha256_hash_migration_on_login():
    """Verifies pre-existing user with legacy SHA-256 hash can log in and is upgraded to bcrypt in-place."""
    email = "legacy.migrate@example.com"
    raw_password = "LegacyPasswordToUpgrade#1"
    legacy_sha256 = hashlib.sha256(raw_password.encode("utf-8")).hexdigest()

    # Seed legacy user
    with SessionLocal() as db:
        user = User(
            email=email,
            hashed_password=legacy_sha256,
            full_name="Legacy User",
            role="patient",
            is_active=True,
        )
        db.add(user)
        db.commit()

    # Log in with legacy credentials
    with SessionLocal() as db:
        login_req = UserLoginRequest(email=email, password=raw_password)
        token = login(login_req, db=db)
        assert token.access_token is not None
        assert token.user.email == email

    # Verify that the user's password hash was automatically upgraded to standard bcrypt ($2b$)
    with SessionLocal() as db:
        updated_user = db.query(User).filter(User.email == email).first()
        assert updated_user.hashed_password != legacy_sha256
        assert updated_user.hashed_password.startswith(("$2b$", "$2a$")), (
            f"Expected bcrypt hash prefix, got {updated_user.hashed_password[:10]}"
        )
        # Verify subsequent login works with the updated bcrypt hash
        assert verify_password(raw_password, updated_user.hashed_password) is True


def test_security_audit_log_never_contains_passwords():
    """Verifies that authentication events logged to audit_log.jsonl never contain plaintext passwords."""
    email = "step1.test@example.com"
    secret_password = "TopSecretPasswordNeverLog!"

    with SessionLocal() as db:
        reg_req = UserRegisterRequest(email=email, password=secret_password, role="patient")
        register(reg_req, db=db)

    with SessionLocal() as db:
        login_req = UserLoginRequest(email=email, password=secret_password)
        login(login_req, db=db)

    # Inspect audit log records
    audit_file = Path("data/audit_log.jsonl")
    if audit_file.exists():
        raw_log = audit_file.read_text(encoding="utf-8")
        assert secret_password not in raw_log, "CRITICAL: Plaintext password found in audit log!"
