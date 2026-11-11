"""Pydantic schemas for extracted laboratory test results and reports."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FlagStatus(str, Enum):
    """Categorical flag assigned to a laboratory test result."""
    NORMAL = "normal"
    HIGH = "high"
    LOW = "low"
    CRITICAL_HIGH = "critical_high"
    CRITICAL_LOW = "critical_low"
    UNKNOWN = "unknown"      # Used when reference range is not provided or unparseable
    ABNORMAL = "abnormal"    # Used for non-numeric abnormal findings (e.g. 'Positive', 'Reactive')


class TestResult(BaseModel):
    """Structured representation of an individual laboratory analyte test result."""
    test_name: str = Field(description="Name or description of the lab test")
    value: Optional[float] = Field(default=None, description="Numeric result value, or None if non-numeric")
    raw_value: str = Field(default="", description="Original string value extracted from report")
    unit: str = Field(default="", description="Measurement unit (e.g. g/dL, mg/dL)")
    ref_low: Optional[float] = Field(default=None, description="Lower bound of reference range")
    ref_high: Optional[float] = Field(default=None, description="Upper bound of reference range")
    ref_raw: str = Field(default="", description="Original reference range string from report")
    flag: FlagStatus = Field(default=FlagStatus.UNKNOWN, description="Assigned flag status")
    extraction_tier: int = Field(default=1, description="Tier that extracted this record: 1, 2, or 3")


class LabReport(BaseModel):
    """Structured representation of a complete laboratory report."""
    patient_name: Optional[str] = Field(default=None, description="Patient name if present")
    patient_age: Optional[str] = Field(default=None, description="Patient age if present")
    patient_gender: Optional[str] = Field(default=None, description="Patient gender if present")
    report_date: Optional[str] = Field(default=None, description="Date of collection/reporting")
    lab_name: Optional[str] = Field(default=None, description="Diagnostic center / lab name")
    report_type: str = Field(default="blood_test", description="Type of report (e.g. blood_test, ultrasound)")
    tests: List[TestResult] = Field(default_factory=list, description="Extracted individual test results")
    extraction_method: str = Field(default="pdfplumber", description="Extractor utilized: pdfplumber | camelot | vision")
