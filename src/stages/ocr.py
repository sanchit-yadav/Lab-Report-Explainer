"""Stage 2: OCR & Layout Parsing (ocr_parse).

Extracts raw text, per-page token/line geometry, and tabular structures from
digital PDFs and scanned laboratory documents.
Automatically handles scanned / image-only PDFs with 300 DPI rasterization,
OpenCV preprocessing (orientation fix, deskew, noise reduction), word/line confidence
scoring, and seamless fallback to multimodal vision.
"""

from __future__ import annotations

import io
import time
from typing import List

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image

from src.extraction.preprocessing import DocumentPreprocessor
from src.stages.logger import get_stage_logger
from src.stages.schemas import OCRLine, OCRPage, OCRParseInput, OCRParseOutput

logger = get_stage_logger("ocr_parse")


class OCRParseStage:
    """Independently callable stage converting document bytes into structured page geometry."""

    def __init__(self):
        self.preprocessor = DocumentPreprocessor()

    def __call__(self, inp: OCRParseInput) -> OCRParseOutput:
        return self.parse(inp)

    def parse(self, inp: OCRParseInput) -> OCRParseOutput:
        t0 = time.perf_counter()
        pages: List[OCRPage] = []
        full_text_chunks: List[str] = []

        if inp.filename.lower().endswith(".txt"):
            text = inp.file_bytes.decode("utf-8", errors="ignore")
            lines = [
                OCRLine(line_num=i, text=line_str.strip(), confidence=1.0)
                for i, line_str in enumerate(text.split("\n"), start=1)
                if line_str.strip()
            ]
            pages = [OCRPage(page_num=1, text=text, lines=lines, confidence=1.0)]
            return OCRParseOutput(
                request_id=inp.request_id,
                full_text=text,
                pages=pages,
                total_pages=1,
                parsing_tier=1,
                confidence=1.0,
            )

        is_pdf = inp.filename.lower().endswith(".pdf") or inp.file_bytes.startswith(b"%PDF-")
        has_digital_text = False

        if is_pdf:
            try:
                with pdfplumber.open(io.BytesIO(inp.file_bytes)) as pdf:
                    extracted_pages = []
                    for idx, page in enumerate(pdf.pages, start=1):
                        text = page.extract_text() or ""
                        lines: List[OCRLine] = []
                        raw_lines = text.split("\n")
                        for l_idx, line_str in enumerate(raw_lines, start=1):
                            clean = line_str.strip()
                            if clean:
                                lines.append(OCRLine(line_num=l_idx, text=clean, confidence=1.0))

                        tables = page.extract_tables() or []
                        extracted_pages.append(
                            OCRPage(
                                page_num=idx,
                                text=text,
                                lines=lines,
                                tables=tables,
                                confidence=1.0 if lines else 0.0,
                            )
                        )

                    # Verify if document has a real text layer (not empty or just whitespace)
                    total_chars = sum(len(p.text.strip()) for p in extracted_pages)
                    if total_chars >= 30:
                        has_digital_text = True
                        pages = extracted_pages
                        full_text_chunks = [p.text for p in pages]
                        logger.info(
                            f"Digital PDF text layer detected with {total_chars} characters across {len(pages)} page(s).",
                            inp.request_id,
                        )
            except Exception as exc:
                logger.warning(
                    "pdfplumber extraction encountered error; using image rasterization fallback",
                    inp.request_id,
                    {"error": str(exc)},
                )

        # ----------------------------------------------------------------------
        # Fallback for Scanned / Image-Only PDFs and Direct Image Uploads
        # ----------------------------------------------------------------------
        vision_tests = []
        vision_patient_name = None
        vision_lab_name = None

        if not has_digital_text:
            page_images: List[Image.Image] = []
            if is_pdf:
                logger.info(
                    "Scanned / image-only PDF detected with empty text layer. Rasterizing pages at ~300 DPI.",
                    inp.request_id,
                )
                try:
                    pdf = pdfium.PdfDocument(inp.file_bytes)
                    for page_idx in range(len(pdf)):
                        # Scale 300 / 72 = 4.1667 (~300 DPI)
                        pil_img = pdf[page_idx].render(scale=300.0 / 72.0).to_pil()
                        page_images.append(pil_img)
                except Exception as exc:
                    logger.error(
                        "Failed to rasterize PDF pages", inp.request_id, {"error": str(exc)}
                    )
            else:
                try:
                    direct_img = Image.open(io.BytesIO(inp.file_bytes))
                    page_images.append(direct_img)
                except Exception as exc:
                    logger.error("Failed to open image file", inp.request_id, {"error": str(exc)})

            # Process each rasterized/scanned page
            for page_idx, raw_img in enumerate(page_images, start=1):
                clean_img, meta = self.preprocessor.preprocess(raw_img)

                ocr_lines: List[OCRLine] = []
                page_text_lines: List[str] = []
                avg_confidence = 0.0

                # 1. Check local Tesseract OCR if available
                try:
                    import pytesseract

                    data = pytesseract.image_to_data(clean_img, output_type=pytesseract.Output.DICT)
                    words = data.get("text", [])
                    confs = [float(c) for c in data.get("conf", []) if float(c) > 0]
                    if confs:
                        avg_confidence = (sum(confs) / len(confs)) / 100.0

                    line_dict = {}
                    for i, w in enumerate(words):
                        w_clean = w.strip()
                        if not w_clean:
                            continue
                        line_n = data["line_num"][i]
                        line_dict.setdefault(line_n, []).append(w_clean)

                    for l_idx, (num, w_list) in enumerate(sorted(line_dict.items()), start=1):
                        l_text = " ".join(w_list)
                        page_text_lines.append(l_text)
                        ocr_lines.append(
                            OCRLine(
                                line_num=l_idx, text=l_text, confidence=round(avg_confidence, 2)
                            )
                        )
                except Exception:
                    pass

                # 2. If local OCR confidence is low (< 0.60) or yielded no lines, fall back to Vision
                if not ocr_lines or avg_confidence < 0.60:
                    try:
                        from src.extraction.vision_parser import VisionExtractor

                        vision = VisionExtractor()
                        page_report = vision.extract_from_image(clean_img, page_idx=page_idx)

                        if page_report.tests:
                            if not vision_patient_name and page_report.patient_name:
                                vision_patient_name = page_report.patient_name
                            if not vision_lab_name and page_report.lab_name:
                                vision_lab_name = page_report.lab_name
                            vision_tests.extend(page_report.tests)

                            ocr_lines = []
                            page_text_lines = []
                            for t_idx, t in enumerate(page_report.tests, start=1):
                                ref_str = (
                                    f"({t.ref_raw})"
                                    if t.ref_raw
                                    else f"({t.ref_low} - {t.ref_high})"
                                )
                                line_str = f"{t.test_name}  {t.raw_value or t.value}  {t.unit}  {ref_str}".strip()
                                page_text_lines.append(line_str)
                                ocr_lines.append(
                                    OCRLine(
                                        line_num=t_idx,
                                        text=line_str,
                                        confidence=t.confidence,
                                    )
                                )
                            avg_confidence = sum(t.confidence for t in page_report.tests) / len(
                                page_report.tests
                            )
                    except Exception as exc:
                        logger.warning(
                            f"Vision OCR fallback warning on page {page_idx}",
                            inp.request_id,
                            {"error": str(exc)},
                        )

                page_text = "\n".join(page_text_lines)
                needs_clearer = avg_confidence < 0.20 or len(ocr_lines) == 0
                advisory = (
                    "Please upload a clearer image. The document text is unreadable or heavily degraded."
                    if needs_clearer
                    else None
                )

                pages.append(
                    OCRPage(
                        page_num=page_idx,
                        text=page_text,
                        lines=ocr_lines,
                        confidence=round(avg_confidence, 2),
                        needs_clearer_image=needs_clearer,
                        advisory=advisory,
                    )
                )
                full_text_chunks.append(page_text)

        structured_report = None
        if vision_tests:
            from src.extraction.schema import LabReport

            structured_report = LabReport(
                patient_name=vision_patient_name,
                lab_name=vision_lab_name,
                report_type="blood_test",
                tests=vision_tests,
                extraction_method="vision",
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        full_text = "\n\n".join(full_text_chunks)
        total_pages = len(pages)
        overall_conf = sum(p.confidence for p in pages) / total_pages if total_pages > 0 else 0.0
        overall_needs_clearer = any(p.needs_clearer_image for p in pages)

        logger.info(
            "Document layout parsed successfully",
            inp.request_id,
            {
                "total_pages": total_pages,
                "total_chars": len(full_text),
                "confidence": round(overall_conf, 2),
                "needs_clearer_image": overall_needs_clearer,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        return OCRParseOutput(
            request_id=inp.request_id,
            full_text=full_text,
            pages=pages,
            total_pages=total_pages,
            parsing_tier=1 if has_digital_text else 3,
            confidence=round(overall_conf, 2),
            needs_clearer_image=overall_needs_clearer,
            advisory=(
                "Please upload a clearer image. The document text is unreadable or heavily degraded."
                if overall_needs_clearer
                else None
            ),
            structured_report=structured_report,
        )


def ocr_parse(inp: OCRParseInput) -> OCRParseOutput:
    """Functional convenience entrypoint for Stage 2."""
    return OCRParseStage()(inp)
