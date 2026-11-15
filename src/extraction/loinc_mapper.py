"""Clinical LOINC (Logical Observation Identifiers Names and Codes) Ontology Mapper.

Standardizes laboratory test nomenclature from diverse health networks (Quest, LabCorp,
SRL, Metropolis, Dr Lal, Thyrocare, Apollo) into official LOINC codes, canonical units,
and clinical panel categories.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Dict, List, Optional, Tuple

from src.extraction.schema import LabReport, TestResult

logger = logging.getLogger("extraction.loinc_mapper")


@dataclass
class LOINCRecord:
    """Canonical LOINC observation record with ontology metadata."""
    code: str
    display_name: str
    common_name: str
    category: str
    canonical_unit: str
    system: str = "Serum/Plasma"


# Master LOINC Ontology Catalog for Clinical Laboratory Analytes
LOINC_CATALOG: Dict[str, LOINCRecord] = {
    # --------------------------------------------------------------------------
    # 1. Lipid Panel
    # --------------------------------------------------------------------------
    "2093-3": LOINCRecord("2093-3", "Cholesterol [Mass/volume] in Serum or Plasma", "Total Cholesterol", "Lipid Panel", "mg/dL"),
    "2085-9": LOINCRecord("2085-9", "Cholesterol in HDL [Mass/volume] in Serum or Plasma", "HDL Cholesterol", "Lipid Panel", "mg/dL"),
    "13457-7": LOINCRecord("13457-7", "Cholesterol in LDL [Mass/volume] in Serum or Plasma by calculation", "LDL Cholesterol", "Lipid Panel", "mg/dL"),
    "2571-8": LOINCRecord("2571-8", "Triglyceride [Mass/volume] in Serum or Plasma", "Triglycerides", "Lipid Panel", "mg/dL"),
    "13458-5": LOINCRecord("13458-5", "Cholesterol in VLDL [Mass/volume] in Serum or Plasma by calculation", "VLDL Cholesterol", "Lipid Panel", "mg/dL"),
    "43396-1": LOINCRecord("43396-1", "Non-HDL Cholesterol [Mass/volume] in Serum or Plasma", "Non-HDL Cholesterol", "Lipid Panel", "mg/dL"),

    # --------------------------------------------------------------------------
    # 2. Complete Blood Count (CBC) & Hematology
    # --------------------------------------------------------------------------
    "718-7": LOINCRecord("718-7", "Hemoglobin [Mass/volume] in Blood", "Hemoglobin", "Hematology", "g/dL", "Whole Blood"),
    "4544-3": LOINCRecord("4544-3", "Hematocrit [Volume Fraction] of Blood", "Hematocrit", "Hematology", "%", "Whole Blood"),
    "789-8": LOINCRecord("789-8", "Erythrocytes [#/volume] in Blood", "RBC Count", "Hematology", "10^6/uL", "Whole Blood"),
    "6690-2": LOINCRecord("6690-2", "Leukocytes [#/volume] in Blood", "WBC Count", "Hematology", "10^3/uL", "Whole Blood"),
    "777-3": LOINCRecord("777-3", "Platelets [#/volume] in Blood", "Platelet Count", "Hematology", "10^3/uL", "Whole Blood"),
    "787-2": LOINCRecord("787-2", "Erythrocyte mean corpuscular volume [Entitic volume]", "Mean Corpuscular Volume (MCV)", "Hematology", "fL", "RBCs"),
    "785-6": LOINCRecord("785-6", "Erythrocyte mean corpuscular hemoglobin [Entitic mass]", "Mean Corpuscular Hemoglobin (MCH)", "Hematology", "pg", "RBCs"),
    "786-4": LOINCRecord("786-4", "Erythrocyte mean corpuscular hemoglobin concentration [Mass/volume]", "MCHC", "Hematology", "g/dL", "RBCs"),
    "21000-5": LOINCRecord("21000-5", "Erythrocyte distribution width [Ratio]", "RDW", "Hematology", "%", "RBCs"),
    "770-8": LOINCRecord("770-8", "Neutrophils/100 leukocytes in Blood", "Neutrophils %", "Hematology", "%", "Whole Blood"),
    "736-9": LOINCRecord("736-9", "Lymphocytes/100 leukocytes in Blood", "Lymphocytes %", "Hematology", "%", "Whole Blood"),
    "742-7": LOINCRecord("742-7", "Monocytes/100 leukocytes in Blood", "Monocytes %", "Hematology", "%", "Whole Blood"),
    "711-2": LOINCRecord("711-2", "Eosinophils/100 leukocytes in Blood", "Eosinophils %", "Hematology", "%", "Whole Blood"),
    "704-7": LOINCRecord("704-7", "Basophils/100 leukocytes in Blood", "Basophils %", "Hematology", "%", "Whole Blood"),
    "4537-7": LOINCRecord("4537-7", "Erythrocyte sedimentation rate", "ESR", "Hematology", "mm/hr", "Whole Blood"),

    # --------------------------------------------------------------------------
    # 3. Glycemic & Metabolic Panel
    # --------------------------------------------------------------------------
    "1558-6": LOINCRecord("1558-6", "Fasting Glucose [Mass/volume] in Serum or Plasma", "Fasting Blood Glucose", "Metabolic Panel", "mg/dL"),
    "2345-7": LOINCRecord("2345-7", "Glucose [Mass/volume] in Serum or Plasma", "Random Blood Glucose", "Metabolic Panel", "mg/dL"),
    "1521-4": LOINCRecord("1521-4", "Glucose [Mass/volume] in Serum or Plasma --2 hours post meal", "Postprandial Blood Glucose", "Metabolic Panel", "mg/dL"),
    "4548-4": LOINCRecord("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "HbA1c", "Metabolic Panel", "%", "Whole Blood"),
    "20448-7": LOINCRecord("20448-7", "Insulin [Units/volume] in Serum or Plasma", "Fasting Insulin", "Metabolic Panel", "uIU/mL"),

    # --------------------------------------------------------------------------
    # 4. Renal Function Panel (KFT)
    # --------------------------------------------------------------------------
    "2160-0": LOINCRecord("2160-0", "Creatinine [Mass/volume] in Serum or Plasma", "Serum Creatinine", "Renal Function", "mg/dL"),
    "3094-0": LOINCRecord("3094-0", "Blood Urea Nitrogen [Mass/volume] in Serum or Plasma", "Blood Urea Nitrogen (BUN)", "Renal Function", "mg/dL"),
    "22707-4": LOINCRecord("22707-4", "Urea [Mass/volume] in Serum or Plasma", "Blood Urea", "Renal Function", "mg/dL"),
    "33914-3": LOINCRecord("33914-3", "Glomerular filtration rate/1.73 sq M.predicted", "Estimated GFR (eGFR)", "Renal Function", "mL/min/1.73m2"),
    "3084-1": LOINCRecord("3084-1", "Urate [Mass/volume] in Serum or Plasma", "Uric Acid", "Renal Function", "mg/dL"),

    # --------------------------------------------------------------------------
    # 5. Liver Function Panel (LFT)
    # --------------------------------------------------------------------------
    "1742-6": LOINCRecord("1742-6", "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma", "SGPT (ALT)", "Liver Function", "U/L"),
    "1920-8": LOINCRecord("1920-8", "Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma", "SGOT (AST)", "Liver Function", "U/L"),
    "6768-6": LOINCRecord("6768-6", "Alkaline phosphatase [Enzymatic activity/volume] in Serum or Plasma", "Alkaline Phosphatase (ALP)", "Liver Function", "U/L"),
    "1975-2": LOINCRecord("1975-2", "Bilirubin.total [Mass/volume] in Serum or Plasma", "Total Bilirubin", "Liver Function", "mg/dL"),
    "1968-7": LOINCRecord("1968-7", "Bilirubin.direct [Mass/volume] in Serum or Plasma", "Direct Bilirubin", "Liver Function", "mg/dL"),
    "1971-1": LOINCRecord("1971-1", "Bilirubin.indirect [Mass/volume] in Serum or Plasma", "Indirect Bilirubin", "Liver Function", "mg/dL"),
    "2885-2": LOINCRecord("2885-2", "Protein.total [Mass/volume] in Serum or Plasma", "Total Protein", "Liver Function", "g/dL"),
    "1751-7": LOINCRecord("1751-7", "Albumin [Mass/volume] in Serum or Plasma", "Serum Albumin", "Liver Function", "g/dL"),
    "2339-0": LOINCRecord("2339-0", "Globulin [Mass/volume] in Serum or Plasma by calculation", "Serum Globulin", "Liver Function", "g/dL"),
    "2324-2": LOINCRecord("2324-2", "Gamma glutamyl transferase [Enzymatic activity/volume] in Serum or Plasma", "GGT", "Liver Function", "U/L"),

    # --------------------------------------------------------------------------
    # 6. Electrolytes & Minerals
    # --------------------------------------------------------------------------
    "2951-2": LOINCRecord("2951-2", "Sodium [Moles/volume] in Serum or Plasma", "Serum Sodium", "Electrolytes", "mEq/L"),
    "2823-3": LOINCRecord("2823-3", "Potassium [Moles/volume] in Serum or Plasma", "Serum Potassium", "Electrolytes", "mEq/L"),
    "2075-0": LOINCRecord("2075-0", "Chloride [Moles/volume] in Serum or Plasma", "Serum Chloride", "Electrolytes", "mEq/L"),
    "17861-6": LOINCRecord("17861-6", "Calcium [Mass/volume] in Serum or Plasma", "Serum Calcium", "Electrolytes", "mg/dL"),
    "19123-9": LOINCRecord("19123-9", "Magnesium [Mass/volume] in Serum or Plasma", "Serum Magnesium", "Electrolytes", "mg/dL"),
    "2777-1": LOINCRecord("2777-1", "Phosphate [Mass/volume] in Serum or Plasma", "Serum Phosphorus", "Electrolytes", "mg/dL"),

    # --------------------------------------------------------------------------
    # 7. Thyroid Function Panel
    # --------------------------------------------------------------------------
    "3016-3": LOINCRecord("3016-3", "Thyrotropin [Units/volume] in Serum or Plasma", "TSH", "Thyroid Function", "uIU/mL"),
    "3024-7": LOINCRecord("3024-7", "Thyroxine (T4) free [Mass/volume] in Serum or Plasma", "Free T4", "Thyroid Function", "ng/dL"),
    "3051-0": LOINCRecord("3051-0", "Triiodothyronine (T3) free [Mass/volume] in Serum or Plasma", "Free T3", "Thyroid Function", "pg/mL"),
    "3026-2": LOINCRecord("3026-2", "Thyroxine (T4) total [Mass/volume] in Serum or Plasma", "Total T4", "Thyroid Function", "ug/dL"),
    "3053-6": LOINCRecord("3053-6", "Triiodothyronine (T3) total [Mass/volume] in Serum or Plasma", "Total T3", "Thyroid Function", "ng/dL"),

    # --------------------------------------------------------------------------
    # 8. Vitamins, Iron & Inflammatory Markers
    # --------------------------------------------------------------------------
    "62292-8": LOINCRecord("62292-8", "25-hydroxyvitamin D3 + 25-hydroxyvitamin D2 [Mass/volume] in Serum or Plasma", "Vitamin D (25-OH)", "Vitamins", "ng/mL"),
    "2132-9": LOINCRecord("2132-9", "Cobalamin (Vitamin B12) [Mass/volume] in Serum or Plasma", "Vitamin B12", "Vitamins", "pg/mL"),
    "2276-4": LOINCRecord("2276-4", "Ferritin [Mass/volume] in Serum or Plasma", "Serum Ferritin", "Iron Studies", "ng/mL"),
    "2498-4": LOINCRecord("2498-4", "Iron [Mass/volume] in Serum or Plasma", "Serum Iron", "Iron Studies", "ug/dL"),
    "1988-5": LOINCRecord("1988-5", "C reactive protein [Mass/volume] in Serum or Plasma", "C-Reactive Protein (CRP)", "Inflammatory", "mg/L"),
}


# Pre-computed normalized alias dictionary for high-speed deterministic matching
SYNONYM_MAP: Dict[str, str] = {
    # Lipids
    "cholesterol": "2093-3",
    "totalcholesterol": "2093-3",
    "serumcholesterol": "2093-3",
    "cholesteroltotal": "2093-3",
    "chol": "2093-3",
    "tc": "2093-3",
    "hdl": "2085-9",
    "hdlcholesterol": "2085-9",
    "hdlc": "2085-9",
    "highdensitylipoprotein": "2085-9",
    "ldl": "13457-7",
    "ldlcholesterol": "13457-7",
    "ldlc": "13457-7",
    "lowdensitylipoprotein": "13457-7",
    "calculatedldl": "13457-7",
    "triglycerides": "2571-8",
    "triglyceride": "2571-8",
    "serumtriglycerides": "2571-8",
    "tg": "2571-8",
    "trig": "2571-8",
    "vldl": "13458-5",
    "vldlcholesterol": "13458-5",
    "nonhdl": "43396-1",
    "nonhdlcholesterol": "43396-1",

    # CBC / Hematology
    "hemoglobin": "718-7",
    "hb": "718-7",
    "hgb": "718-7",
    "hematocrit": "4544-3",
    "hct": "4544-3",
    "pcv": "4544-3",
    "rbc": "789-8",
    "rbccount": "789-8",
    "redbloodcells": "789-8",
    "erythrocytes": "789-8",
    "totalrbc": "789-8",
    "wbc": "6690-2",
    "wbccount": "6690-2",
    "whitebloodcells": "6690-2",
    "leukocytes": "6690-2",
    "totalleukocytecount": "6690-2",
    "tlc": "6690-2",
    "platelets": "777-3",
    "plateletcount": "777-3",
    "plt": "777-3",
    "mcv": "787-2",
    "meancorpuscularvolume": "787-2",
    "mch": "785-6",
    "meancorpuscularhemoglobin": "785-6",
    "mchc": "786-4",
    "rdw": "21000-5",
    "neutrophils": "770-8",
    "lymphocytes": "736-9",
    "monocytes": "742-7",
    "eosinophils": "711-2",
    "basophils": "704-7",
    "esr": "4537-7",

    # Glycemic
    "fastingbloodglucose": "1558-6",
    "fastingglucose": "1558-6",
    "glucosefasting": "1558-6",
    "fbg": "1558-6",
    "bsf": "1558-6",
    "randombloodglucose": "2345-7",
    "randomglucose": "2345-7",
    "rbs": "2345-7",
    "postprandialbloodglucose": "1521-4",
    "ppbs": "1521-4",
    "hba1c": "4548-4",
    "glycatedhemoglobin": "4548-4",
    "glycohemoglobin": "4548-4",
    "insulin": "20448-7",
    "fastinginsulin": "20448-7",

    # Renal
    "creatinine": "2160-0",
    "serumcreatinine": "2160-0",
    "creat": "2160-0",
    "bun": "3094-0",
    "bloodureanitrogen": "3094-0",
    "urea": "22707-4",
    "bloodurea": "22707-4",
    "serumurea": "22707-4",
    "egfr": "33914-3",
    "estimatedgfr": "33914-3",
    "uricacid": "3084-1",
    "serumurate": "3084-1",

    # Hepatic
    "sgpt": "1742-6",
    "alt": "1742-6",
    "alanineaminotransferase": "1742-6",
    "sgptalt": "1742-6",
    "sgot": "1920-8",
    "ast": "1920-8",
    "aspartateaminotransferase": "1920-8",
    "sgotast": "1920-8",
    "alp": "6768-6",
    "alkalinephosphatase": "6768-6",
    "alkphos": "6768-6",
    "totalbilirubin": "1975-2",
    "bilirubintotal": "1975-2",
    "tbili": "1975-2",
    "directbilirubin": "1968-7",
    "bilirubindirect": "1968-7",
    "dbili": "1968-7",
    "indirectbilirubin": "1971-1",
    "totalprotein": "2885-2",
    "albumin": "1751-7",
    "serumalbumin": "1751-7",
    "globulin": "2339-0",
    "ggt": "2324-2",

    # Electrolytes
    "sodium": "2951-2",
    "serumsodium": "2951-2",
    "na": "2951-2",
    "potassium": "2823-3",
    "serumpotassium": "2823-3",
    "k": "2823-3",
    "chloride": "2075-0",
    "serumchloride": "2075-0",
    "cl": "2075-0",
    "calcium": "17861-6",
    "serumcalcium": "17861-6",
    "ca": "17861-6",
    "magnesium": "19123-9",
    "phosphorus": "2777-1",

    # Thyroid
    "tsh": "3016-3",
    "thyroidstimulatinghormone": "3016-3",
    "freet4": "3024-7",
    "ft4": "3024-7",
    "freet3": "3051-0",
    "ft3": "3051-0",
    "totalt4": "3026-2",
    "t4": "3026-2",
    "totalt3": "3053-6",
    "t3": "3053-6",

    # Vitamins & Iron
    "vitamind": "62292-8",
    "vitamind25oh": "62292-8",
    "25hydroxyvitamind": "62292-8",
    "vitamind3": "62292-8",
    "vitaminb12": "2132-9",
    "b12": "2132-9",
    "ferritin": "2276-4",
    "serumferritin": "2276-4",
    "iron": "2498-4",
    "serumiron": "2498-4",
    "crp": "1988-5",
    "creactiveprotein": "1988-5",
    "hscrp": "1988-5",
}


class LOINCMapper:
    """Clinical ontology standardizer matching arbitrary lab strings to LOINC codes."""

    @staticmethod
    def normalize_name(name: str) -> str:
        """Strip punctuation, spaces, and clinical boilerplate tokens for key lookup."""
        if not name:
            return ""
        clean = name.lower()
        # Remove parentheticals, e.g. "(serum)", "(calc)", "[fasting]"
        clean = re.sub(r"\(.*?\)|\[.*?\]", "", clean)
        # Remove common lab boilerplate words
        clean = re.sub(r"\b(serum|plasma|blood|level|levels|test|panel|rate|estimated|calculated|total|fasting)\b", "", clean)
        # Keep only alphanumeric characters
        clean = re.sub(r"[^a-z0-9]", "", clean)
        return clean

    @classmethod
    def map_analyte(cls, test_name: str) -> Optional[LOINCRecord]:
        """Resolve a raw laboratory test name to its official LOINC ontology record."""
        if not test_name:
            return None

        # 1. Direct lowercase lookup
        direct_key = re.sub(r"[^a-z0-9]", "", test_name.lower())
        if direct_key in SYNONYM_MAP:
            return LOINC_CATALOG.get(SYNONYM_MAP[direct_key])

        # 2. Normalized stripped lookup
        norm_key = cls.normalize_name(test_name)
        if norm_key in SYNONYM_MAP:
            return LOINC_CATALOG.get(SYNONYM_MAP[norm_key])

        # 3. Fuzzy substring containment
        for alias, loinc_code in SYNONYM_MAP.items():
            if len(alias) >= 4 and (alias in direct_key or direct_key in alias):
                return LOINC_CATALOG.get(loinc_code)

        logger.debug(f"Unmapped laboratory analyte: '{test_name}'")
        return None

    @classmethod
    def enrich_test_result(cls, test: TestResult) -> TestResult:
        """Enrich a TestResult instance with LOINC code, display name, and category."""
        record = cls.map_analyte(test.test_name)
        if record:
            test.loinc_code = record.code
            test.loinc_name = record.display_name
            test.category = record.category
        return test

    @classmethod
    def enrich_report(cls, report: LabReport) -> LabReport:
        """Enrich all test results in a LabReport with standardized LOINC ontology."""
        mapped_count = 0
        for test in report.tests:
            cls.enrich_test_result(test)
            if test.loinc_code:
                mapped_count += 1

        logger.info(
            f"LOINC ontology mapping: {mapped_count}/{len(report.tests)} analytes mapped to standard codes."
        )
        return report
