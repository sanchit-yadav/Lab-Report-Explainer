"""PDF export generator for clinical doctor discussion briefs.

Uses ReportLab to generate a clean, professional, patient-centered
Doctor Discussion Brief and Lab Summary PDF.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.explainer.schema import ReportExplanation, TestExplanation
from src.extraction.schema import FlagStatus, LabReport, TestResult

logger = logging.getLogger("pdf_export")

# Register Unicode font for Hindi if available on system
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_OBLIQUE = "Helvetica-Oblique"

try:
    windows_nirmala = Path("C:/Windows/Fonts/Nirmala.ttc")
    if windows_nirmala.exists():
        pdfmetrics.registerFont(TTFont("Nirmala", str(windows_nirmala), subfontIndex=0))
        pdfmetrics.registerFont(TTFont("Nirmala-Bold", str(windows_nirmala), subfontIndex=1))
        # Use Nirmala if rendering Hindi
        HINDI_FONT_AVAILABLE = True
    else:
        HINDI_FONT_AVAILABLE = False
except Exception as e:
    logger.debug(f"Could not register Hindi font: {e}")
    HINDI_FONT_AVAILABLE = False

# Clinical Badge Colors for PDF Table
STATUS_COLORS = {
    FlagStatus.CRITICAL_HIGH: colors.HexColor("#dc2626"),  # Red
    FlagStatus.CRITICAL_LOW: colors.HexColor("#dc2626"),   # Red
    FlagStatus.HIGH: colors.HexColor("#d97706"),           # Amber
    FlagStatus.LOW: colors.HexColor("#d97706"),            # Amber
    FlagStatus.NORMAL: colors.HexColor("#16a34a"),         # Green
    FlagStatus.ABNORMAL: colors.HexColor("#ea580c"),       # Orange
    FlagStatus.UNKNOWN: colors.HexColor("#64748b"),        # Slate
}

STATUS_BG_COLORS = {
    FlagStatus.CRITICAL_HIGH: colors.HexColor("#fee2e2"),
    FlagStatus.CRITICAL_LOW: colors.HexColor("#fee2e2"),
    FlagStatus.HIGH: colors.HexColor("#fef3c7"),
    FlagStatus.LOW: colors.HexColor("#fef3c7"),
    FlagStatus.NORMAL: colors.HexColor("#f0fdf4"),
    FlagStatus.ABNORMAL: colors.HexColor("#ffedd5"),
    FlagStatus.UNKNOWN: colors.HexColor("#f1f5f9"),
}


def generate_doctor_brief_pdf(
    explanation: ReportExplanation,
    lang: str = "en",
) -> bytes:
    """Generate a printable, clinical-grade Doctor Discussion Brief PDF.

    Args:
        explanation: The populated ReportExplanation object.
        lang: Target language code ('en' or 'hi').

    Returns:
        Raw PDF document bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    use_hindi_font = (lang == "hi" and HINDI_FONT_AVAILABLE)
    body_font = "Nirmala" if use_hindi_font else FONT_REGULAR
    bold_font = "Nirmala-Bold" if use_hindi_font else FONT_BOLD

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName=bold_font,
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=12,
    )

    section_heading = ParagraphStyle(
        "DocSection",
        parent=styles["Heading2"],
        fontName=bold_font,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=10,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )

    summary_box_style = ParagraphStyle(
        "SummaryText",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
    )

    disclaimer_style = ParagraphStyle(
        "DocDisclaimer",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#64748b"),
        alignment=1,  # Center
    )

    story = []

    # 1. Header Banner
    header_title = (
        "CLINICAL LAB REPORT — DOCTOR DISCUSSION BRIEF"
        if lang == "en"
        else "लैब रिपोर्ट — डॉक्टर से चर्चा हेतु संक्षिप्त विवरण"
    )
    header_subtitle = (
        "Prepared to facilitate informed, constructive dialogue with your licensed healthcare provider."
        if lang == "en"
        else "आपके योग्य चिकित्सक के साथ परामर्श और चर्चा में सहायता के लिए तैयार किया गया विवरण।"
    )
    story.append(Paragraph(f"<b>{header_title}</b>", title_style))
    story.append(Paragraph(header_subtitle, subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=10))

    # 2. Patient & Report Metadata Bar
    raw_report: Optional[LabReport] = explanation.raw_report
    p_name = explanation.patient_name or (raw_report.patient_name if raw_report else "Patient")
    r_date = explanation.report_date or (raw_report.report_date if raw_report else "Recent")
    lab_name = raw_report.lab_name if raw_report else "Diagnostic Pathology"

    meta_data = [
        [
            Paragraph(f"<b>Patient:</b> {p_name}", body_style),
            Paragraph(f"<b>Date:</b> {r_date}", body_style),
            Paragraph(f"<b>Lab:</b> {lab_name}", body_style),
            Paragraph(f"<b>Parameters:</b> {explanation.total_tests}", body_style),
            Paragraph(f"<b>Out of Range:</b> <font color='#dc2626'><b>{explanation.flagged_count}</b></font>", body_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[1.5 * inch, 1.2 * inch, 1.8 * inch, 1.2 * inch, 1.3 * inch])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # 3. Executive Summary Box
    summary_text = explanation.report_summary_hi if (lang == "hi" and use_hindi_font) else explanation.report_summary_en
    summary_heading = "Executive Summary" if lang == "en" else "रिपोर्ट सारांश"
    summary_data = [
        [
            Paragraph(
                f"<b>{summary_heading}:</b> {summary_text}",
                summary_box_style,
            )
        ]
    ]
    summary_table = Table(summary_data, colWidths=[7.0 * inch])
    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f9ff")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#bae6fd")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ])
    )
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # 4. Analyte Results Table
    story.append(Paragraph("<b>Complete Analyte Summary</b>", section_heading))

    table_headers = [
        Paragraph("<b>Investigation</b>", body_style),
        Paragraph("<b>Observed</b>", body_style),
        Paragraph("<b>Unit</b>", body_style),
        Paragraph("<b>Reference Interval</b>", body_style),
        Paragraph("<b>Status</b>", body_style),
    ]
    table_rows = [table_headers]

    tests_to_display: List[TestResult] = []
    if raw_report and raw_report.tests:
        tests_to_display = raw_report.tests
    else:
        for exp in explanation.test_explanations:
            tests_to_display.append(
                TestResult(test_name=exp.test_name, value=0.0, flag=exp.flag)
            )

    # Sort with out-of-range first
    flag_order = {
        FlagStatus.CRITICAL_HIGH: 0,
        FlagStatus.CRITICAL_LOW: 0,
        FlagStatus.HIGH: 1,
        FlagStatus.LOW: 1,
        FlagStatus.ABNORMAL: 2,
        FlagStatus.UNKNOWN: 3,
        FlagStatus.NORMAL: 4,
    }
    sorted_tests = sorted(tests_to_display, key=lambda t: flag_order.get(t.flag, 5))

    row_styles = []
    for idx, test in enumerate(sorted_tests, start=1):
        status_color = STATUS_COLORS.get(test.flag, colors.HexColor("#475569"))
        status_name = test.flag.value.upper().replace("_", " ")

        ref_str = test.ref_raw or (
            f"{test.ref_low} - {test.ref_high}" if test.ref_low is not None and test.ref_high is not None else "N/A"
        )
        val_str = str(test.raw_value or (test.value if test.value is not None else "N/A"))

        # Colored text for status
        status_para = Paragraph(f"<font color='{status_color.hexval()}'><b>{status_name}</b></font>", body_style)

        table_rows.append([
            Paragraph(f"<b>{test.test_name}</b>", body_style),
            Paragraph(f"<b>{val_str}</b>", body_style),
            Paragraph(test.unit or "-", body_style),
            Paragraph(ref_str, body_style),
            status_para,
        ])

        # Light background for abnormal rows
        if test.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN):
            row_styles.append(("BACKGROUND", (0, idx), (-1, idx), STATUS_BG_COLORS.get(test.flag, colors.white)))

    analyte_table = Table(table_rows, colWidths=[2.3 * inch, 1.1 * inch, 1.0 * inch, 1.4 * inch, 1.2 * inch])
    base_table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
    ] + row_styles
    analyte_table.setStyle(TableStyle(base_table_style))
    story.append(analyte_table)
    story.append(Spacer(1, 14))

    # 5. Targeted Findings & Questions for the Doctor
    if explanation.test_explanations:
        q_heading = (
            "Targeted Doctor Discussion Questions"
            if lang == "en"
            else "डॉक्टर से पूछे जाने वाले लक्षित प्रश्न"
        )
        story.append(Paragraph(f"<b>{q_heading}</b>", section_heading))

        for exp in explanation.test_explanations:
            status_color = STATUS_COLORS.get(exp.flag, colors.HexColor("#475569"))
            status_name = exp.flag.value.upper().replace("_", " ")

            exp_text = exp.explanation_hi if (lang == "hi" and use_hindi_font) else exp.explanation_en

            finding_box = [
                [
                    Paragraph(
                        f"<b>{exp.test_name}</b> (<font color='{status_color.hexval()}'><b>{status_name}</b></font>):<br/>"
                        f"{exp_text}",
                        body_style,
                    )
                ]
            ]
            f_table = Table(finding_box, colWidths=[7.0 * inch])
            f_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ])
            )
            story.append(f_table)
            story.append(Spacer(1, 4))

            # Doctor questions bullets
            for q in exp.doctor_questions:
                q_para = Paragraph(f"• <i>{q}</i>", body_style)
                story.append(q_para)

            story.append(Spacer(1, 8))

    # 6. Global Mandatory Clinical Disclaimer Footer
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#94a3b8"), spaceAfter=8))
    disclaimer_text = (
        "CONFIDENTIAL MEDICAL EDUCATION SUMMARY: This document was prepared by the AI Clinical Lab Report Explainer "
        "solely to help patients understand laboratory metrics and facilitate informed discussions with their doctor. "
        "It DOES NOT provide a clinical diagnosis, evaluate disease prognosis, or prescribe medications. "
        "Always review all laboratory results and treatment plans with your licensed physician."
    )
    story.append(Paragraph(disclaimer_text, disclaimer_style))

    doc.build(story)
    return buffer.getvalue()
