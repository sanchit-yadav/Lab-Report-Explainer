"""Unit tests for the container health diagnostic probe."""

from src.health import (
    check_api_credentials,
    check_configuration,
    check_rag_models,
    run_preflight_diagnostic,
)


def test_health_configuration_check():
    res = check_configuration()
    assert res["status"] == "HEALTHY"
    assert "explanation_model" in res
    assert "languages" in res


def test_health_api_credentials_check():
    res = check_api_credentials()
    assert "gemini_api_key_configured" in res
    assert "langfuse_configured" in res
    assert res["status"] in ("HEALTHY", "DEGRADED (Offline fallback only)")


def test_health_rag_models_check():
    res = check_rag_models()
    assert "cross_encoder" in res
    assert "embedder" in res
    assert res["status"] in ("HEALTHY", "DEGRADED")


def test_run_preflight_diagnostic():
    is_healthy = run_preflight_diagnostic()
    assert isinstance(is_healthy, bool)
    assert is_healthy is True
