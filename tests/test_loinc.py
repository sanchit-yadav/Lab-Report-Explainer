"""Unit tests for LOINC clinical laboratory ontology mapping."""

from __future__ import annotations

import pytest

from src.extraction.loinc_mapper import LOINCMapper, LOINCRecord
from src.extraction.schema import FlagStatus, LabReport, TestResult


def test_map_lipid_panel_analytes():
    """Lipid analytes map to correct canonical LOINC codes and categories."""
    assert LOINCMapper.map_analyte("Total Cholesterol").code == "2093-3"
    assert LOINCMapper.map_analyte("HDL Cholesterol").code == "2085-9"
    assert LOINCMapper.map_analyte("LDL-C (Calculated)").code == "13457-7"
    assert LOINCMapper.map_analyte("Serum Triglycerides").code == "2571-8"
    assert LOINCMapper.map_analyte("VLDL").code == "13458-5"


def test_map_hematology_analytes():
    """CBC and hematology abbreviations map accurately."""
    assert LOINCMapper.map_analyte("Hemoglobin").code == "718-7"
    assert LOINCMapper.map_analyte("Hb").code == "718-7"
    assert LOINCMapper.map_analyte("HCT").code == "4544-3"
    assert LOINCMapper.map_analyte("Total Leukocyte Count (TLC)").code == "6690-2"
    assert LOINCMapper.map_analyte("Platelet Count").code == "777-3"
    assert LOINCMapper.map_analyte("MCV").code == "787-2"
    assert LOINCMapper.map_analyte("ESR").code == "4537-7"


def test_map_glycemic_and_metabolic():
    """Diabetes and glucose markers map to standard LOINC codes."""
    assert LOINCMapper.map_analyte("Fasting Blood Glucose").code == "1558-6"
    assert LOINCMapper.map_analyte("HbA1c").code == "4548-4"
    assert LOINCMapper.map_analyte("Glycated Hemoglobin").code == "4548-4"
    assert LOINCMapper.map_analyte("Postprandial Blood Glucose").code == "1521-4"


def test_map_renal_and_hepatic():
    """Liver and kidney markers map accurately with cross-industry abbreviations."""
    assert LOINCMapper.map_analyte("Serum Creatinine").code == "2160-0"
    assert LOINCMapper.map_analyte("Blood Urea Nitrogen").code == "3094-0"
    assert LOINCMapper.map_analyte("SGOT (AST)").code == "1920-8"
    assert LOINCMapper.map_analyte("SGPT / ALT").code == "1742-6"
    assert LOINCMapper.map_analyte("Total Bilirubin").code == "1975-2"
    assert LOINCMapper.map_analyte("Alkaline Phosphatase (ALP)").code == "6768-6"


def test_map_electrolytes_and_thyroid():
    """Electrolytes and thyroid hormones map cleanly."""
    assert LOINCMapper.map_analyte("Potassium").code == "2823-3"
    assert LOINCMapper.map_analyte("Sodium").code == "2951-2"
    assert LOINCMapper.map_analyte("TSH").code == "3016-3"
    assert LOINCMapper.map_analyte("Free T4").code == "3024-7"
    assert LOINCMapper.map_analyte("Ferritin").code == "2276-4"


def test_enrich_report_method():
    """LabReport tests are enriched with LOINC codes, display names, and panels."""
    report = LabReport(
        patient_name="Pooja Sharma",
        tests=[
            TestResult(test_name="Hemoglobin", value=13.2, unit="g/dL"),
            TestResult(test_name="Serum Triglycerides", value=190.0, unit="mg/dL"),
            TestResult(test_name="Uncommon Mystery Biomarker", value=5.0, unit="U/L"),
        ],
    )

    enriched = LOINCMapper.enrich_report(report)

    assert enriched.tests[0].loinc_code == "718-7"
    assert enriched.tests[0].category == "Hematology"
    assert enriched.tests[1].loinc_code == "2571-8"
    assert enriched.tests[1].category == "Lipid Panel"
    assert enriched.tests[2].loinc_code is None  # Graceful fallback for unmapped analytes
