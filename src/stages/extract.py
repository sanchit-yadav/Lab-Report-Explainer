"""Stage 3: Biomarker Value Extraction & Deterministic Flagging (extract_values).

Parses analyte observations, units, and reference ranges from OCR geometry.
Deterministically computes reference status (low, normal, high, critical) using
strict mathematical interval logic. The LLM NEVER decides clinical flags.
"""

from __future__ import annotations

import time
from typing import List, Optional

from src.config import get_config
from src.extraction.loinc_mapper import LOINCMapper
from src.extraction.router import ExtractionRouter
from src.extraction.schema import FlagStatus, LabReport
from src.flagging.demographics import DemographicIntervalEngine
from src.flagging.flagger import Flagger
from src.flagging.panic_values import PanicValueEngine
from src.stages.logger import get_stage_logger
from src.stages.schemas import (
    ExtractionOutputItem,
    ExtractValuesInput,
    ExtractValuesOutput,
)

logger = get_stage_logger("extract_values")


class ExtractValuesStage:
    """Independently callable stage extracting biomarker observations and computing deterministic flags."""

    def __init__(self):
        self.config = get_config()
        self.flagger = Flagger(self.config.extraction.flagging)
        self.panic_engine = PanicValueEngine()
        self.router = ExtractionRouter()

    def __call__(self, inp: ExtractValuesInput) -> ExtractValuesOutput:
        return self.extract(inp)

    def extract(self, inp: ExtractValuesInput) -> ExtractValuesOutput:
        t0 = time.perf_counter()
        parsed = inp.parsed_doc

        # Extract using unified multi-tier extraction router (or reuse Vision result from Stage 2)
        extracted_report: Optional[LabReport] = None
        if parsed.structured_report and parsed.structured_report.tests:
            extracted_report = parsed.structured_report
        else:
            source_payload = inp.raw_bytes if inp.raw_bytes else parsed.full_text.encode("utf-8")
            try:
                extracted_report = self.router.extract(source_payload)
            except Exception as exc:
                logger.warning(
                    "Router extraction warning, assembling from parsed pages",
                    inp.request_id,
                    {"error": str(exc)},
                )

        if not extracted_report or not extracted_report.tests:
            # Fallback to OCR parsed tables / lines from Stage 2
            from src.extraction.pdf_parser import PDFPlumberExtractor

            parser = PDFPlumberExtractor()
            fallback_tests = []
            for page in parsed.pages:
                if page.tables:
                    for tbl in page.tables:
                        fallback_tests.extend(parser.parse_table_rows(tbl))
            if not fallback_tests and parsed.full_text:
                fallback_tests = parser._extract_from_text_lines(parsed.full_text.splitlines())

            if fallback_tests:
                extracted_report = LabReport(
                    patient_name=extracted_report.patient_name
                    if extracted_report
                    else inp.patient_name_hint,
                    tests=fallback_tests,
                    extraction_method="ocr_parsed_fallback",
                )
            elif not extracted_report:
                extracted_report = LabReport(
                    patient_name=inp.patient_name_hint,
                    tests=[],
                    extraction_method="fallback",
                )

        # 1. Apply Standard Ontology Mapping (LOINC)
        extracted_report = LOINCMapper.enrich_report(extracted_report)

        # 2. Apply Demographic Interval Adjustments
        extracted_report = DemographicIntervalEngine.apply_demographic_stratification(
            extracted_report
        )

        # 3. Compute Deterministic Range Flags (Pure deterministic Python, zero LLM)
        extracted_report = self.flagger.flag_report(extracted_report)

        # 4. Map to Standard ExtractionOutputItem schema
        items: List[ExtractionOutputItem] = []
        flagged_count = 0
        critical_count = 0

        for idx, test in enumerate(extracted_report.tests, start=1):
            # Compute panic value check
            panic_alerts = self.panic_engine.evaluate([test])
            is_critical = len(panic_alerts) > 0

            flag_val = test.flag
            if is_critical:
                if flag_val == FlagStatus.LOW:
                    flag_val = FlagStatus.CRITICAL_LOW
                elif flag_val == FlagStatus.HIGH:
                    flag_val = FlagStatus.CRITICAL_HIGH
                critical_count += 1

            if flag_val not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN):
                flagged_count += 1

            # Estimate source page and line reference based on text lookup
            source_page = 1
            line_ref: Optional[str] = None
            for p in parsed.pages:
                for line in p.lines:
                    if test.test_name.lower() in line.text.lower():
                        source_page = p.page_num
                        line_ref = f"page_{p.page_num}_line_{line.line_num}"
                        break
                if line_ref:
                    break

            item = ExtractionOutputItem(
                test_name=test.test_name,
                value=test.value,
                unit=test.unit or "",
                ref_low=test.ref_low,
                ref_high=test.ref_high,
                flag=flag_val,
                source_page=getattr(test, "source_page", source_page) or source_page,
                source_location=getattr(test, "source_location", None) or line_ref or f"line_{idx}",
                source_bbox_or_line=getattr(test, "source_bbox_or_line", None)
                or line_ref
                or f"line_{idx}",
                confidence=getattr(test, "confidence", 0.95 if test.value is not None else 0.70),
                raw_value=test.raw_value or (str(test.value) if test.value is not None else ""),
                ref_raw=test.ref_raw
                or (
                    f"{test.ref_low} - {test.ref_high}"
                    if test.ref_low is not None and test.ref_high is not None
                    else ""
                ),
                loinc_code=test.loinc_code,
                loinc_name=test.loinc_name,
                category=test.category,
            )
            items.append(item)

        # 5. Evaluate Biological Plausibility and OCR Scan Fidelity
        from src.security.plausibility import PlausibilityValidator

        plaus_check = PlausibilityValidator().validate_report(items)
        if plaus_check.needs_better_upload:
            logger.warning(
                "Biological plausibility violation detected; requesting clean upload",
                inp.request_id,
                {"findings": plaus_check.implausible_findings},
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Values extracted and deterministically flagged",
            inp.request_id,
            {
                "analyte_count": len(items),
                "flagged_count": flagged_count,
                "critical_count": critical_count,
                "needs_better_upload": plaus_check.needs_better_upload,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        return ExtractValuesOutput(
            request_id=inp.request_id,
            patient_name=extracted_report.patient_name or inp.patient_name_hint,
            patient_age=extracted_report.patient_age,
            patient_gender=extracted_report.patient_gender,
            report_date=extracted_report.report_date,
            lab_name=extracted_report.lab_name,
            items=items,
            flagged_count=flagged_count,
            critical_count=critical_count,
            extraction_method=extracted_report.extraction_method,
            needs_better_upload=plaus_check.needs_better_upload,
            implausible_findings=plaus_check.implausible_findings,
            plausibility_advisory=plaus_check.advisory_message
            if plaus_check.needs_better_upload
            else None,
        )


def extract_values(inp: ExtractValuesInput) -> ExtractValuesOutput:
    """Functional convenience entrypoint for Stage 3."""
    return ExtractValuesStage()(inp)
