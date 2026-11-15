"""Unit tests for HIPAA PHI scrubbing and Sentry monitoring hooks."""

from __future__ import annotations

from src.monitoring.sentry import (
    init_sentry,
    scrub_phi_from_event,
    scrub_phi_from_text,
)


def test_scrub_phi_from_text_patterns():
    """Verify regex scrubbing of emails, phones, MRNs, DOBs, surrogate tokens, and patient headers."""
    raw = (
        "Patient: John Doe, DOB: 05/12/1982, MRN: MRN-98421, "
        "Email: patient.test@gmail.com, Phone: +1-555-234-5678, "
        "Token: [PATIENT_NAME_1] has elevated glucose."
    )
    scrubbed = scrub_phi_from_text(raw)

    assert "John Doe" not in scrubbed
    assert "[REDACTED_PATIENT_NAME]" in scrubbed
    assert "05/12/1982" not in scrubbed
    assert "[REDACTED_DOB]" in scrubbed
    assert "MRN-98421" not in scrubbed
    assert "[REDACTED_MRN]" in scrubbed
    assert "patient.test@gmail.com" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "555-234-5678" not in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[PATIENT_NAME_1]" not in scrubbed
    assert "[REDACTED_SURROGATE_TOKEN]" in scrubbed
    assert "elevated glucose" in scrubbed


def test_scrub_phi_from_event_structure():
    """Verify deep scrubbing of Sentry event objects across user, exceptions, frames, and headers."""
    event = {
        "user": {
            "ip_address": "192.168.1.100",
            "email": "dr.smith@hospital.org",
            "username": "clinician_42",
        },
        "logentry": {
            "formatted": "Error processing report for patient.smith@gmail.com with token [PATIENT_NAME_2]",
        },
        "exception": {
            "values": [
                {
                    "value": "Failed on patient: Jane Doe with phone (555) 019-2834",
                    "stacktrace": {
                        "frames": [
                            {
                                "vars": {
                                    "patient_email": "jane.doe@sample.com",
                                    "clean_metric": 14.5,
                                }
                            }
                        ]
                    },
                }
            ]
        },
        "breadcrumbs": {
            "values": [
                {
                    "message": "User queried about MRN: 482109",
                    "data": {"query": "Tell me about patient [PATIENT_NAME_3]"},
                }
            ]
        },
        "request": {
            "headers": {
                "Authorization": "Bearer secret_jwt_token",
                "Cookie": "session_id=12345",
                "User-Agent": "Mozilla/5.0",
            },
            "query_string": "email=test@example.com",
        },
    }

    cleaned = scrub_phi_from_event(event)

    # User scrubbing
    assert cleaned["user"]["ip_address"] == "0.0.0.0"
    assert cleaned["user"]["email"] == "[REDACTED_USER_EMAIL]"

    # Logentry scrubbing
    assert "patient.smith@gmail.com" not in cleaned["logentry"]["formatted"]
    assert "[REDACTED_EMAIL]" in cleaned["logentry"]["formatted"]
    assert "[PATIENT_NAME_2]" not in cleaned["logentry"]["formatted"]

    # Exception & Frame variable scrubbing
    exc_val = cleaned["exception"]["values"][0]["value"]
    assert "(555) 019-2834" not in exc_val
    assert "[REDACTED_PHONE]" in exc_val
    frame_var = cleaned["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["patient_email"]
    assert "jane.doe@sample.com" not in frame_var
    assert "[REDACTED_EMAIL]" in frame_var
    assert cleaned["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["clean_metric"] == 14.5

    # Breadcrumb scrubbing
    assert "482109" not in cleaned["breadcrumbs"]["values"][0]["message"]
    assert "[PATIENT_NAME_3]" not in cleaned["breadcrumbs"]["values"][0]["data"]["query"]

    # Request headers scrubbing
    assert cleaned["request"]["headers"]["Authorization"] == "[STRIPPED_SENSITIVE_HEADER]"
    assert cleaned["request"]["headers"]["Cookie"] == "[STRIPPED_SENSITIVE_HEADER]"
    assert "test@example.com" not in cleaned["request"]["query_string"]


def test_init_sentry_without_dsn():
    """Verify init_sentry safely no-ops and returns False when DSN is not set."""
    assert init_sentry() is False
