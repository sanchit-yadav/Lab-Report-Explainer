"""Reproduction test showing before vs after fix for:
'can't log in with previously correct details'

BEFORE FIX:
- verify_password(plain, legacy_sha256) returned False
- login(req) for a user created with legacy hash raised 401 HTTPException

AFTER FIX:
- verify_password(plain, legacy_sha256) returns True
- login(req) succeeds, returns TokenResponse with valid JWT
- Stored password hash is migrated in-place to modern bcrypt
"""

from __future__ import annotations

import hashlib

from src.api.auth import verify_password
from src.api.models import UserLoginRequest
from src.api.routes.auth import login
from src.db.models import User
from src.db.session import SessionLocal


def test_legacy_hash_now_verifies_successfully():
    """AFTER FIX: Legacy SHA-256 password hash verifies successfully via migration engine."""
    password = "MyCorrectPassword2026!"
    legacy_sha256_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

    # Fixed: legacy hashes now return True via verify_and_migrate_password
    assert verify_password(password, legacy_sha256_hash) is True


def test_legacy_user_now_logs_in_and_upgrades_to_bcrypt():
    """AFTER FIX: Pre-existing user with legacy hash can log in and gets upgraded to bcrypt."""
    test_email = "preexisting.legacy.user@example.com"
    raw_password = "ValidPassword#2026"
    legacy_hash = hashlib.sha256(raw_password.encode("utf-8")).hexdigest()

    # Seed legacy user
    with SessionLocal() as db:
        existing = db.query(User).filter(User.email == test_email).first()
        if existing:
            db.delete(existing)
            db.commit()

        user = User(
            email=test_email,
            hashed_password=legacy_hash,
            full_name="Pre-Existing User",
            is_active=True,
        )
        db.add(user)
        db.commit()

    # Attempt login with previously correct details
    with SessionLocal() as db:
        req = UserLoginRequest(email=test_email, password=raw_password)
        # Fixed: login now succeeds with valid token response!
        token_resp = login(req, db=db)
        assert token_resp.access_token is not None
        assert token_resp.user.email == test_email

    # Verify that in the database, the hash was migrated in-place to modern bcrypt
    with SessionLocal() as db:
        updated = db.query(User).filter(User.email == test_email).first()
        assert updated.hashed_password != legacy_hash
        assert updated.hashed_password.startswith(("$2b$", "$2a$"))
