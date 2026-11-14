"""Container Health Probe and Pre-Flight System Diagnostic."""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Dict

from src.config import get_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("healthcheck")


def check_configuration() -> Dict[str, Any]:
    """Verify all YAML configs and prompt templates load without errors."""
    try:
        cfg = get_config()
        return {
            "status": "HEALTHY",
            "explanation_model": cfg.models.explanation_llm,
            "vision_fallback": cfg.models.vision_fallback,
            "languages": cfg.languages.supported,
        }
    except Exception as e:
        return {"status": "UNHEALTHY", "error": str(e)}


def check_api_credentials() -> Dict[str, Any]:
    """Check availability of required Gemini API and Langfuse credentials."""
    cfg = get_config()
    gemini_key = os.environ.get("GEMINI_API_KEY") or cfg.gemini_api_key
    langfuse_public = os.environ.get("LANGFUSE_PUBLIC_KEY") or cfg.langfuse_public_key
    langfuse_secret = os.environ.get("LANGFUSE_SECRET_KEY") or cfg.langfuse_secret_key

    return {
        "gemini_api_key_configured": bool(gemini_key),
        "langfuse_configured": bool(langfuse_public and langfuse_secret),
        "status": "HEALTHY" if gemini_key else "DEGRADED (Offline fallback only)",
    }


def check_rag_models() -> Dict[str, Any]:
    """Verify local cross-encoder and embedding dependencies."""
    cfg = get_config()
    results = {}
    try:
        from src.rag.reranker import CrossEncoderReranker
        reranker = CrossEncoderReranker(cfg.rag.reranker)
        results["cross_encoder"] = "READY"
    except Exception as e:
        results["cross_encoder"] = f"UNAVAILABLE: {e}"

    try:
        from src.rag.embeddings import EmbeddingManager
        embedder = EmbeddingManager(cfg.rag.embeddings)
        results["embedder"] = "READY"
    except Exception as e:
        results["embedder"] = f"UNAVAILABLE: {e}"

    all_ready = all(v == "READY" for v in results.values())
    results["status"] = "HEALTHY" if all_ready else "DEGRADED"
    return results


def run_preflight_diagnostic() -> bool:
    """Execute complete health assessment."""
    logger.info("Starting AI Clinical Lab Report Explainer Pre-Flight Check...")
    start_t = time.perf_counter()

    config_res = check_configuration()
    creds_res = check_api_credentials()
    rag_res = check_rag_models()

    elapsed = (time.perf_counter() - start_t) * 1000.0

    logger.info(f"1. Configuration Check: {config_res['status']}")
    logger.info(f"2. API Credentials Check: {creds_res['status']}")
    logger.info(f"3. RAG & Model Check: {rag_res['status']}")
    logger.info(f"Diagnostic completed in {elapsed:.1f}ms.")

    is_healthy = config_res["status"] == "HEALTHY"
    return is_healthy


if __name__ == "__main__":
    healthy = run_preflight_diagnostic()
    sys.exit(0 if healthy else 1)
