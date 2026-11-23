"""Structured, PII-safe logging utility for modular pipeline stages."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

# Regex patterns for common PII to scrub from log messages and attributes
PII_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b"), "[PHONE_REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    (re.compile(r"\b(dob|birth|born)[:\s]+[\d/.-]+\b", re.IGNORECASE), "[DOB_REDACTED]"),
]

BLOCKED_KEYS = {
    "patient_name",
    "patient_phone",
    "patient_email",
    "patient_address",
    "password",
    "hashed_password",
    "raw_password",
    "token",
    "access_token",
    "authorization",
    "api_key",
    "secret",
}


def sanitize_value(val: Any) -> Any:
    """Recursively scrub PII from dictionary, list, or string data."""
    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            if k.lower() in BLOCKED_KEYS:
                sanitized[k] = "[PII_REDACTED]"
            else:
                sanitized[k] = sanitize_value(v)
        return sanitized
    elif isinstance(val, list):
        return [sanitize_value(item) for item in val]
    elif isinstance(val, str):
        cleaned = val
        for pattern, replacement in PII_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)
        return cleaned
    return val


class StageLogger:
    """Logger wrapper enforcing request_id tracking and structured PII-scrubbed JSON logs."""

    def __init__(self, stage_name: str):
        self.stage_name = stage_name
        self.logger = logging.getLogger(f"pipeline.stage.{stage_name}")

    def _format(
        self,
        event: str,
        request_id: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload = {
            "stage": self.stage_name,
            "request_id": request_id,
            "event": event,
        }
        if extra:
            payload.update(sanitize_value(extra))
        return json.dumps(payload)

    def debug(self, event: str, request_id: str = "internal", extra: Optional[Dict[str, Any]] = None) -> None:
        self.logger.debug(self._format(event, request_id, extra))

    def info(self, event: str, request_id: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self.logger.info(self._format(event, request_id, extra))

    def warning(self, event: str, request_id: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self.logger.warning(self._format(event, request_id, extra))

    def error(self, event: str, request_id: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self.logger.error(self._format(event, request_id, extra))


def get_stage_logger(stage_name: str) -> StageLogger:
    """Return a StageLogger instance for the given pipeline stage."""
    return StageLogger(stage_name)
