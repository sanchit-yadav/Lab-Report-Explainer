"""Authentication API endpoints: registration, login, and user profile management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_and_migrate_password,
)
from src.api.models import TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse
from src.db.models import User
from src.db.session import get_db
from src.security.audit import SecurityAuditLogger
from src.security.rate_limiter import SlidingWindowRateLimiter

logger = logging.getLogger("auth_routes")

# 10 login attempts per minute per IP to protect against credential stuffing
login_rate_limiter = SlidingWindowRateLimiter(times=10, seconds=60, name="login")

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & User Management"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New User Account",
)
def register(
    req: UserRegisterRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Register a new user account, encrypt password, and return JWT Bearer token."""
    normalized_email = req.email.lower().strip()
    existing_user = db.query(User).filter(User.email == normalized_email).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    hashed_pw = hash_password(req.password)
    user = User(
        email=normalized_email,
        hashed_password=hashed_pw,
        full_name=req.full_name.strip() if req.full_name else None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    SecurityAuditLogger.get_instance().log_event(
        event_type="USER_REGISTERED",
        actor_id=user.id,
        resource_id=user.id,
        details={"email": user.email},
    )

    token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate User and Obtain JWT Token",
    dependencies=[Depends(login_rate_limiter)],
)
def login(
    req: UserLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email and password to receive a JWT Bearer token."""
    normalized_email = req.email.lower().strip()
    user = db.query(User).filter(User.email == normalized_email).first()

    audit = SecurityAuditLogger.get_instance()

    is_valid = False
    needs_rehash = False
    upgraded_hash = None
    if user:
        is_valid, needs_rehash, upgraded_hash = verify_and_migrate_password(
            req.password,
            user.hashed_password,
        )

    if not user or not is_valid:
        audit.log_event(
            event_type="LOGIN_FAILED",
            actor_id="anonymous",
            resource_id=normalized_email,
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Safe zero-downtime migration: rehash legacy password schemes to modern bcrypt
    if needs_rehash and upgraded_hash:
        user.hashed_password = upgraded_hash
        db.commit()
        db.refresh(user)
        logger.info(f"User '{user.id}' password hash upgraded to standard bcrypt upon successful authentication.")

    if not user.is_active:
        audit.log_event(
            event_type="LOGIN_FAILED",
            actor_id=user.id,
            resource_id=user.id,
            details={"reason": "account_deactivated"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact support.",
        )

    audit.log_event(
        event_type="LOGIN_SUCCESS",
        actor_id=user.id,
        resource_id=user.id,
        details={"email": user.email},
    )

    token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current Authenticated User Profile",
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return profile metadata for the currently authenticated user."""
    return UserResponse.model_validate(current_user)
