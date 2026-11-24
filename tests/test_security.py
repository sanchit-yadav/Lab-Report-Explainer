"""Unit tests for pre-analytical threat scanner and HIPAA cryptographic audit log."""

from __future__ import annotations

import pytest

from src.security.audit import GENESIS_HASH, SecurityAuditLogger
from src.security.scanner import FileSecurityScanner


@pytest.fixture
def scanner():
    return FileSecurityScanner()


@pytest.fixture
def clean_audit_logger(tmp_path):
    log_file = tmp_path / "test_audit.jsonl"
    audit = SecurityAuditLogger(log_file_path=log_file)
    audit.clear()
    return audit


# ------------------------------------------------------------------------------
# 1. FileSecurityScanner Tests
# ------------------------------------------------------------------------------

def test_scanner_allows_clean_pdf(scanner):
    """Valid PDF without active scripts passes scan."""
    clean_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF"
    res = scanner.scan_bytes(clean_pdf, "clean_report.pdf")
    assert res.is_safe is True
    assert res.threat_type is None
    assert res.risk_score == 0


def test_scanner_rejects_empty_file(scanner):
    """Empty files are rejected."""
    res = scanner.scan_bytes(b"", "empty.pdf")
    assert res.is_safe is False
    assert res.threat_type == "EMPTY_FILE"


def test_scanner_rejects_executable_disguised_as_pdf(scanner):
    """Windows PE (.exe) disguised as .pdf is intercepted by magic bytes."""
    malicious_bytes = b"MZ\x90\x00\x03\x00\x00\x00%PDF-1.4"
    res = scanner.scan_bytes(malicious_bytes, "report.pdf")
    assert res.is_safe is False
    assert res.threat_type == "EXECUTABLE_PAYLOAD"


def test_scanner_rejects_embedded_javascript(scanner):
    """PDF containing /JavaScript stream action is rejected."""
    malicious_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Action /S /JavaScript /JS (app.alert('exploit')) >>\n"
        b"endobj\n"
    )
    res = scanner.scan_bytes(malicious_pdf, "invoice.pdf")
    assert res.is_safe is False
    assert res.threat_type == "ACTIVE_EXPLOIT_DETECTED"
    assert "/JavaScript" in res.details


def test_scanner_rejects_launch_action(scanner):
    """PDF containing /Launch process trigger is rejected."""
    malicious_pdf = (
        b"%PDF-1.4\n"
        b"2 0 obj\n"
        b"<< /Type /Action /S /Launch /F (cmd.exe) >>\n"
        b"endobj\n"
    )
    res = scanner.scan_bytes(malicious_pdf, "cbc.pdf")
    assert res.is_safe is False
    assert res.threat_type == "ACTIVE_EXPLOIT_DETECTED"
    assert "/Launch" in res.details


def test_scanner_validates_image_headers(scanner):
    """Image files must conform to magic header bytes."""
    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    res_png = scanner.scan_bytes(valid_png, "photo.png")
    assert res_png.is_safe is True

    fake_png = b"NOT_A_PNG_HEADER_DATA"
    res_fake = scanner.scan_bytes(fake_png, "photo.png")
    assert res_fake.is_safe is False
    assert res_fake.threat_type == "CORRUPT_OR_DISGUISED_IMAGE"


# ------------------------------------------------------------------------------
# 2. SecurityAuditLogger Tests (Cryptographic Merkle Chain)
# ------------------------------------------------------------------------------

def test_audit_log_genesis_and_chaining(clean_audit_logger):
    """First record links to GENESIS_HASH; subsequent records link to predecessor."""
    audit = clean_audit_logger

    r1 = audit.log_event("DOCUMENT_UPLOADED", "user_123", "hash_abc", {"filename": "cbc.pdf"})
    assert r1.previous_hash == GENESIS_HASH
    assert len(r1.entry_hash) == 64

    r2 = audit.log_event("PHI_DEIDENTIFIED", "system", "hash_abc", {"redacted": ["name"]})
    assert r2.previous_hash == r1.entry_hash

    r3 = audit.log_event("PDF_DOWNLOADED", "user_123", "job_456", {"pages": 1})
    assert r3.previous_hash == r2.entry_hash


def test_audit_log_verifies_valid_chain(clean_audit_logger):
    """Unmodified chain passes cryptographic integrity verification."""
    audit = clean_audit_logger
    for i in range(5):
        audit.log_event(f"EVENT_{i}", "actor", f"resource_{i}")

    is_valid, err = audit.verify_integrity()
    assert is_valid is True
    assert err is None


def test_audit_log_detects_tampering(clean_audit_logger):
    """Modifying any historical record in the chain triggers integrity violation."""
    audit = clean_audit_logger
    for i in range(4):
        audit.log_event(f"EVENT_{i}", "actor", f"resource_{i}")

    # Artificially tamper with record 1 in memory
    audit._chain[1].details["tampered_key"] = "malicious_change"

    is_valid, err = audit.verify_integrity()
    assert is_valid is False
    assert "Tampered record at index 1" in str(err)


def test_audit_log_query_filtering(clean_audit_logger):
    """Records can be filtered by resource_id or event_type."""
    audit = clean_audit_logger
    audit.log_event("UPLOAD", "u1", "res_A")
    audit.log_event("VIEW", "u1", "res_A")
    audit.log_event("UPLOAD", "u2", "res_B")

    records_a = audit.get_records(resource_id="res_A")
    assert len(records_a) == 2

    records_upload = audit.get_records(event_type="UPLOAD")
    assert len(records_upload) == 2
