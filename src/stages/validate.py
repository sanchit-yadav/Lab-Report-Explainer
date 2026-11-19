"""Stage 1: Document Upload Validation & Sanitization (validate_upload).

Validates file magic signatures, enforces maximum size boundaries, inspects for
embedded exploits or macros, and strips metadata prior to analytical parsing.
"""

from __future__ import annotations

import hashlib
import io
import time
from typing import Optional

from src.security.scanner import FileSecurityScanner
from src.stages.logger import get_stage_logger
from src.stages.schemas import ValidateUploadInput, ValidateUploadOutput

logger = get_stage_logger("validate_upload")

# Magic byte signatures for authorized clinical document formats
MAGIC_SIGNATURES = {
    "application/pdf": [b"%PDF-"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/webp": [b"RIFF"],
}


class ValidateUploadStage:
    """Independently callable validation stage ensuring input document hygiene."""

    def __init__(self):
        self.scanner = FileSecurityScanner()

    def __call__(self, inp: ValidateUploadInput) -> ValidateUploadOutput:
        return self.validate(inp)

    def validate(self, inp: ValidateUploadInput) -> ValidateUploadOutput:
        t0 = time.perf_counter()
        raw_bytes = inp.file_bytes
        file_size = len(raw_bytes)
        file_hash = hashlib.sha256(raw_bytes).hexdigest()

        # 1. Size constraint check
        if file_size == 0:
            logger.warning("Empty file upload rejected", inp.request_id, {"filename": inp.filename})
            return ValidateUploadOutput(
                request_id=inp.request_id,
                is_valid=False,
                file_hash=file_hash,
                filename=inp.filename,
                file_size_bytes=0,
                mime_type="unknown",
                sanitized_bytes=b"",
                error="Uploaded file is empty (0 bytes).",
            )

        if file_size > inp.max_file_size_bytes:
            max_mb = inp.max_file_size_bytes / (1024 * 1024)
            logger.warning(
                "File size limit exceeded",
                inp.request_id,
                {"size_bytes": file_size, "limit_mb": max_mb},
            )
            return ValidateUploadOutput(
                request_id=inp.request_id,
                is_valid=False,
                file_hash=file_hash,
                filename=inp.filename,
                file_size_bytes=file_size,
                mime_type="unknown",
                sanitized_bytes=b"",
                error=f"File exceeds maximum allowed size of {max_mb:.0f} MB.",
            )

        # 2. Magic byte signature verification
        detected_mime: Optional[str] = None
        for mime, sigs in MAGIC_SIGNATURES.items():
            if any(raw_bytes.startswith(sig) for sig in sigs):
                detected_mime = mime
                break

        # Check for webp RIFF ... WEBP header format
        if not detected_mime and raw_bytes.startswith(b"RIFF") and len(raw_bytes) > 12:
            if raw_bytes[8:12] == b"WEBP":
                detected_mime = "image/webp"

        if not detected_mime:
            logger.warning("Invalid magic byte signature", inp.request_id, {"filename": inp.filename})
            return ValidateUploadOutput(
                request_id=inp.request_id,
                is_valid=False,
                file_hash=file_hash,
                filename=inp.filename,
                file_size_bytes=file_size,
                mime_type="application/octet-stream",
                sanitized_bytes=b"",
                error="File failed magic-byte validation. Only PDF, PNG, JPG, and WebP are accepted.",
            )

        # 3. Security scan for embedded executables and macros
        scan_res = self.scanner.scan_bytes(raw_bytes, inp.filename)
        if not scan_res.is_safe:
            logger.error(
                "File security scan failed",
                inp.request_id,
                {"threat_type": scan_res.threat_type, "risk_score": scan_res.risk_score},
            )
            return ValidateUploadOutput(
                request_id=inp.request_id,
                is_valid=False,
                file_hash=file_hash,
                filename=inp.filename,
                file_size_bytes=file_size,
                mime_type=detected_mime,
                sanitized_bytes=b"",
                error=f"Security check failed: {scan_res.details}",
            )

        # 4. Metadata stripping & page count determination
        page_count: Optional[int] = None
        sanitized_bytes = raw_bytes

        if detected_mime == "application/pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
                page_count = len(reader.pages)

                # Strip PDF metadata to sanitize document
                writer = pypdf.PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                # Omit original metadata dictionary
                writer.add_metadata({})
                out_buffer = io.BytesIO()
                writer.write(out_buffer)
                sanitized_bytes = out_buffer.getvalue() or raw_bytes
            except Exception:
                # Fallback to original bytes if metadata stripping encountered warning
                sanitized_bytes = raw_bytes

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Upload validated successfully",
            inp.request_id,
            {
                "mime_type": detected_mime,
                "file_size": file_size,
                "page_count": page_count,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        return ValidateUploadOutput(
            request_id=inp.request_id,
            is_valid=True,
            file_hash=file_hash,
            filename=inp.filename,
            file_size_bytes=file_size,
            mime_type=detected_mime,
            page_count=page_count,
            sanitized_bytes=sanitized_bytes,
        )


def validate_upload(inp: ValidateUploadInput) -> ValidateUploadOutput:
    """Functional convenience entrypoint for Stage 1."""
    return ValidateUploadStage()(inp)
