"""Tier 1 PDF Extractor using pdfplumber.

Extracts tables and patient metadata from digital vector PDF lab reports.
High speed, zero API cost, and high determinism.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import BinaryIO, List, Optional, Union

import pdfplumber

from src.extraction.normalizer import (
    clean_text,
    identify_columns,
    normalize_unit,
    parse_numeric_value,
    parse_reference_range,
)
from src.extraction.schema import LabReport, TestResult


RE_PATIENT_NAME = re.compile(
    r"Patient Name:\s*([^|\n\r]+?)(?:\s+(?:Age\s*/\s*Gender|Age|Gender|Referred|Sample|ID|Status|Date)\s*:|$)",
    re.IGNORECASE,
)
RE_AGE_GENDER = re.compile(r"Age\s*(?:/\s*Gender)?:\s*([^|\n\r]+?)(?:\s+(?:Referred|Sample|ID|Status|Date):|$)", re.IGNORECASE)
RE_COLLECTION_DATE = re.compile(r"(?:Collection Date|Date):\s*([^|\n\r]+?)(?:\s+(?:Referred|Sample|ID|Status):|$)", re.IGNORECASE)
RE_LAB_NAME = re.compile(r"^(.*?)(?:Technologies|Diagnostics|PathLabs|Healthcare|Lab|Pathology)", re.IGNORECASE)


class PDFPlumberExtractor:
    """Extracts structured lab reports using pdfplumber."""

    def __init__(self):
        self.tier_id = 1

    def extract(self, pdf_source: Union[str, Path, bytes, BinaryIO]) -> LabReport:
        """Parse a PDF document and return a validated LabReport instance."""
        if isinstance(pdf_source, (str, Path)):
            pdf_file = pdfplumber.open(str(pdf_source))
        elif isinstance(pdf_source, bytes):
            pdf_file = pdfplumber.open(io.BytesIO(pdf_source))
        else:
            pdf_file = pdfplumber.open(pdf_source)

        patient_name: Optional[str] = None
        patient_age: Optional[str] = None
        patient_gender: Optional[str] = None
        report_date: Optional[str] = None
        lab_name: Optional[str] = None
        tests: List[TestResult] = []

        with pdf_file:
            # 1. Extract metadata from text across pages
            all_text_lines: List[str] = []
            for page in pdf_file.pages:
                page_text = page.extract_text() or ""
                all_text_lines.extend(page_text.splitlines())

            full_text = "\n".join(all_text_lines)
            
            # Patient Name
            m_name = RE_PATIENT_NAME.search(full_text)
            if m_name:
                patient_name = clean_text(m_name.group(1))

            # Age / Gender
            m_ag = RE_AGE_GENDER.search(full_text)
            if m_ag:
                raw_ag = clean_text(m_ag.group(1))
                if "/" in raw_ag:
                    parts = raw_ag.split("/", 1)
                    patient_age = clean_text(parts[0])
                    patient_gender = clean_text(parts[1])
                else:
                    patient_age = raw_ag

            # Collection Date
            m_date = RE_COLLECTION_DATE.search(full_text)
            if m_date:
                report_date = clean_text(m_date.group(1))

            # Lab Name (first non-empty line usually has the lab name)
            for line in all_text_lines:
                cl = clean_text(line)
                if cl and any(k in cl.lower() for k in ["ltd", "diagnostics", "pathlabs", "healthcare", "lab"]):
                    lab_name = cl
                    break

            # 2. Extract structured test tables from all pages
            for page in pdf_file.pages:
                tables = page.extract_tables()
                if not tables:
                    continue

                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    header_idx = -1
                    col_map = {}

                    # Locate the header row
                    for r_idx, row in enumerate(table[:3]):
                        candidate_map = identify_columns(row)
                        if "test_name" in candidate_map and "value" in candidate_map:
                            header_idx = r_idx
                            col_map = candidate_map
                            break

                    if header_idx == -1:
                        continue

                    # Process table rows following the header
                    for row in table[header_idx + 1:]:
                        if not row or all(c is None or clean_text(c) == "" for c in row):
                            continue

                        # Extract test name
                        t_col = col_map.get("test_name", 0)
                        raw_test_name = clean_text(row[t_col]) if t_col < len(row) else ""
                        if not raw_test_name or raw_test_name.lower().startswith("patient name"):
                            continue

                        # Extract value
                        v_col = col_map.get("value", 1)
                        raw_val = clean_text(row[v_col]) if v_col < len(row) else ""
                        if not raw_val:
                            continue

                        # Extract unit
                        raw_unit = ""
                        if "unit" in col_map and col_map["unit"] < len(row):
                            raw_unit = clean_text(row[col_map["unit"]])

                        # Extract reference range
                        raw_range = ""
                        if "ref_range" in col_map and col_map["ref_range"] < len(row):
                            raw_range = clean_text(row[col_map["ref_range"]])

                        # Normalization
                        numeric_val = parse_numeric_value(raw_val)
                        norm_unit = normalize_unit(raw_unit)
                        ref_low, ref_high = parse_reference_range(raw_range)

                        tests.append(
                            TestResult(
                                test_name=raw_test_name,
                                value=numeric_val,
                                raw_value=raw_val,
                                unit=norm_unit,
                                ref_low=ref_low,
                                ref_high=ref_high,
                                ref_raw=raw_range,
                                extraction_tier=self.tier_id,
                            )
                        )

        return LabReport(
            patient_name=patient_name,
            patient_age=patient_age,
            patient_gender=patient_gender,
            report_date=report_date,
            lab_name=lab_name,
            report_type="blood_test",
            tests=tests,
            extraction_method="pdfplumber",
        )
