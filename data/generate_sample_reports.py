"""Synthetic lab report PDF and ground-truth JSON generator.

Uses ReportLab to generate 10 realistic synthetic diagnostic reports
with purely fictional clinical values, covering different laboratory styles,
multipage tables, non-numeric results, and complex border arrangements.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "data" / "sample_reports"
LABELED_DIR = PROJECT_ROOT / "data" / "labeled"


def _ensure_dirs():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LABELED_DIR.mkdir(parents=True, exist_ok=True)


def create_header(canvas, doc, lab_name: str, subtitle: str):
    """Draw common lab banner header."""
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 14)
    canvas.setFillColor(colors.HexColor("#1A365D"))
    canvas.drawString(54, 750, lab_name)
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#4A5568"))
    canvas.drawString(54, 738, subtitle)
    canvas.setStrokeColor(colors.HexColor("#CBD5E0"))
    canvas.setLineWidth(1)
    canvas.line(54, 730, 558, 730)
    canvas.restoreState()


def build_report_pdf(
    filename: str,
    lab_name: str,
    subtitle: str,
    patient_info: Dict[str, str],
    table_headers: List[str],
    table_rows: List[List[str]],
    multipage: bool = False,
    complex_borders: bool = False,
) -> Path:
    """Build a synthetic PDF report and save it to data/sample_reports."""
    pdf_path = REPORTS_DIR / filename
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=72,
        bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    story = []

    # Patient info table
    p_data = [
        [f"Patient Name: {patient_info['name']}", f"Age / Gender: {patient_info['age']} / {patient_info['gender']}"],
        [f"Referred By: Dr. A. Verma, MD", f"Collection Date: {patient_info['date']}"],
        [f"Sample ID: SMPL-{patient_info['id']}", f"Report Status: Final Authorized"],
    ]
    p_table = Table(p_data, colWidths=[250, 250])
    p_table.setStyle(
        TableStyle([
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#2D3748")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ])
    )
    story.append(p_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=12))

    # Test Results Table
    full_table_data = [table_headers] + table_rows
    col_widths = [190, 90, 80, 140]
    
    t_style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1A202C")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("ALIGN", (1, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#718096")),
    ]

    if complex_borders:
        t_style_cmds.extend([
            ("GRID", (0, 0), (-1, -1), 1.0, colors.HexColor("#4A5568")),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F7FAFC")),
            ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#F7FAFC")),
        ])

    if multipage:
        # Split rows across two pages
        half = len(table_rows) // 2
        page1_data = [table_headers] + table_rows[:half]
        page2_data = [table_headers] + table_rows[half:]
        
        t1 = Table(page1_data, colWidths=col_widths)
        t1.setStyle(TableStyle(t_style_cmds))
        story.append(t1)
        story.append(PageBreak())
        
        t2 = Table(page2_data, colWidths=col_widths)
        t2.setStyle(TableStyle(t_style_cmds))
        story.append(Paragraph(f"<b>{lab_name} — Continued Report</b>", styles["Normal"]))
        story.append(Spacer(1, 10))
        story.append(t2)
    else:
        results_table = Table(full_table_data, colWidths=col_widths)
        results_table.setStyle(TableStyle(t_style_cmds))
        story.append(results_table)

    story.append(Spacer(1, 16))
    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        textColor=colors.HexColor("#718096"),
        alignment=1,
    )
    story.append(
        Paragraph(
            "*** End of Report — Results relate only to specimen tested. Please correlate clinically with consulting physician. ***",
            disclaimer_style,
        )
    )

    doc.build(
        story,
        onFirstPage=lambda c, d: create_header(c, d, lab_name, subtitle),
        onLaterPages=lambda c, d: create_header(c, d, lab_name, subtitle),
    )
    return pdf_path


def save_ground_truth(filename: str, report_dict: Dict[str, Any]) -> Path:
    """Save ground truth JSON to data/labeled."""
    json_path = LABELED_DIR / filename
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)
    return json_path


# ==============================================================================
# Sample Datasets Definition
# ==============================================================================

REPORTS_DATA = [
    # 1. Thyrocare CBC
    {
        "filename_pdf": "thyrocare_cbc.pdf",
        "filename_json": "thyrocare_cbc.json",
        "lab_name": "Thyrocare Technologies Ltd",
        "subtitle": "National Reference Laboratory | Automated Diagnostic Division",
        "patient": {"name": "Aarav Sharma", "age": "34", "gender": "Male", "date": "2026-10-14", "id": "98124"},
        "headers": ["Investigation", "Observed Value", "Unit", "Biological Ref. Interval"],
        "rows": [
            ["Hemoglobin", "14.2", "g/dL", "13.0 - 17.0"],
            ["WBC Count", "11,500", "cells/cumm", "4000 - 11000"],
            ["RBC Count", "4.8", "x10⁶/µL", "4.5 - 5.5"],
            ["Platelet Count", "240000", "cells/cumm", "150000 - 450000"],
            ["Hematocrit", "42.5", "%", "40.0 - 50.0"],
            ["MCV", "88.2", "fL", "80.0 - 100.0"],
            ["MCH", "29.5", "pg", "27.0 - 33.0"],
            ["MCHC", "33.4", "g/dL", "32.0 - 36.0"],
        ],
        "ground_truth_tests": [
            {"test_name": "Hemoglobin", "value": 14.2, "raw_value": "14.2", "unit": "g/dL", "ref_low": 13.0, "ref_high": 17.0},
            {"test_name": "WBC Count", "value": 11500.0, "raw_value": "11,500", "unit": "cells/cumm", "ref_low": 4000.0, "ref_high": 11000.0},
            {"test_name": "RBC Count", "value": 4.8, "raw_value": "4.8", "unit": "x10⁶/µL", "ref_low": 4.5, "ref_high": 5.5},
            {"test_name": "Platelet Count", "value": 240000.0, "raw_value": "240000", "unit": "cells/cumm", "ref_low": 150000.0, "ref_high": 450000.0},
            {"test_name": "Hematocrit", "value": 42.5, "raw_value": "42.5", "unit": "%", "ref_low": 40.0, "ref_high": 50.0},
            {"test_name": "MCV", "value": 88.2, "raw_value": "88.2", "unit": "fL", "ref_low": 80.0, "ref_high": 100.0},
            {"test_name": "MCH", "value": 29.5, "raw_value": "29.5", "unit": "pg", "ref_low": 27.0, "ref_high": 33.0},
            {"test_name": "MCHC", "value": 33.4, "raw_value": "33.4", "unit": "g/dL", "ref_low": 32.0, "ref_high": 36.0},
        ],
    },
    # 2. SRL Lipid Panel
    {
        "filename_pdf": "srl_lipid_panel.pdf",
        "filename_json": "srl_lipid_panel.json",
        "lab_name": "SRL Diagnostics",
        "subtitle": "Department of Clinical Biochemistry | NABL Accredited",
        "patient": {"name": "Pooja Patel", "age": "45", "gender": "Female", "date": "2026-10-18", "id": "45210"},
        "headers": ["Test Name", "Result", "Units", "Reference Range"],
        "rows": [
            ["Total Cholesterol", "248.0", "mg/dL", "< 200"],
            ["Triglycerides", "185.0", "mg/dL", "< 150"],
            ["HDL Cholesterol", "42.0", "mg/dL", "> 50"],
            ["LDL Cholesterol", "162.0", "mg/dL", "< 100"],
            ["VLDL Cholesterol", "37.0", "mg/dL", "10.0 - 30.0"],
        ],
        "ground_truth_tests": [
            {"test_name": "Total Cholesterol", "value": 248.0, "raw_value": "248.0", "unit": "mg/dL", "ref_low": None, "ref_high": 200.0},
            {"test_name": "Triglycerides", "value": 185.0, "raw_value": "185.0", "unit": "mg/dL", "ref_low": None, "ref_high": 150.0},
            {"test_name": "HDL Cholesterol", "value": 42.0, "raw_value": "42.0", "unit": "mg/dL", "ref_low": 50.0, "ref_high": None},
            {"test_name": "LDL Cholesterol", "value": 162.0, "raw_value": "162.0", "unit": "mg/dL", "ref_low": None, "ref_high": 100.0},
            {"test_name": "VLDL Cholesterol", "value": 37.0, "raw_value": "37.0", "unit": "mg/dL", "ref_low": 10.0, "ref_high": 30.0},
        ],
    },
    # 3. Dr Lal PathLabs Thyroid
    {
        "filename_pdf": "lal_pathlabs_thyroid.pdf",
        "filename_json": "lal_pathlabs_thyroid.json",
        "lab_name": "Dr. Lal PathLabs Ltd.",
        "subtitle": "Endocrine & Hormone Assay Laboratory",
        "patient": {"name": "Sunita Verma", "age": "52", "gender": "Female", "date": "2026-10-22", "id": "89311"},
        "headers": ["Parameter", "Observed Value", "Unit", "Bio. Ref. Interval"],
        "rows": [
            ["TSH - Thyroid Stimulating Hormone", "6.85", "µIU/mL", "0.45 - 4.50"],
            ["Total T3", "110.0", "ng/dL", "80.0 - 200.0"],
            ["Total T4", "7.4", "µg/dL", "5.0 - 12.0"],
            ["Free T3", "2.8", "pg/mL", "2.0 - 4.4"],
            ["Free T4", "1.1", "ng/dL", "0.8 - 1.8"],
        ],
        "ground_truth_tests": [
            {"test_name": "TSH - Thyroid Stimulating Hormone", "value": 6.85, "raw_value": "6.85", "unit": "µIU/mL", "ref_low": 0.45, "ref_high": 4.50},
            {"test_name": "Total T3", "value": 110.0, "raw_value": "110.0", "unit": "ng/dL", "ref_low": 80.0, "ref_high": 200.0},
            {"test_name": "Total T4", "value": 7.4, "raw_value": "7.4", "unit": "µg/dL", "ref_low": 5.0, "ref_high": 12.0},
            {"test_name": "Free T3", "value": 2.8, "raw_value": "2.8", "unit": "pg/mL", "ref_low": 2.0, "ref_high": 4.4},
            {"test_name": "Free T4", "value": 1.1, "raw_value": "1.1", "unit": "ng/dL", "ref_low": 0.8, "ref_high": 1.8},
        ],
    },
    # 4. Metropolis Liver Function Test
    {
        "filename_pdf": "metropolis_liver.pdf",
        "filename_json": "metropolis_liver.json",
        "lab_name": "Metropolis Healthcare Ltd",
        "subtitle": "Department of Hepatic & Metabolic Studies",
        "patient": {"name": "Vikram Singh", "age": "41", "gender": "Male", "date": "2026-10-25", "id": "12904"},
        "headers": ["Investigation", "Your Result", "UOM", "Ref. Interval"],
        "rows": [
            ["Bilirubin Total", "1.8", "mg/dL", "0.2 - 1.2"],
            ["Bilirubin Direct", "0.6", "mg/dL", "0.0 - 0.3"],
            ["SGOT (AST)", "58.0", "U/L", "5.0 - 40.0"],
            ["SGPT (ALT)", "72.0", "U/L", "7.0 - 56.0"],
            ["Alkaline Phosphatase (ALP)", "95.0", "U/L", "44.0 - 147.0"],
            ["Total Protein", "7.1", "g/dL", "6.0 - 8.3"],
            ["Serum Albumin", "4.2", "g/dL", "3.5 - 5.2"],
        ],
        "ground_truth_tests": [
            {"test_name": "Bilirubin Total", "value": 1.8, "raw_value": "1.8", "unit": "mg/dL", "ref_low": 0.2, "ref_high": 1.2},
            {"test_name": "Bilirubin Direct", "value": 0.6, "raw_value": "0.6", "unit": "mg/dL", "ref_low": 0.0, "ref_high": 0.3},
            {"test_name": "SGOT (AST)", "value": 58.0, "raw_value": "58.0", "unit": "U/L", "ref_low": 5.0, "ref_high": 40.0},
            {"test_name": "SGPT (ALT)", "value": 72.0, "raw_value": "72.0", "unit": "U/L", "ref_low": 7.0, "ref_high": 56.0},
            {"test_name": "Alkaline Phosphatase (ALP)", "value": 95.0, "raw_value": "95.0", "unit": "U/L", "ref_low": 44.0, "ref_high": 147.0},
            {"test_name": "Total Protein", "value": 7.1, "raw_value": "7.1", "unit": "g/dL", "ref_low": 6.0, "ref_high": 8.3},
            {"test_name": "Serum Albumin", "value": 4.2, "raw_value": "4.2", "unit": "g/dL", "ref_low": 3.5, "ref_high": 5.2},
        ],
    },
    # 5. Thyrocare Kidney Function Test (includes non-numeric eGFR ">60")
    {
        "filename_pdf": "thyrocare_kidney.pdf",
        "filename_json": "thyrocare_kidney.json",
        "lab_name": "Thyrocare Technologies Ltd",
        "subtitle": "Renal Panel Analysis Laboratory",
        "patient": {"name": "Kavita Rao", "age": "58", "gender": "Female", "date": "2026-10-27", "id": "67329"},
        "headers": ["Test Description", "Observed Value", "Units", "Reference Range"],
        "rows": [
            ["Blood Urea Nitrogen (BUN)", "24.0", "mg/dL", "7.0 - 20.0"],
            ["Serum Creatinine", "1.45", "mg/dL", "0.60 - 1.20"],
            ["Uric Acid", "6.2", "mg/dL", "3.5 - 7.2"],
            ["eGFR (Estimated)", "> 60", "mL/min/1.73m²", "> 60"],
            ["BUN / Creatinine Ratio", "16.5", "Ratio", "10.0 - 20.0"],
        ],
        "ground_truth_tests": [
            {"test_name": "Blood Urea Nitrogen (BUN)", "value": 24.0, "raw_value": "24.0", "unit": "mg/dL", "ref_low": 7.0, "ref_high": 20.0},
            {"test_name": "Serum Creatinine", "value": 1.45, "raw_value": "1.45", "unit": "mg/dL", "ref_low": 0.60, "ref_high": 1.20},
            {"test_name": "Uric Acid", "value": 6.2, "raw_value": "6.2", "unit": "mg/dL", "ref_low": 3.5, "ref_high": 7.2},
            {"test_name": "eGFR (Estimated)", "value": 60.0, "raw_value": "> 60", "unit": "mL/min/1.73m²", "ref_low": 60.0, "ref_high": None},
            {"test_name": "BUN / Creatinine Ratio", "value": 16.5, "raw_value": "16.5", "unit": "Ratio", "ref_low": 10.0, "ref_high": 20.0},
        ],
    },
    # 6. SRL Diabetes Panel
    {
        "filename_pdf": "srl_diabetes.pdf",
        "filename_json": "srl_diabetes.json",
        "lab_name": "SRL Diagnostics",
        "subtitle": "Metabolic Disorders & Glycemic Monitoring Unit",
        "patient": {"name": "Ramesh Gupta", "age": "50", "gender": "Male", "date": "2026-10-29", "id": "31002"},
        "headers": ["Test Name", "Result", "Units", "Reference Range"],
        "rows": [
            ["Fasting Blood Glucose", "138.0", "mg/dL", "70.0 - 99.0"],
            ["Post Prandial Glucose", "215.0", "mg/dL", "70.0 - 140.0"],
            ["HbA1c (Glycated Hemoglobin)", "8.2", "%", "4.0 - 5.6"],
            ["Estimated Average Glucose (eAG)", "189.0", "mg/dL", "70.0 - 126.0"],
        ],
        "ground_truth_tests": [
            {"test_name": "Fasting Blood Glucose", "value": 138.0, "raw_value": "138.0", "unit": "mg/dL", "ref_low": 70.0, "ref_high": 99.0},
            {"test_name": "Post Prandial Glucose", "value": 215.0, "raw_value": "215.0", "unit": "mg/dL", "ref_low": 70.0, "ref_high": 140.0},
            {"test_name": "HbA1c (Glycated Hemoglobin)", "value": 8.2, "raw_value": "8.2", "unit": "%", "ref_low": 4.0, "ref_high": 5.6},
            {"test_name": "Estimated Average Glucose (eAG)", "value": 189.0, "raw_value": "189.0", "unit": "mg/dL", "ref_low": 70.0, "ref_high": 126.0},
        ],
    },
    # 7. Multipage Full Body Checkup
    {
        "filename_pdf": "multipage_full_body.pdf",
        "filename_json": "multipage_full_body.json",
        "lab_name": "Apollo Diagnostics Central Lab",
        "subtitle": "Comprehensive Executive Health Profile",
        "patient": {"name": "Meera Iyer", "age": "48", "gender": "Female", "date": "2026-11-01", "id": "77109"},
        "headers": ["Investigation", "Value", "Unit", "Biological Ref Range"],
        "multipage": True,
        "rows": [
            ["Hemoglobin", "13.1", "g/dL", "12.0 - 15.0"],
            ["WBC Count", "7,200", "cells/cumm", "4000 - 11000"],
            ["Platelet Count", "210000", "cells/cumm", "150000 - 450000"],
            ["Total Cholesterol", "212.0", "mg/dL", "< 200"],
            ["Triglycerides", "142.0", "mg/dL", "< 150"],
            ["HDL Cholesterol", "56.0", "mg/dL", "> 50"],
            ["Fasting Glucose", "94.0", "mg/dL", "70.0 - 99.0"],
            ["Serum Creatinine", "0.85", "mg/dL", "0.60 - 1.10"],
            ["Blood Urea", "22.0", "mg/dL", "15.0 - 40.0"],
            ["SGPT (ALT)", "28.0", "U/L", "7.0 - 56.0"],
            ["TSH", "3.20", "µIU/mL", "0.45 - 4.50"],
            ["Vitamin D (25-OH)", "18.5", "ng/mL", "30.0 - 100.0"],
            ["Vitamin B12", "380.0", "pg/mL", "211.0 - 911.0"],
        ],
        "ground_truth_tests": [
            {"test_name": "Hemoglobin", "value": 13.1, "raw_value": "13.1", "unit": "g/dL", "ref_low": 12.0, "ref_high": 15.0},
            {"test_name": "WBC Count", "value": 7200.0, "raw_value": "7,200", "unit": "cells/cumm", "ref_low": 4000.0, "ref_high": 11000.0},
            {"test_name": "Platelet Count", "value": 210000.0, "raw_value": "210000", "unit": "cells/cumm", "ref_low": 150000.0, "ref_high": 450000.0},
            {"test_name": "Total Cholesterol", "value": 212.0, "raw_value": "212.0", "unit": "mg/dL", "ref_low": None, "ref_high": 200.0},
            {"test_name": "Triglycerides", "value": 142.0, "raw_value": "142.0", "unit": "mg/dL", "ref_low": None, "ref_high": 150.0},
            {"test_name": "HDL Cholesterol", "value": 56.0, "raw_value": "56.0", "unit": "mg/dL", "ref_low": 50.0, "ref_high": None},
            {"test_name": "Fasting Glucose", "value": 94.0, "raw_value": "94.0", "unit": "mg/dL", "ref_low": 70.0, "ref_high": 99.0},
            {"test_name": "Serum Creatinine", "value": 0.85, "raw_value": "0.85", "unit": "mg/dL", "ref_low": 0.60, "ref_high": 1.10},
            {"test_name": "Blood Urea", "value": 22.0, "raw_value": "22.0", "unit": "mg/dL", "ref_low": 15.0, "ref_high": 40.0},
            {"test_name": "SGPT (ALT)", "value": 28.0, "raw_value": "28.0", "unit": "U/L", "ref_low": 7.0, "ref_high": 56.0},
            {"test_name": "TSH", "value": 3.20, "raw_value": "3.20", "unit": "µIU/mL", "ref_low": 0.45, "ref_high": 4.50},
            {"test_name": "Vitamin D (25-OH)", "value": 18.5, "raw_value": "18.5", "unit": "ng/mL", "ref_low": 30.0, "ref_high": 100.0},
            {"test_name": "Vitamin B12", "value": 380.0, "raw_value": "380.0", "unit": "pg/mL", "ref_low": 211.0, "ref_high": 911.0},
        ],
    },
    # 8. Complex Borders Report (Ideal for Camelot lattice test)
    {
        "filename_pdf": "complex_borders.pdf",
        "filename_json": "complex_borders.json",
        "lab_name": "Max Healthcare Pathology",
        "subtitle": "Department of Laboratory Medicine",
        "patient": {"name": "Deepak Joshi", "age": "39", "gender": "Male", "date": "2026-11-03", "id": "55018"},
        "headers": ["Analyte", "Result", "Units", "Biological Reference"],
        "complex_borders": True,
        "rows": [
            ["Serum Calcium", "9.4", "mg/dL", "8.5 - 10.5"],
            ["Serum Phosphorus", "3.6", "mg/dL", "2.5 - 4.5"],
            ["Serum Magnesium", "2.1", "mg/dL", "1.7 - 2.4"],
            ["Serum Iron", "85.0", "µg/dL", "60.0 - 170.0"],
            ["Total Iron Binding Capacity (TIBC)", "320.0", "µg/dL", "240.0 - 450.0"],
            ["Ferritin", "45.0", "ng/mL", "20.0 - 250.0"],
        ],
        "ground_truth_tests": [
            {"test_name": "Serum Calcium", "value": 9.4, "raw_value": "9.4", "unit": "mg/dL", "ref_low": 8.5, "ref_high": 10.5},
            {"test_name": "Serum Phosphorus", "value": 3.6, "raw_value": "3.6", "unit": "mg/dL", "ref_low": 2.5, "ref_high": 4.5},
            {"test_name": "Serum Magnesium", "value": 2.1, "raw_value": "2.1", "unit": "mg/dL", "ref_low": 1.7, "ref_high": 2.4},
            {"test_name": "Serum Iron", "value": 85.0, "raw_value": "85.0", "unit": "µg/dL", "ref_low": 60.0, "ref_high": 170.0},
            {"test_name": "Total Iron Binding Capacity (TIBC)", "value": 320.0, "raw_value": "320.0", "unit": "µg/dL", "ref_low": 240.0, "ref_high": 450.0},
            {"test_name": "Ferritin", "value": 45.0, "raw_value": "45.0", "unit": "ng/mL", "ref_low": 20.0, "ref_high": 250.0},
        ],
    },
    # 9. Non-Numeric Laboratory Findings
    {
        "filename_pdf": "non_numeric.pdf",
        "filename_json": "non_numeric.json",
        "lab_name": "Suburban Diagnostics",
        "subtitle": "Clinical Microbiology & Urinalysis Division",
        "patient": {"name": "Anita Desai", "age": "29", "gender": "Female", "date": "2026-11-05", "id": "81203"},
        "headers": ["Investigation", "Observed Result", "Unit", "Biological Reference"],
        "rows": [
            ["Urine Protein", "Trace", "", "Negative"],
            ["Urine Sugar (Glucose)", "Negative", "", "Negative"],
            ["Urine Ketones", "Negative", "", "Negative"],
            ["Urine Bilirubin", "Negative", "", "Negative"],
            ["Hepatitis B Surface Antigen (HBsAg)", "Non-Reactive", "", "Non-Reactive"],
            ["HIV 1 & 2 Antibody Screen", "Non-Reactive", "", "Non-Reactive"],
            ["VDRL / RPR", "Non-Reactive", "", "Non-Reactive"],
        ],
        "ground_truth_tests": [
            {"test_name": "Urine Protein", "value": None, "raw_value": "Trace", "unit": "", "ref_low": None, "ref_high": None},
            {"test_name": "Urine Sugar (Glucose)", "value": None, "raw_value": "Negative", "unit": "", "ref_low": None, "ref_high": None},
            {"test_name": "Urine Ketones", "value": None, "raw_value": "Negative", "unit": "", "ref_low": None, "ref_high": None},
            {"test_name": "Urine Bilirubin", "value": None, "raw_value": "Negative", "unit": "", "ref_low": None, "ref_high": None},
            {"test_name": "Hepatitis B Surface Antigen (HBsAg)", "value": None, "raw_value": "Non-Reactive", "unit": "", "ref_low": None, "ref_high": None},
            {"test_name": "HIV 1 & 2 Antibody Screen", "value": None, "raw_value": "Non-Reactive", "unit": "", "ref_low": None, "ref_high": None},
            {"test_name": "VDRL / RPR", "value": None, "raw_value": "Non-Reactive", "unit": "", "ref_low": None, "ref_high": None},
        ],
    },
    # 10. Scanned Report (CBC with special layout tested with vision fallback)
    {
        "filename_pdf": "scanned_report.pdf",
        "filename_json": "scanned_report.json",
        "lab_name": "Community Health Pathology",
        "subtitle": "General Outpatient Clinical Laboratory",
        "patient": {"name": "Sanjay Mishra", "age": "61", "gender": "Male", "date": "2026-11-07", "id": "11984"},
        "headers": ["Test Name", "Result", "Units", "Normal Range"],
        "rows": [
            ["Hemoglobin", "11.2", "g/dL", "13.0 - 17.0"],
            ["Erythrocyte Sedimentation Rate (ESR)", "35.0", "mm/hr", "0.0 - 15.0"],
            ["C-Reactive Protein (CRP)", "12.4", "mg/L", "< 5.0"],
            ["Serum Creatinine", "1.1", "mg/dL", "0.7 - 1.3"],
        ],
        "ground_truth_tests": [
            {"test_name": "Hemoglobin", "value": 11.2, "raw_value": "11.2", "unit": "g/dL", "ref_low": 13.0, "ref_high": 17.0},
            {"test_name": "Erythrocyte Sedimentation Rate (ESR)", "value": 35.0, "raw_value": "35.0", "unit": "mm/hr", "ref_low": 0.0, "ref_high": 15.0},
            {"test_name": "C-Reactive Protein (CRP)", "value": 12.4, "raw_value": "12.4", "unit": "mg/L", "ref_low": None, "ref_high": 5.0},
            {"test_name": "Serum Creatinine", "value": 1.1, "raw_value": "1.1", "unit": "mg/dL", "ref_low": 0.7, "ref_high": 1.3},
        ],
    },
]


def generate_all():
    """Generate all 10 synthetic PDF reports and ground-truth JSON files."""
    _ensure_dirs()
    print("Generating synthetic laboratory reports and ground truth...")

    for rep in REPORTS_DATA:
        # 1. Build PDF
        pdf_path = build_report_pdf(
            filename=rep["filename_pdf"],
            lab_name=rep["lab_name"],
            subtitle=rep["subtitle"],
            patient_info=rep["patient"],
            table_headers=rep["headers"],
            table_rows=rep["rows"],
            multipage=rep.get("multipage", False),
            complex_borders=rep.get("complex_borders", False),
        )

        # 2. Build Ground Truth JSON
        gt_dict = {
            "patient_name": rep["patient"]["name"],
            "patient_age": rep["patient"]["age"],
            "patient_gender": rep["patient"]["gender"],
            "report_date": rep["patient"]["date"],
            "lab_name": rep["lab_name"],
            "report_type": "blood_test",
            "tests": rep["ground_truth_tests"],
        }
        json_path = save_ground_truth(rep["filename_json"], gt_dict)
        print(f" -> Generated: {pdf_path.name} | Ground Truth: {json_path.name} ({len(rep['ground_truth_tests'])} tests)")

    print(f"Successfully generated {len(REPORTS_DATA)} reports in {REPORTS_DIR}")


if __name__ == "__main__":
    generate_all()
