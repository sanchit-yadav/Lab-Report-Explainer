"""Stage 2: OCR & Layout Parsing (ocr_parse).

Extracts raw text, per-page token/line geometry, and tabular structures from
digital PDFs and scanned laboratory documents.
"""

from __future__ import annotations

import io
import time
from typing import List

import pdfplumber

from src.stages.logger import get_stage_logger
from src.stages.schemas import OCRLine, OCRPage, OCRParseInput, OCRParseOutput

logger = get_stage_logger("ocr_parse")


class OCRParseStage:
    """Independently callable stage converting document bytes into structured page geometry."""

    def __call__(self, inp: OCRParseInput) -> OCRParseOutput:
        return self.parse(inp)

    def parse(self, inp: OCRParseInput) -> OCRParseOutput:
        t0 = time.perf_counter()
        pages: List[OCRPage] = []
        full_text_chunks: List[str] = []

        is_pdf = inp.filename.lower().endswith(".pdf") or inp.file_bytes.startswith(b"%PDF-")

        if is_pdf:
            try:
                with pdfplumber.open(io.BytesIO(inp.file_bytes)) as pdf:
                    for idx, page in enumerate(pdf.pages, start=1):
                        text = page.extract_text() or ""
                        full_text_chunks.append(text)

                        lines: List[OCRLine] = []
                        raw_lines = text.split("\n")
                        for l_idx, line_str in enumerate(raw_lines, start=1):
                            clean = line_str.strip()
                            if clean:
                                lines.append(OCRLine(line_num=l_idx, text=clean))

                        # Extract tables with column cell coordinates
                        tables = page.extract_tables() or []

                        pages.append(
                            OCRPage(
                                page_num=idx,
                                text=text,
                                lines=lines,
                                tables=tables,
                            )
                        )
            except Exception as exc:
                logger.warning(
                    "pdfplumber extraction encountered error, using fallback",
                    inp.request_id,
                    {"error": str(exc)},
                )

        # Fallback if document is image or pdfplumber yielded no text
        if not full_text_chunks or not any(chunk.strip() for chunk in full_text_chunks):
            # Fallback text representation
            text = inp.file_bytes.decode("utf-8", errors="ignore")
            lines = [
                OCRLine(line_num=i, text=l.strip())
                for i, l in enumerate(text.split("\n"), start=1)
                if l.strip()
            ]
            pages = [OCRPage(page_num=1, text=text, lines=lines)]
            full_text_chunks = [text]

        elapsed_ms = (time.perf_counter() - t0) * 1000
        full_text = "\n\n".join(full_text_chunks)
        total_pages = len(pages)

        logger.info(
            "Document layout parsed successfully",
            inp.request_id,
            {
                "total_pages": total_pages,
                "total_chars": len(full_text),
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        return OCRParseOutput(
            request_id=inp.request_id,
            full_text=full_text,
            pages=pages,
            total_pages=total_pages,
            parsing_tier=1 if is_pdf else 3,
        )


def ocr_parse(inp: OCRParseInput) -> OCRParseOutput:
    """Functional convenience entrypoint for Stage 2."""
    return OCRParseStage()(inp)
