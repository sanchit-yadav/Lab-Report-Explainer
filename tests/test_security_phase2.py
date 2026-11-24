"""Tests for Phase 2: Production Secrets, Security Hardening, Rate Limiting, and DB Pooling."""

from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from src.api.auth import DEFAULT_DEV_JWT_SECRET, validate_jwt_security
from src.db.session import check_db_connection
from src.health import run_health_check
from src.security.rate_limiter import SlidingWindowRateLimiter


def test_validate_jwt_security_rejects_default_in_production(monkeypatch):
    """Enforce that default dev JWT secret cannot be used in production."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", DEFAULT_DEV_JWT_SECRET)

    with pytest.raises(RuntimeError) as exc_info:
        validate_jwt_security()
    assert "default development JWT_SECRET_KEY is being used in a production environment" in str(exc_info.value)


def test_validate_jwt_security_rejects_short_key_in_production(monkeypatch):
    """Enforce that short secret key (< 32 chars) cannot be used in production."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "weak-short-key-123")

    with pytest.raises(RuntimeError) as exc_info:
        validate_jwt_security()
    assert "at least 32 characters" in str(exc_info.value)


def test_validate_jwt_security_accepts_strong_key_in_production(monkeypatch):
    """Enforce that 32+ character custom secret passes in production."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "custom-super-secret-key-32-chars-long-xyz-987654")

    assert validate_jwt_security() is True


def test_validate_jwt_security_allows_default_in_dev(monkeypatch):
    """Development environment permits default secret with a warning."""
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", DEFAULT_DEV_JWT_SECRET)

    assert validate_jwt_security() is True


def test_sliding_window_rate_limiter_allows_under_limit(monkeypatch):
    """Requests under limit pass successfully."""
    monkeypatch.delenv("DISABLE_RATE_LIMITING", raising=False)
    limiter = SlidingWindowRateLimiter(times=3, seconds=10, name="test_limiter")

    mock_request = MagicMock()
    mock_request.headers.get.return_value = None
    mock_request.client.host = "192.168.1.100"

    # 3 requests should all pass
    for _ in range(3):
        limiter(mock_request)


def test_sliding_window_rate_limiter_blocks_over_limit(monkeypatch):
    """Requests exceeding limit raise HTTP 429 with Retry-After header."""
    monkeypatch.delenv("DISABLE_RATE_LIMITING", raising=False)
    limiter = SlidingWindowRateLimiter(times=2, seconds=10, name="test_limiter")

    mock_request = MagicMock()
    mock_request.headers.get.return_value = None
    mock_request.client.host = "10.0.0.50"

    limiter(mock_request)
    limiter(mock_request)

    # 3rd request must be blocked with HTTP 429
    with pytest.raises(HTTPException) as exc_info:
        limiter(mock_request)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
    assert int(exc_info.value.headers["Retry-After"]) > 0


def test_rate_limiter_extracts_x_forwarded_for(monkeypatch):
    """Rate limiter accurately extracts original client IP from proxy headers."""
    monkeypatch.delenv("DISABLE_RATE_LIMITING", raising=False)
    limiter = SlidingWindowRateLimiter(times=1, seconds=10, name="proxy_test")

    req_proxy = MagicMock()
    req_proxy.headers.get.return_value = "203.0.113.195, 70.41.3.18, 150.172.238.178"

    limiter(req_proxy)

    # 2nd request from same forwarded IP should block
    with pytest.raises(HTTPException) as exc_info:
        limiter(req_proxy)
    assert exc_info.value.status_code == 429


def test_rate_limiter_toggle_bypass(monkeypatch):
    """DISABLE_RATE_LIMITING environment toggle completely disables throttling."""
    monkeypatch.setenv("DISABLE_RATE_LIMITING", "true")
    limiter = SlidingWindowRateLimiter(times=1, seconds=10, name="disabled_test")

    mock_request = MagicMock()
    mock_request.headers.get.return_value = None
    mock_request.client.host = "127.0.0.1"

    # Should not block even after 10 requests
    for _ in range(10):
        limiter(mock_request)


def test_database_connection_and_health():
    """Verify database connection probe and preflight diagnostic."""
    assert check_db_connection() is True

    health = run_health_check()
    assert health["database"]["status"] == "HEALTHY"
    assert health["database"]["dialect"] in ("sqlite", "postgresql")
