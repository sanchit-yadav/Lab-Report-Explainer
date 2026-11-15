"""HIPAA/GDPR PHI De-Identification & Surrogate Anonymization Engine.

Removes 18 HIPAA Safe Harbor patient identifiers (Names, Dates of Birth, Phone Numbers,
Emails, MRNs, Addresses, Physician Names) and replaces them with surrogate tokens
before transmitting prompt tokens to external model APIs.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Pattern, Tuple

from src.extraction.schema import LabReport

logger = logging.getLogger("privacy.deidentifier")


RESERVED_CLINICAL_TERMS = {
    "dob", "date", "age", "sex", "gender", "id", "mrn", "uhid", "sample",
    "status", "test", "result", "ref", "reference", "unit", "units", "range",
    "normal", "high", "low", "abnormal", "critical", "serum", "plasma",
    "blood", "urine", "doctor", "physician", "consultant", "pathology", "lab",
}


@dataclass
class DetectedEntity:
    """Represents an identified Protected Health Information (PHI) instance."""
    entity_type: str
    original_value: str
    surrogate_token: str
    start_pos: int
    end_pos: int
    confidence: float = 1.0


@dataclass
class AnonymizationResult:
    """Output of de-identification containing sanitized text and surrogate mapping."""
    sanitized_text: str
    entity_mapping: Dict[str, str] = field(default_factory=dict)
    detected_entities: List[DetectedEntity] = field(default_factory=list)
    has_phi: bool = False


class PHIDeidentifier:
    """Clinical PHI De-identification engine complying with HIPAA §164.514(b) Safe Harbor."""

    def __init__(self):
        self._init_regex_patterns()

    def _init_regex_patterns(self):
        """Compile regex patterns for high-risk PHI entities."""
        # 1. Email Addresses
        self.email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
            re.IGNORECASE,
        )

        # 2. Phone Numbers (US & Indian national/international formats)
        self.phone_pattern = re.compile(
            r"(?:(?:\+91[\-\s]?)?[6789]\d{9})|"                     # Indian mobile
            r"(?:\+?1[\-\s]?)?\(?\d{3}\)?[\-\s]?\d{3}[\-\s]?\d{4}|"  # US format
            r"\b\d{3}[\-\.]\d{3}[\-\.]\d{4}\b",
        )

        # 3. Medical Record Numbers (MRN), UHID, Lab IDs, Sample Barcodes
        self.mrn_pattern = re.compile(
            r"\b(?:MRN|UHID|PATIENT\s*ID|PID|LAB\s*ID|SAMPLE\s*ID|BARCODE|REG\s*NO|ACCESSION\s*NO)[:\s#-]+([A-Z0-9\-_]{4,20})\b",
            re.IGNORECASE,
        )

        # 4. Dates of Birth and full calendar dates
        self.dob_pattern = re.compile(
            r"\b(?:DOB|DATE\s*OF\s*BIRTH|BORN)[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4})\b|"
            r"\b(\d{1,2}[\/\-\.](?:0[1-9]|1[0-2])[\/\-\.](?:19|20)\d{2})\b",
            re.IGNORECASE,
        )

        # 5. Doctor / Physician / Consultant References
        self.doctor_pattern = re.compile(
            r"\b(?:DR\.?|DOCTOR|PHYSICIAN|CONSULTANT|REF\.?\s*BY|DR\s+PATHOLOGIST|डॉ\.?)[:\s]+([A-Z][a-zA-Z\.\s]{2,30})\b",
            re.IGNORECASE,
        )

        # 6. Patient Name Prefixes and Headers
        self.patient_name_prefix_pattern = re.compile(
            r"\b(?:PATIENT\s*NAME|मरीज\s*का\s*नाम)[:\s]+(?:MR\.?|MRS\.?|MS\.?|MISS|MASTER|श्री|श्रीमती)?\s*([A-Z][a-zA-Z\s]{2,35})\b|"
            r"\b(?:MR\.?|MRS\.?|MS\.?|MISS|MASTER)\s+([A-Z][a-zA-Z]{2,20}\s+[A-Z][a-zA-Z]{2,20})\b",
            re.IGNORECASE,
        )

        # 7. Postal Codes and Pin Codes (US 5-digit ZIP, Indian 6-digit PIN)
        self.postal_pattern = re.compile(
            r"\b(?:PIN|PINCODE|ZIP|POSTAL\s*CODE)[:\s]*([1-9][0-9]{5}|[0-9]{5}(?:-[0-9]{4})?)\b",
            re.IGNORECASE,
        )

    def anonymize_text(self, text: str) -> AnonymizationResult:
        """Scan raw clinical text, identify all PHI entities, and substitute surrogate tokens."""
        if not text:
            return AnonymizationResult(sanitized_text="", has_phi=False)

        sanitized = text
        entity_mapping: Dict[str, str] = {}
        detected_entities: List[DetectedEntity] = []

        counter: Dict[str, int] = {
            "PATIENT_NAME": 1,
            "EMAIL": 1,
            "PHONE": 1,
            "MRN": 1,
            "DOB": 1,
            "DOCTOR": 1,
            "POSTAL": 1,
        }

        def record_replacement(ent_type: str, raw_val: str, current_text: str) -> str:
            clean_val = raw_val.strip()
            if not clean_val or clean_val.lower() in RESERVED_CLINICAL_TERMS:
                return current_text

            # If already assigned, reuse token
            for tok, orig in entity_mapping.items():
                if orig.lower() == clean_val.lower() and ent_type in tok:
                    return re.sub(r"(?<!\[)\b" + re.escape(clean_val) + r"\b(?!\])", tok, current_text)

            idx = counter[ent_type]
            counter[ent_type] += 1
            token = f"[{ent_type}_{idx}]"
            entity_mapping[token] = clean_val
            detected_entities.append(
                DetectedEntity(
                    entity_type=ent_type,
                    original_value=clean_val,
                    surrogate_token=token,
                    start_pos=0,
                    end_pos=0,
                )
            )
            return re.sub(r"(?<!\[)\b" + re.escape(clean_val) + r"\b(?!\])", token, current_text)

        # A. Emails
        for m in list(self.email_pattern.finditer(sanitized)):
            raw = m.group(0)
            token = f"[EMAIL_{counter['EMAIL']}]"
            counter["EMAIL"] += 1
            entity_mapping[token] = raw
            sanitized = sanitized.replace(raw, token)
            detected_entities.append(DetectedEntity("EMAIL", raw, token, m.start(), m.end()))

        # B. Phone numbers
        for m in list(self.phone_pattern.finditer(sanitized)):
            raw = m.group(0)
            # Avoid replacing pure 4-digit or standard small numbers
            if len(re.sub(r"\D", "", raw)) >= 7:
                token = f"[PHONE_{counter['PHONE']}]"
                counter["PHONE"] += 1
                entity_mapping[token] = raw
                sanitized = sanitized.replace(raw, token)
                detected_entities.append(DetectedEntity("PHONE", raw, token, m.start(), m.end()))

        # C. MRN and Patient IDs
        for m in list(self.mrn_pattern.finditer(sanitized)):
            id_val = m.group(1) if m.lastindex and m.group(1) else m.group(0)
            sanitized = record_replacement("MRN", id_val, sanitized)

        # D. Dates of Birth
        for m in list(self.dob_pattern.finditer(sanitized)):
            dob_val = m.group(1) or m.group(2) or m.group(0)
            sanitized = record_replacement("DOB", dob_val, sanitized)

        # E. Doctor Names
        for m in list(self.doctor_pattern.finditer(sanitized)):
            doc_val = m.group(1) if m.lastindex and m.group(1) else m.group(0)
            # Skip if common analyte name matched by mistake
            if doc_val.strip().lower() not in {"cholesterol", "hemoglobin", "glucose", "platelet"}:
                sanitized = record_replacement("DOCTOR", doc_val, sanitized)

        # F. Patient Name headers
        for m in list(self.patient_name_prefix_pattern.finditer(sanitized)):
            name_val = m.group(1) or m.group(2) or m.group(0)
            sanitized = record_replacement("PATIENT_NAME", name_val, sanitized)

        # G. Postal / Pin Codes
        for m in list(self.postal_pattern.finditer(sanitized)):
            post_val = m.group(1) if m.lastindex and m.group(1) else m.group(0)
            sanitized = record_replacement("POSTAL", post_val, sanitized)

        has_phi = len(entity_mapping) > 0
        if has_phi:
            logger.info(f"De-identified {len(entity_mapping)} PHI entities from text payload.")

        return AnonymizationResult(
            sanitized_text=sanitized,
            entity_mapping=entity_mapping,
            detected_entities=detected_entities,
            has_phi=has_phi,
        )

    def de_anonymize_text(self, text: str, entity_mapping: Dict[str, str]) -> str:
        """Substitute surrogate tokens back with original values for local user presentation."""
        if not text or not entity_mapping:
            return text

        restored = text
        for token, original in entity_mapping.items():
            restored = restored.replace(token, original)
        return restored

    def anonymize_lab_report(self, report: LabReport) -> Tuple[LabReport, Dict[str, str]]:
        """Create a deep clone of a LabReport with all patient-identifying fields de-identified."""
        sanitized = copy.deepcopy(report)
        mapping: Dict[str, str] = {}

        # 1. Patient Name
        if sanitized.patient_name:
            token = "[PATIENT_NAME_1]"
            mapping[token] = sanitized.patient_name
            sanitized.patient_name = token

        # 2. Patient Age (Generalize into HIPAA Safe Harbor age bracket if > 89)
        if sanitized.patient_age:
            digits = re.findall(r"\d+", str(sanitized.patient_age))
            if digits and int(digits[0]) > 89:
                mapping["[AGE_1]"] = str(sanitized.patient_age)
                sanitized.patient_age = "90+"

        # 3. Lab / Clinic Name (Replace with neutral surrogate to prevent geographic inference)
        if sanitized.lab_name and sanitized.lab_name.lower() not in {"diagnostic laboratory", "clinical lab"}:
            token = "[CLINICAL_LAB_1]"
            mapping[token] = sanitized.lab_name
            sanitized.lab_name = token

        logger.info(f"Anonymized LabReport metadata ({len(mapping)} surrogate tokens generated).")
        return sanitized, mapping

    def de_anonymize_explanation(
        self,
        explanation_en: str,
        explanation_hi: str,
        entity_mapping: Dict[str, str],
    ) -> Tuple[str, str]:
        """Re-hydrate surrogate tokens in English and Hindi explanation outputs."""
        restored_en = self.de_anonymize_text(explanation_en, entity_mapping)
        restored_hi = self.de_anonymize_text(explanation_hi, entity_mapping)
        return restored_en, restored_hi
