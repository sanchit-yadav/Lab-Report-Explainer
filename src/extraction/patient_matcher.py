"""Deterministic Patient Identity Matching and Isolation Engine.

Protects against Patient Cross-Contamination hazards by validating patient identity
across multiple uploaded documents (comparing normalized names, gender consistency,
and age parameters).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.extraction.schema import LabReport

# Common clinical name prefixes to strip during normalization
TITLES = [
    r"\bmr\b\.?",
    r"\bmrs\b\.?",
    r"\bms\b\.?",
    r"\bmiss\b\.?",
    r"\bdr\b\.?",
    r"\bmaster\b\.?",
    r"\bshri\b\.?",
    r"\bshree\b\.?",
    r"\bsmt\b\.?",
    r"\bmd\b\.?",
]


def normalize_patient_name(name: Optional[str]) -> str:
    """Normalize patient name by stripping clinical titles, punctuation, and excess spaces."""
    if not name or not name.strip():
        return ""

    cleaned = name.lower().strip()

    # Strip prefixes
    for prefix in TITLES:
        cleaned = re.sub(rf"^{prefix}\s*", "", cleaned)
        cleaned = re.sub(rf"\s+{prefix}\s+", " ", cleaned)

    # Remove non-alphabet characters except spaces
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", cleaned)
    # Collapse multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_gender(gender: Optional[str]) -> Optional[str]:
    """Normalize gender strings to canonical 'male', 'female', or None."""
    if not gender:
        return None
    g = gender.strip().lower()
    if g.startswith("m"):
        return "male"
    if g.startswith("f"):
        return "female"
    return None


def parse_numeric_age(age_str: Optional[str]) -> Optional[int]:
    """Extract numeric years from age strings like '52 Y', '31 Years', '45'."""
    if not age_str:
        return None
    match = re.search(r"\b(\d{1,3})\b", age_str)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


class PatientMatchResult(BaseModel):
    """Result of patient identity verification across documents."""
    is_single_patient: bool = True
    distinct_patients: List[str] = Field(default_factory=list)
    patient_groups: Dict[str, List[LabReport]] = Field(default_factory=dict)
    warning_message_en: Optional[str] = None
    warning_message_hi: Optional[str] = None


def are_reports_same_patient(r1: LabReport, r2: LabReport) -> Tuple[bool, Optional[str]]:
    """Determine whether two laboratory reports belong to the same patient.

    Returns:
        (is_same, reason_if_mismatch)
    """
    n1 = normalize_patient_name(r1.patient_name)
    n2 = normalize_patient_name(r2.patient_name)

    # 1. Name Check (if both reports have names)
    if n1 and n2:
        # Check token containment (e.g. 'ramesh kumar' and 'ramesh kumar sharma' or 'ramesh kumar' and 'ramesh')
        tokens1 = set(n1.split())
        tokens2 = set(n2.split())

        # If completely disjoint names, definitely different patients
        overlap = tokens1.intersection(tokens2)
        if not overlap:
            return False, f"Different patient names: '{r1.patient_name}' vs '{r2.patient_name}'"

        # Check Jaccard similarity between name tokens
        similarity = len(overlap) / max(len(tokens1.union(tokens2)), 1)
        if similarity < 0.5 and not (tokens1.issubset(tokens2) or tokens2.issubset(tokens1)):
            return False, f"Name mismatch: '{r1.patient_name}' vs '{r2.patient_name}'"

    # 2. Gender Consistency Check
    g1 = normalize_gender(r1.patient_gender)
    g2 = normalize_gender(r2.patient_gender)
    if g1 and g2 and g1 != g2:
        return False, f"Gender mismatch: '{r1.patient_name}' ({g1}) vs '{r2.patient_name}' ({g2})"

    # 3. Age Consistency Check (allow up to 2 years variance for longitudinal reports)
    a1 = parse_numeric_age(r1.patient_age)
    a2 = parse_numeric_age(r2.patient_age)
    if a1 is not None and a2 is not None and abs(a1 - a2) > 3:
        return False, f"Significant age difference: {a1} years vs {a2} years"

    return True, None


def group_reports_by_patient(reports: List[LabReport]) -> PatientMatchResult:
    """Group a collection of reports into distinct patient cohorts to prevent clinical cross-contamination."""
    if not reports:
        return PatientMatchResult(is_single_patient=True)

    if len(reports) == 1:
        p_label = reports[0].patient_name or "Patient 1"
        return PatientMatchResult(
            is_single_patient=True,
            distinct_patients=[p_label],
            patient_groups={p_label: reports},
        )

    # Partition reports into cohorts
    cohorts: List[List[LabReport]] = []

    for rep in reports:
        placed = False
        for cohort in cohorts:
            # Check against representative report in cohort
            is_same, _ = are_reports_same_patient(cohort[0], rep)
            if is_same:
                cohort.append(rep)
                placed = True
                break
        if not placed:
            cohorts.append([rep])

    # Build cohort dictionary
    patient_groups: Dict[str, List[LabReport]] = {}
    distinct_names: List[str] = []

    for idx, cohort in enumerate(cohorts, start=1):
        # Pick the most complete name in the cohort
        best_name = next(
            (r.patient_name for r in cohort if r.patient_name and len(r.patient_name.strip()) > 2),
            f"Patient {idx}",
        )
        gender_suffix = next((f" ({r.patient_gender})" for r in cohort if r.patient_gender), "")
        age_suffix = next((f", {r.patient_age}" for r in cohort if r.patient_age), "")
        cohort_label = f"{best_name}{gender_suffix}{age_suffix}".strip()

        # Handle identical labels
        if cohort_label in patient_groups:
            cohort_label = f"{cohort_label} ({idx})"

        patient_groups[cohort_label] = cohort
        distinct_names.append(cohort_label)

    is_single = len(cohorts) == 1

    warning_en = None
    warning_hi = None
    if not is_single:
        p_list_str = ", ".join(f"'{name}'" for name in distinct_names)
        warning_en = (
            f"Patient Mismatch Detected: The uploaded documents belong to {len(cohorts)} different individuals ({p_list_str}). "
            "To prevent medical cross-contamination and inaccurate reference range calculations, the reports have been safely "
            "separated into distinct patient profiles."
        )
        warning_hi = (
            f"मरीजों की पहचान में भिन्नता: अपलोड किए गए दस्तावेज़ {len(cohorts)} अलग-अलग व्यक्तियों ({p_list_str}) के हैं। "
            "चिकित्सीय सुरक्षा और सही संदर्भ सीमा सुनिश्चित करने के लिए, इन रिपोर्टों को अलग-अलग प्रोफाइलों में सुरक्षित रूप से विभाजित किया गया है।"
        )

    return PatientMatchResult(
        is_single_patient=is_single,
        distinct_patients=distinct_names,
        patient_groups=patient_groups,
        warning_message_en=warning_en,
        warning_message_hi=warning_hi,
    )
