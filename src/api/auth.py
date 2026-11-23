"""Authentication, password hashing, JWT bearer token management, and FastAPI security dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from src.db.models import User
from src.db.session import get_db

logger = logging.getLogger("auth")

# Cryptographic secret key for signing JWTs (must be at least 32 bytes)
DEFAULT_DEV_JWT_SECRET = (
    "clinical-cds-lab-report-explainer-enterprise-secret-key-2026-secure-phi-token-v1"
)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", DEFAULT_DEV_JWT_SECRET)
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # Default 24 hours
_BCRYPT_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", "12"))


def validate_jwt_security() -> bool:
    """Validate that the JWT signing secret meets production security criteria.

    Raises:
        RuntimeError: If running in production with the default or a weak key.
    """
    env = os.environ.get("ENV") or os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development"
    is_prod = env.strip().lower() in ("production", "prod", "staging")
    secret = os.environ.get("JWT_SECRET_KEY", DEFAULT_DEV_JWT_SECRET)

    if is_prod:
        if secret == DEFAULT_DEV_JWT_SECRET:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: The default development JWT_SECRET_KEY "
                "is being used in a production environment! Generate a cryptographically secure 256-bit "
                "key (e.g. `openssl rand -hex 32`) and assign it to the JWT_SECRET_KEY environment variable."
            )
        if len(secret) < 32:
            raise RuntimeError(
                f"CRITICAL SECURITY CONFIGURATION ERROR: JWT_SECRET_KEY is only {len(secret)} characters long. "
                "Production requires at least 32 characters (256 bits) for HMAC-SHA256 signing security."
            )
        logger.info("Production JWT security configuration validated successfully.")
    else:
        if secret == DEFAULT_DEV_JWT_SECRET:
            logger.warning(
                "Running with default development JWT secret key. "
                "Ensure JWT_SECRET_KEY is set to a secure secret before deploying to production."
            )
    return True


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt with standard salt rounds."""
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify that a plaintext password matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as exc:
        logger.warning(f"Password verification encountered error: {exc}")
        return False


def create_access_token(
    subject: str,
    role: str = "patient",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token containing subject ID, role, and expiration."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token.

    Raises:
        HTTPException: If token is expired, invalid, or signature verification fails.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency requiring an authenticated user with a valid Bearer token."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer token in Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: missing subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with token was not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """FastAPI dependency for endpoints that support both authenticated and anonymous access."""
    if not token:
        return None

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    except Exception:
        return None


def verify_report_access(record: Any, current_user: Optional[User]) -> None:
    """Enforce strict authorization and prevent Insecure Direct Object References (IDOR).

    Guarantees tenant isolation: patients can only access their own reports,
    while administrative users can access any report for auditing.
    """
    record_user_id = getattr(record, "user_id", None)
    if not record_user_id:
        return

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access this protected patient report.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if current_user.role != "admin" and current_user.id != record_user_id:
        from src.security.audit import SecurityAuditLogger
        SecurityAuditLogger.get_instance().log_event(
            event_type="IDOR_ATTEMPT_BLOCKED",
            actor_id=current_user.id,
            resource_id=getattr(record, "job_id", getattr(record, "id", "unknown")),
            details={"owner_user_id": record_user_id, "role": current_user.role},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to access or modify this clinical report.",
        )
