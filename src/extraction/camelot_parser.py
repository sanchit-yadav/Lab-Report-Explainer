"""Tier 2 PDF Extractor using camelot-py.

Fallback for complex borders, boxed tables, and multi-line cell borders.
Supports both lattice and stream table extraction algorithms.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import BinaryIO, List, Optional, Union

import camelot

from src.extraction.normalizer import (
    clean_text,
    identify_columns,
    normalize_unit,
    parse_numeric_value,
    parse_reference_range,
)
from src.extraction.schema import LabReport, TestResult


class CamelotExtractor:
    """Extracts structured lab reports using Camelot."""

    def __init__(self, method: str = "lattice"):
        self.tier_id = 2
        self.method = method  # "lattice" or "stream"

    def extract(self, pdf_source: Union[str, Path, bytes, BinaryIO]) -> LabReport:
        """Parse a PDF document using Camelot and return a LabReport."""
        temp_file = None
        if isinstance(pdf_source, (str, Path)):
            pdf_path = str(pdf_source)
        else:
            # Camelot requires a filesystem path, so write bytes to a temp file
            data = pdf_source if isinstance(pdf_source, bytes) else pdf_source.read()
            temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            temp_file.write(data)
            temp_file.close()
            pdf_path = temp_file.name

        try:
            # 1. Attempt primary method (lattice or configured method)
            tables = camelot.read_pdf(pdf_path, pages="all", flavor=self.method)
            
            # If lattice yielded no tables, try stream as fallback
            if len(tables) == 0 and self.method == "lattice":
                tables = camelot.read_pdf(pdf_path, pages="all", flavor="stream")

            tests: List[TestResult] = []

            for table in tables:
                df = table.df
                if df.empty or len(df) < 2:
                    continue

                raw_rows = df.values.tolist()
                header_idx = -1
                col_map = {}

                for r_idx, row in enumerate(raw_rows[:3]):
                    candidate_map = identify_columns([str(c) for c in row])
                    if "test_name" in candidate_map and "value" in candidate_map:
                        header_idx = r_idx
                        col_map = candidate_map
                        break

                if header_idx == -1:
                    continue

                for row in raw_rows[header_idx + 1:]:
                    if not row or all(clean_text(c) == "" for c in row):
                        continue

                    t_col = col_map.get("test_name", 0)
                    raw_test_name = clean_text(row[t_col]) if t_col < len(row) else ""
                    if not raw_test_name:
                        continue

                    v_col = col_map.get("value", 1)
                    raw_val = clean_text(row[v_col]) if v_col < len(row) else ""
                    if not raw_val:
                        continue

                    raw_unit = ""
                    if "unit" in col_map and col_map["unit"] < len(row):
                        raw_unit = clean_text(row[col_map["unit"]])

                    raw_range = ""
                    if "ref_range" in col_map and col_map["ref_range"] < len(row):
                        raw_range = clean_text(row[col_map["ref_range"]])

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
                report_type="blood_test",
                tests=tests,
                extraction_method=f"camelot_{self.method}",
            )
        finally:
            if temp_file:
                try:
                    Path(temp_file.name).unlink(missing_ok=True)
                except Exception:
                    pass
