"""HL7 FHIR Release 4 Interoperability Exporter for Clinical Laboratory Reports.

Generates standard FHIR DiagnosticReport, Observation, and Bundle JSON resources
for direct integration into Electronic Health Record (EHR) systems (Epic, Cerner, AthenaHealth).
"""

from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.explainer.schema import ReportExplanation
from src.extraction.loinc_mapper import LOINCMapper
from src.extraction.schema import FlagStatus, LabReport, TestResult

logger = logging.getLogger("interop.fhir")

# FHIR v3 ObservationInterpretation code mapping
FHIR_INTERPRETATION_MAP = {
    FlagStatus.NORMAL: {"code": "N", "display": "Normal"},
    FlagStatus.HIGH: {"code": "H", "display": "High"},
    FlagStatus.LOW: {"code": "L", "display": "Low"},
    FlagStatus.CRITICAL_HIGH: {"code": "HH", "display": "Critical high"},
    FlagStatus.CRITICAL_LOW: {"code": "LL", "display": "Critical low"},
    FlagStatus.ABNORMAL: {"code": "A", "display": "Abnormal"},
}


class FHIRExporter:
    """Transforms native LabReport and ReportExplanation models into official HL7 FHIR R4 resources."""

    @staticmethod
    def _generate_deterministic_id(prefix: str, *keys: str) -> str:
        """Create a stable UUID5 based on clinical entity values."""
        raw = ":".join(keys)
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{prefix}:{raw}"))

    @classmethod
    def test_result_to_observation(
        cls,
        test: TestResult,
        patient_id: str,
        patient_name: str,
        effective_time: str,
    ) -> Dict[str, Any]:
        """Convert an individual TestResult analyte into a FHIR R4 Observation resource."""
        # Ensure LOINC mapping
        if not test.loinc_code:
            LOINCMapper.enrich_test_result(test)

        obs_id = cls._generate_deterministic_id(
            "Observation", patient_id, test.test_name, str(test.value)
        )
        loinc_code = test.loinc_code or "unknown"
        loinc_display = test.loinc_name or test.test_name

        obs: Dict[str, Any] = {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "laboratory",
                            "display": "Laboratory",
                        }
                    ]
                }
            ],
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": loinc_code,
                        "display": loinc_display,
                    }
                ],
                "text": test.test_name,
            },
            "subject": {
                "reference": f"Patient/{patient_id}",
                "display": patient_name or "Anonymous Patient",
            },
            "effectiveDateTime": effective_time,
        }

        # Value Quantity or String
        if test.value is not None:
            obs["valueQuantity"] = {
                "value": float(test.value),
                "unit": test.unit or "",
                "system": "http://unitsofmeasure.org",
                "code": test.unit or "",
            }
        elif test.raw_value:
            obs["valueString"] = test.raw_value

        # Interpretation Flag
        if test.flag in FHIR_INTERPRETATION_MAP:
            f_code = FHIR_INTERPRETATION_MAP[test.flag]
            obs["interpretation"] = [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                            "code": f_code["code"],
                            "display": f_code["display"],
                        }
                    ],
                    "text": test.flag.value.upper(),
                }
            ]

        # Reference Interval
        if test.ref_low is not None or test.ref_high is not None or test.ref_raw:
            ref_range: Dict[str, Any] = {}
            if test.ref_low is not None:
                ref_range["low"] = {"value": float(test.ref_low), "unit": test.unit or ""}
            if test.ref_high is not None:
                ref_range["high"] = {"value": float(test.ref_high), "unit": test.unit or ""}
            if test.ref_raw:
                ref_range["text"] = test.ref_raw
            obs["referenceRange"] = [ref_range]

        return obs

    @classmethod
    def create_diagnostic_report(
        cls,
        report: LabReport,
        explanation: Optional[ReportExplanation] = None,
        pdf_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Generate a complete FHIR R4 Bundle containing DiagnosticReport and Observations."""
        patient_name = report.patient_name or "Anonymous Patient"
        patient_id = cls._generate_deterministic_id(
            "Patient", patient_name, str(report.patient_age or "")
        )
        effective_time = report.report_date or datetime.now(timezone.utc).isoformat()
        issued_time = datetime.now(timezone.utc).isoformat()

        report_id = cls._generate_deterministic_id("DiagnosticReport", patient_id, effective_time)

        # 1. Generate Observation resources for each analyte
        observations: List[Dict[str, Any]] = []
        result_references: List[Dict[str, str]] = []

        for test in report.tests:
            obs = cls.test_result_to_observation(test, patient_id, patient_name, effective_time)
            observations.append(obs)
            result_references.append({"reference": f"Observation/{obs['id']}"})

        # 2. Build DiagnosticReport resource
        diag_report: Dict[str, Any] = {
            "resourceType": "DiagnosticReport",
            "id": report_id,
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                            "code": "LAB",
                            "display": "Laboratory",
                        }
                    ]
                }
            ],
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "11502-2",
                        "display": "Laboratory report",
                    }
                ],
                "text": "Clinical Laboratory Evaluation & Interpretation",
            },
            "subject": {
                "reference": f"Patient/{patient_id}",
                "display": patient_name,
            },
            "effectiveDateTime": effective_time,
            "issued": issued_time,
            "performer": [
                {
                    "display": report.lab_name or "Diagnostic Laboratory Services",
                }
            ],
            "result": result_references,
        }

        # Add Educational Summary if explanation exists
        if explanation and explanation.report_summary_en:
            diag_report["conclusion"] = explanation.report_summary_en

        # Attach Base64 PDF brief if provided
        if pdf_bytes:
            diag_report["presentedForm"] = [
                {
                    "contentType": "application/pdf",
                    "data": base64.b64encode(pdf_bytes).decode("utf-8"),
                    "title": "Doctor Discussion Brief (PDF)",
                }
            ]

        # 3. Assemble into FHIR R4 Bundle
        bundle_id = str(uuid.uuid4())
        bundle_entries: List[Dict[str, Any]] = [
            {
                "fullUrl": f"urn:uuid:{report_id}",
                "resource": diag_report,
            }
        ]

        for obs in observations:
            bundle_entries.append(
                {
                    "fullUrl": f"urn:uuid:{obs['id']}",
                    "resource": obs,
                }
            )

        fhir_bundle = {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "collection",
            "timestamp": issued_time,
            "total": len(bundle_entries),
            "entry": bundle_entries,
        }

        logger.info(
            f"Assembled FHIR R4 Bundle {bundle_id} containing DiagnosticReport/{report_id} "
            f"and {len(observations)} Observations."
        )
        return fhir_bundle
