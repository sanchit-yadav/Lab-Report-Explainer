"""Schemas for generated clinical explanations and structured report summaries."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from src.extraction.schema import FlagStatus


class TestExplanation(BaseModel):
    """Bilingual, patient-centered explanation for a single lab test result."""
    __test__ = False
    test_name: str = Field(description="Name of the laboratory test")
    flag: FlagStatus = Field(description="Assigned categorical flag status")
    explanation_en: str = Field(description="Clear, everyday English explanation of the test and result")
    explanation_hi: str = Field(description="Natural, empathetic Hindi explanation of the test and result")
    source_urls: List[str] = Field(default_factory=list, description="Verified source URLs cited")
    doctor_questions: List[str] = Field(
        default_factory=list,
        description="2-3 specific, constructive questions for the patient to ask their physician",
    )
    disclaimer: str = Field(
        default="⚠️ This is an educational explanation, not a medical diagnosis. Please discuss with your doctor.",
        description="Mandatory medical disclaimer",
    )


class ReportExplanation(BaseModel):
    """Comprehensive structured explanation for an entire laboratory report."""
    __test__ = False
    patient_name: Optional[str] = None
    report_date: Optional[str] = None
    report_summary_en: str = Field(description="Overview summary in English")
    report_summary_hi: str = Field(description="Overview summary in Hindi")
    test_explanations: List[TestExplanation] = Field(default_factory=list)
    flagged_count: int = Field(default=0, description="Number of abnormal or out-of-range tests")
    total_tests: int = Field(default=0, description="Total tests processed")
    disclaimer: str = Field(
        default="⚠️ This explanation is for educational purposes only and is not a medical diagnosis. Please discuss all results with your doctor.",
        description="Global medical disclaimer",
    )
