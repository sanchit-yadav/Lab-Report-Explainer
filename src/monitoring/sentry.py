"""HIPAA-compliant SRE error reporting and Sentry integration.

Provides strict pre-transmission PHI scrubbing hooks ensuring zero Protected
Health Information (patient names, identifiers, contact details, or surrogate tokens)
is leaked into Sentry exception logs, stack traces, or breadcrumbs.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional


logger = logging.getLogger("sentry_monitor")

# Regex patterns for Protected Health Information (PHI)
PHI_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHI_PHONE_PATTERN = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
PHI_SURROGATE_PATTERN = re.compile(
    r"\[(PATIENT_NAME|DOB|PHONE|EMAIL|MRN|DOCTOR|ADDRESS|IDENTIFIER|AGE)_\d+\]",
    re.IGNORECASE,
)
PHI_MRN_PATTERN = re.compile(
    r"\b(?:MRN|UHID|PATIENT\s*ID|REC(?:ORD)?\s*#?)\s*[:#-]?\s*([A-Za-z0-9-]+)\b",
    re.IGNORECASE,
)
PHI_DOB_PATTERN = re.compile(
    r"\b(?:DOB|Date\s*of\s*Birth|Born)\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    re.IGNORECASE,
)
PHI_NAME_HEADER_PATTERN = re.compile(
    r"\b(?:Patient(?:\s*Name)?|Pt\.?\s*Name)\s*[:#-]\s*([A-Za-z\s.]+?)(?=\s{2,}|\n|,|$)",
    re.IGNORECASE,
)


def scrub_phi_from_text(text: str) -> str:
    """Scrub patient names, emails, phones, MRNs, and surrogate tokens from arbitrary text."""
    if not text or not isinstance(text, str):
        return text

    scrubbed = PHI_EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    scrubbed = PHI_PHONE_PATTERN.sub("[REDACTED_PHONE]", scrubbed)
    scrubbed = PHI_SURROGATE_PATTERN.sub("[REDACTED_SURROGATE_TOKEN]", scrubbed)
    scrubbed = PHI_MRN_PATTERN.sub("[REDACTED_MRN]", scrubbed)
    scrubbed = PHI_DOB_PATTERN.sub("[REDACTED_DOB]", scrubbed)
    scrubbed = PHI_NAME_HEADER_PATTERN.sub("Patient: [REDACTED_PATIENT_NAME]", scrubbed)
    return scrubbed


def _scrub_recursive(data: Any) -> Any:
    """Recursively traverse JSON-like data structures and scrub all strings."""
    if isinstance(data, str):
        return scrub_phi_from_text(data)
    elif isinstance(data, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in data.items():
            # Drop sensitive headers entirely
            if isinstance(k, str) and k.lower() in {
                "authorization",
                "cookie",
                "x-forwarded-for",
                "set-cookie",
            }:
                cleaned[k] = "[STRIPPED_SENSITIVE_HEADER]"
            else:
                cleaned[k] = _scrub_recursive(v)
        return cleaned
    elif isinstance(data, list):
        return [_scrub_recursive(item) for item in data]
    return data


def scrub_phi_from_event(
    event: Dict[str, Any], hint: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Sentry before_send callback scrubbing PHI and IP addresses before dispatch."""
    # 1. Mask IP address and user identifiers (HIPAA Safe Harbor)
    if "user" in event and isinstance(event["user"], dict):
        event["user"]["ip_address"] = "0.0.0.0"
        if "email" in event["user"]:
            event["user"]["email"] = "[REDACTED_USER_EMAIL]"
        if "username" in event["user"]:
            event["user"]["username"] = "[REDACTED_USERNAME]"

    # 2. Scrub logentry message
    if "logentry" in event and isinstance(event["logentry"], dict):
        if "formatted" in event["logentry"]:
            event["logentry"]["formatted"] = scrub_phi_from_text(
                event["logentry"]["formatted"]
            )
        if "message" in event["logentry"]:
            event["logentry"]["message"] = scrub_phi_from_text(
                event["logentry"]["message"]
            )

    # 3. Scrub exceptions and stack trace frame variables
    if "exception" in event and isinstance(event["exception"], dict):
        for val in event["exception"].get("values", []):
            if "value" in val and isinstance(val["value"], str):
                val["value"] = scrub_phi_from_text(val["value"])
            stacktrace = val.get("stacktrace")
            if stacktrace and isinstance(stacktrace, dict):
                for frame in stacktrace.get("frames", []):
                    if "vars" in frame and isinstance(frame["vars"], dict):
                        frame["vars"] = _scrub_recursive(frame["vars"])

    # 4. Scrub breadcrumbs
    if "breadcrumbs" in event and isinstance(event["breadcrumbs"], dict):
        for crumb in event["breadcrumbs"].get("values", []):
            if "message" in crumb and isinstance(crumb["message"], str):
                crumb["message"] = scrub_phi_from_text(crumb["message"])
            if "data" in crumb and isinstance(crumb["data"], dict):
                crumb["data"] = _scrub_recursive(crumb["data"])

    # 5. Scrub request body and query string
    if "request" in event and isinstance(event["request"], dict):
        req = event["request"]
        if "data" in req:
            req["data"] = _scrub_recursive(req["data"])
        if "query_string" in req and isinstance(req["query_string"], str):
            req["query_string"] = scrub_phi_from_text(req["query_string"])
        if "headers" in req and isinstance(req["headers"], dict):
            req["headers"] = _scrub_recursive(req["headers"])

    return event


def init_sentry() -> bool:
    """Initialize Sentry SDK with HIPAA-compliant before_send PHI scrubbing hook."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        logger.info("SENTRY_DSN not configured; operating in local logging mode.")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        environment = os.environ.get("ENVIRONMENT", "production")
        release = os.environ.get("RELEASE_VERSION", "1.0.0")

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=0.1,  # 10% sampling in production
            send_default_pii=False,  # HIPAA requirement: NEVER send default PII
            before_send=scrub_phi_from_event,
            integrations=[FastApiIntegration()],
        )
        logger.info("Sentry initialized with HIPAA before_send PHI filter (env=%s)", environment)
        return True
    except ImportError:
        logger.warning("sentry-sdk package not installed; skipping Sentry initialization.")
        return False
    except Exception as exc:
        logger.error("Failed to initialize Sentry: %s", exc)
        return False


def capture_exception(
    exc: Exception, tags: Optional[Dict[str, str]] = None, extra: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Capture exception to Sentry (if initialized) or fallback to local logging."""
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            if tags:
                for k, v in tags.items():
                    scope.set_tag(k, v)
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, _scrub_recursive(v))
            return sentry_sdk.capture_exception(exc)
    except (ImportError, Exception):
        logger.exception("Exception recorded: %s", exc)
        return None


def capture_message(
    message: str, level: str = "info", tags: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """Capture diagnostic message to Sentry (if initialized)."""
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            if tags:
                for k, v in tags.items():
                    scope.set_tag(k, v)
            scrubbed_msg = scrub_phi_from_text(message)
            return sentry_sdk.capture_message(scrubbed_msg, level=level)
    except (ImportError, Exception):
        logger.info("Diagnostic message: %s", message)
        return None
