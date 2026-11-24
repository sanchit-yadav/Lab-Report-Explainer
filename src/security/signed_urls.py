"""Cryptographically signed short-lived URL generator and validator.

Generates and verifies time-limited HMAC-SHA256 signatures for clinical report
assets, downloads, and sensitive file endpoints.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional, Tuple


def _get_signing_key() -> bytes:
    """Retrieve secret key for HMAC signature generation."""
    key = (
        os.environ.get("URL_SIGNING_SECRET")
        or os.environ.get("JWT_SECRET_KEY")
        or "clinical_secure_default_key_change_in_production"
    )
    return key.encode("utf-8")


def generate_signed_report_token(
    job_id: str,
    user_id: Optional[str] = None,
    ttl_seconds: int = 900,  # 15 minutes default
) -> Tuple[int, str]:
    """Generate (expires_at, signature) tuple for an authorized report asset."""
    expires_at = int(time.time()) + ttl_seconds
    uid_str = user_id or "anonymous"
    payload = f"{job_id}:{uid_str}:{expires_at}".encode("utf-8")
    signature = hmac.new(_get_signing_key(), payload, hashlib.sha256).hexdigest()
    return expires_at, signature


def verify_signed_report_token(
    job_id: str,
    user_id: Optional[str],
    expires_at: int,
    signature: str,
) -> bool:
    """Verify validity and non-expiration of signed report token."""
    # 1. Expiration check
    current_time = int(time.time())
    if current_time > expires_at:
        return False

    # 2. Signature verification with constant-time equality check
    uid_str = user_id or "anonymous"
    payload = f"{job_id}:{uid_str}:{expires_at}".encode("utf-8")
    expected_sig = hmac.new(_get_signing_key(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


def create_signed_token(
    job_id: str,
    user_id: Optional[str] = None,
    ttl_seconds: int = 900,
) -> str:
    """Create a URL-safe compact token combining expiration, user, and HMAC signature."""
    exp, sig = generate_signed_report_token(job_id, user_id, ttl_seconds)
    uid_enc = user_id or "anonymous"
    return f"{exp}.{uid_enc}.{sig}"


def verify_signed_token(token: str, job_id: str) -> bool:
    """Verify validity and non-expiration of a compact signed URL token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        exp_s, uid, sig = parts
        exp = int(exp_s)
        user_param = None if uid == "anonymous" else uid
        return verify_signed_report_token(
            job_id=job_id, user_id=user_param, expires_at=exp, signature=sig
        )
    except Exception:
        return False
