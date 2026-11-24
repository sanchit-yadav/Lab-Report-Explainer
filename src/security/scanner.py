"""Pre-analytical file security scanner detecting PDF exploits, macros, and malformed files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger("security.scanner")


@dataclass
class SecurityScanResult:
    """Security assessment result for an uploaded document."""

    is_safe: bool
    threat_type: Optional[str] = None
    details: str = "Document passed all security checks."
    risk_score: int = 0  # 0 (safe) to 100 (critical threat)


class FileSecurityScanner:
    """Scans incoming PDF and image documents before parsing to prevent exploits."""

    # Disallowed binary executable magic signatures
    EXECUTABLE_SIGNATURES = [
        (b"MZ", "Windows PE Executable / DLL"),
        (b"\x7fELF", "Linux ELF Executable"),
        (b"\xca\xfe\xba\xbe", "Java Bytecode / Mach-O Binary"),
        (b"PK\x03\x04", "Encapsulated Zip / Archive"),  # Disallow raw zip archives uploaded as pdf
        (b"Rar!\x1a\x07", "Rar Archive"),
        (b"7z\xbc\xaf\x27\x1c", "7-Zip Archive"),
    ]

    # Malicious PDF exploitation keywords and actions
    SUSPICIOUS_PDF_PATTERNS = [
        (re.compile(rb"/JavaScript\b", re.IGNORECASE), "Embedded PDF JavaScript (/JavaScript)", 80),
        (re.compile(rb"/JS\b", re.IGNORECASE), "Embedded PDF JavaScript (/JS)", 80),
        (
            re.compile(rb"/Launch\b", re.IGNORECASE),
            "Arbitrary Process Launch Action (/Launch)",
            100,
        ),
        (
            re.compile(rb"/EmbeddedFiles\b", re.IGNORECASE),
            "Embedded Binary Attachment (/EmbeddedFiles)",
            70,
        ),
        (
            re.compile(rb"/RichMedia\b", re.IGNORECASE),
            "Embedded Flash / RichMedia Action (/RichMedia)",
            90,
        ),
    ]

    def __init__(self, max_file_size_bytes: int = 50 * 1024 * 1024):
        self.max_file_size_bytes = max_file_size_bytes

    def scan_bytes(self, content: bytes, filename: str = "upload.pdf") -> SecurityScanResult:
        """Scan raw document bytes for malware, exploits, and format violations."""
        file_size = len(content)

        # 1. Size Verification
        if file_size == 0:
            return SecurityScanResult(
                is_safe=False,
                threat_type="EMPTY_FILE",
                details="Uploaded document is empty (0 bytes).",
                risk_score=100,
            )

        if file_size > self.max_file_size_bytes:
            return SecurityScanResult(
                is_safe=False,
                threat_type="FILE_TOO_LARGE",
                details=f"Document exceeds size limit of {self.max_file_size_bytes / (1024 * 1024)}MB.",
                risk_score=80,
            )

        file_ext = Path(filename).suffix.lower()

        # 2. Executable Signature Detection
        for magic, desc in self.EXECUTABLE_SIGNATURES:
            if content.startswith(magic):
                # Allow PK if someone uploaded OpenDocument or docx, but for lab reports we strictly want PDF/Image
                logger.warning(f"Intercepted executable payload disguised as {filename}: {desc}")
                return SecurityScanResult(
                    is_safe=False,
                    threat_type="EXECUTABLE_PAYLOAD",
                    details=f"File contains disallowed binary header: {desc}.",
                    risk_score=100,
                )

        # 3. Format Magic Byte Validation
        if file_ext == ".pdf":
            # PDF must contain %PDF- in the first 1024 bytes
            if b"%PDF-" not in content[:1024]:
                return SecurityScanResult(
                    is_safe=False,
                    threat_type="INVALID_PDF_HEADER",
                    details="File claims to be a PDF but lacks valid %PDF- magic header.",
                    risk_score=90,
                )

            # 4. Deep Inspection of PDF Stream Objects for Exploits
            for pattern, threat_desc, score in self.SUSPICIOUS_PDF_PATTERNS:
                if pattern.search(content):
                    logger.warning(f"Intercepted active exploit in PDF '{filename}': {threat_desc}")
                    return SecurityScanResult(
                        is_safe=False,
                        threat_type="ACTIVE_EXPLOIT_DETECTED",
                        details=f"Malicious active content detected in PDF: {threat_desc}.",
                        risk_score=score,
                    )

            # Check for excessive object count (decompression bomb / DoS attempt)
            obj_count = len(re.findall(rb"\b\d+\s+\d+\s+obj\b", content))
            if obj_count > 30000:
                return SecurityScanResult(
                    is_safe=False,
                    threat_type="PDF_BOMB",
                    details=f"Excessive object count ({obj_count}) indicates a potential decompression bomb.",
                    risk_score=95,
                )

        elif file_ext in {".png", ".jpg", ".jpeg", ".webp"}:
            is_valid_img = (
                content.startswith(b"\x89PNG\r\n\x1a\n")  # PNG
                or content.startswith(b"\xff\xd8\xff")  # JPEG
                or (content.startswith(b"RIFF") and b"WEBP" in content[:16])  # WebP
            )
            if not is_valid_img:
                return SecurityScanResult(
                    is_safe=False,
                    threat_type="CORRUPT_OR_DISGUISED_IMAGE",
                    details=f"File extension '{file_ext}' does not match valid image header bytes.",
                    risk_score=85,
                )

        return SecurityScanResult(
            is_safe=True,
            threat_type=None,
            details="Document passed pre-analytical security analysis.",
            risk_score=0,
        )

    def scan_file(self, file_path: Union[str, Path]) -> SecurityScanResult:
        """Scan a document file on disk."""
        path = Path(file_path)
        if not path.exists():
            return SecurityScanResult(
                is_safe=False,
                threat_type="FILE_NOT_FOUND",
                details=f"File '{path}' does not exist.",
                risk_score=100,
            )

        content = path.read_bytes()
        return self.scan_bytes(content, filename=path.name)
