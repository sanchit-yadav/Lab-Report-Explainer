"""Longitudinal Patient History and Analyte Trend Tracker.

Extracts chronological analyte series across multiple dated laboratory reports,
calculates physiological deltas and trajectories, and generates empathetic
progress narratives.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.extraction.schema import FlagStatus, LabReport, TestResult


class TrendDirection(str, Enum):
    IMPROVING = "improving"
    WORSENING = "worsening"
    STABLE = "stable"
    FLUCTUATING = "fluctuating"


class AnalyteDataPoint(BaseModel):
    """A single chronological measurement of an analyte."""
    date_str: str = Field(description="Date string from the report")
    timestamp: float = Field(default=0.0, description="Unix timestamp for sorting")
    value: float = Field(description="Numeric analyte value")
    unit: str = Field(default="", description="Measurement unit")
    flag: FlagStatus = Field(default=FlagStatus.UNKNOWN)


class AnalyteTrend(BaseModel):
    """Historical progression of a single analyte across multiple dates."""
    test_name: str
    unit: str = ""
    data_points: List[AnalyteDataPoint] = Field(default_factory=list)
    delta_absolute: Optional[float] = None
    delta_percent: Optional[float] = None
    direction: TrendDirection = TrendDirection.STABLE
    narrative_en: str = ""
    narrative_hi: str = ""


def _parse_report_date(date_str: Optional[str]) -> Tuple[float, str]:
    """Parse various hospital report date formats into a sortable timestamp and canonical string."""
    if not date_str or not date_str.strip():
        # Fallback to current time if no date was recorded
        now = datetime.now()
        return now.timestamp(), now.strftime("%d-%b-%Y")

    cleaned = date_str.strip()
    date_formats = [
        "%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
        "%d %b %Y", "%d %B %Y", "%m/%d/%Y", "%b %d, %Y",
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.timestamp(), dt.strftime("%d-%b-%Y")
        except ValueError:
            continue

    # If unparseable, return fallback
    now = datetime.now()
    return now.timestamp(), cleaned


class HistoryTracker:
    """Manages longitudinal lab reports and analyzes chronological biomarker trajectories."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.reports: List[LabReport] = []

    def add_report(self, report: LabReport) -> None:
        """Add a lab report to the chronological patient history."""
        self.reports.append(report)
        if self.storage_dir:
            self._save_to_disk()

    def add_reports(self, reports: List[LabReport]) -> None:
        """Add multiple lab reports at once."""
        for r in reports:
            self.reports.append(r)
        if self.storage_dir:
            self._save_to_disk()

    def get_analyte_trends(self, patient_name: Optional[str] = None) -> Dict[str, AnalyteTrend]:
        """Aggregate test results into chronological trends, strictly isolated by patient identity."""
        from src.extraction.patient_matcher import group_reports_by_patient, normalize_patient_name

        # Patient isolation guard: never mix data across different patients
        target_reports = self.reports
        if patient_name:
            norm_target = normalize_patient_name(patient_name)
            target_reports = [
                r for r in self.reports
                if normalize_patient_name(r.patient_name) == norm_target
            ]
        elif self.reports:
            match_res = group_reports_by_patient(self.reports)
            if not match_res.is_single_patient:
                # Default to latest patient to prevent cross-contamination
                latest_pname = self.reports[-1].patient_name
                norm_target = normalize_patient_name(latest_pname)
                target_reports = [
                    r for r in self.reports
                    if normalize_patient_name(r.patient_name) == norm_target
                ]

        # 1. Group tests by canonical/normalized test name
        grouped: Dict[str, List[Tuple[float, str, TestResult]]] = {}

        for report in target_reports:
            t_stamp, date_formatted = _parse_report_date(report.report_date)
            for test in report.tests:
                if test.value is None or not test.test_name:
                    continue
                norm_name = test.test_name.strip()
                if norm_name not in grouped:
                    grouped[norm_name] = []
                grouped[norm_name].append((t_stamp, date_formatted, test))

        # 2. Build AnalyteTrend for each analyte
        trends: Dict[str, AnalyteTrend] = {}

        for name, records in grouped.items():
            # Sort chronologically by timestamp
            records.sort(key=lambda x: x[0])

            data_points = [
                AnalyteDataPoint(
                    date_str=r[1],
                    timestamp=r[0],
                    value=r[2].value,  # type: ignore[arg-type]
                    unit=r[2].unit,
                    flag=r[2].flag,
                )
                for r in records
            ]

            unit = data_points[0].unit if data_points else ""

            # Need at least 2 points to compute delta and trend
            if len(data_points) >= 2:
                prev_val = data_points[-2].value
                curr_val = data_points[-1].value
                delta_abs = round(curr_val - prev_val, 2)
                delta_pct = round((delta_abs / prev_val) * 100, 1) if prev_val != 0 else 0.0

                prev_flag = data_points[-2].flag
                curr_flag = data_points[-1].flag

                # Assess trend direction relative to healthy direction
                # For an elevated analyte: decreasing is improving
                # For a low analyte: increasing is improving
                if curr_flag in (FlagStatus.HIGH, FlagStatus.CRITICAL_HIGH):
                    if delta_abs < 0:
                        direction = TrendDirection.IMPROVING
                    elif delta_abs > 0:
                        direction = TrendDirection.WORSENING
                    else:
                        direction = TrendDirection.STABLE
                elif curr_flag in (FlagStatus.LOW, FlagStatus.CRITICAL_LOW):
                    if delta_abs > 0:
                        direction = TrendDirection.IMPROVING
                    elif delta_abs < 0:
                        direction = TrendDirection.WORSENING
                    else:
                        direction = TrendDirection.STABLE
                else:
                    # Current is normal
                    if prev_flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN):
                        direction = TrendDirection.IMPROVING
                    else:
                        direction = TrendDirection.STABLE

                # Generate narrative
                change_sign = "+" if delta_abs > 0 else ""
                prev_date = data_points[-2].date_str
                curr_date = data_points[-1].date_str

                if direction == TrendDirection.IMPROVING:
                    n_en = (
                        f"{name} changed by {change_sign}{delta_abs} {unit} ({change_sign}{delta_pct}%) "
                        f"from {prev_date} ({prev_val}) to {curr_date} ({curr_val}), showing positive clinical improvement."
                    )
                    n_hi = (
                        f"{name} में {prev_date} ({prev_val}) से {curr_date} ({curr_val}) तक "
                        f"{change_sign}{delta_abs} {unit} ({change_sign}{delta_pct}%) का सकारात्मक सुधार देखा गया है।"
                    )
                elif direction == TrendDirection.WORSENING:
                    n_en = (
                        f"{name} changed by {change_sign}{delta_abs} {unit} ({change_sign}{delta_pct}%) "
                        f"from {prev_date} ({prev_val}) to {curr_date} ({curr_val}), moving further from optimal range."
                    )
                    n_hi = (
                        f"{name} में {prev_date} ({prev_val}) से {curr_date} ({curr_val}) के बीच "
                        f"{change_sign}{delta_abs} {unit} ({change_sign}{delta_pct}%) का प्रतिकूल बदलाव देखा गया है।"
                    )
                else:
                    n_en = (
                        f"{name} remained stable at {curr_val} {unit} compared to {prev_date} ({prev_val} {unit})."
                    )
                    n_hi = (
                        f"{name} {prev_date} ({prev_val} {unit}) की तुलना में {curr_val} {unit} पर स्थिर बना हुआ है।"
                    )

                trends[name] = AnalyteTrend(
                    test_name=name,
                    unit=unit,
                    data_points=data_points,
                    delta_absolute=delta_abs,
                    delta_percent=delta_pct,
                    direction=direction,
                    narrative_en=n_en,
                    narrative_hi=n_hi,
                )
            else:
                # Single data point
                trends[name] = AnalyteTrend(
                    test_name=name,
                    unit=unit,
                    data_points=data_points,
                    direction=TrendDirection.STABLE,
                    narrative_en=f"Baseline measurement recorded at {data_points[0].value} {unit}.",
                    narrative_hi=f"आधारभूत माप {data_points[0].value} {unit} दर्ज किया गया।",
                )

        return trends

    def _save_to_disk(self) -> None:
        """Persist current report history as JSON for cross-session continuity."""
        if not self.storage_dir:
            return
        out_file = self.storage_dir / "patient_history.json"
        data = [r.model_dump() for r in self.reports]
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_from_disk(self) -> None:
        """Load stored reports from disk if present."""
        if not self.storage_dir:
            return
        in_file = self.storage_dir / "patient_history.json"
        if not in_file.exists():
            return
        try:
            with open(in_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.reports = [LabReport(**item) for item in data]
        except Exception:
            pass
