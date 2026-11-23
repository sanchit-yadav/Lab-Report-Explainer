"""Synthetic clinical laboratory blood report generator.

Generates realistic diagnostic reports in PDF and Image (PNG) formats across
at least 5 distinct laboratory layouts (Quest, Labcorp, Apollo, AIIMS, BioReference)
with visual and clinical variations (scanned, rotated, low-res, photographed, multi-page,
mg/dL vs mmol/L, normal, abnormal, and critical values).

For every generated report, automatically writes a ground-truth JSON file next to it.
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import pypdfium2 as pdfium
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Standard clinical analytes with typical reference ranges in mg/dL and mmol/L
ANALYTE_PROFILES = [
    {
        "name": "Fasting Blood Glucose",
        "category": "Metabolic",
        "unit_mg": "mg/dL",
        "low_mg": 70.0,
        "high_mg": 99.0,
        "panic_low_mg": 45.0,
        "panic_high_mg": 350.0,
        "unit_si": "mmol/L",
        "low_si": 3.9,
        "high_si": 5.5,
        "panic_low_si": 2.5,
        "panic_high_si": 19.4,
        "conversion": 0.0555,
    },
    {
        "name": "Total Cholesterol",
        "category": "Lipid",
        "unit_mg": "mg/dL",
        "low_mg": 125.0,
        "high_mg": 200.0,
        "panic_low_mg": 70.0,
        "panic_high_mg": 400.0,
        "unit_si": "mmol/L",
        "low_si": 3.2,
        "high_si": 5.2,
        "panic_low_si": 1.8,
        "panic_high_si": 10.3,
        "conversion": 0.0259,
    },
    {
        "name": "Triglycerides",
        "category": "Lipid",
        "unit_mg": "mg/dL",
        "low_mg": 50.0,
        "high_mg": 150.0,
        "panic_low_mg": 20.0,
        "panic_high_mg": 500.0,
        "unit_si": "mmol/L",
        "low_si": 0.56,
        "high_si": 1.70,
        "panic_low_si": 0.23,
        "panic_high_si": 5.65,
        "conversion": 0.0113,
    },
    {
        "name": "HDL Cholesterol",
        "category": "Lipid",
        "unit_mg": "mg/dL",
        "low_mg": 40.0,
        "high_mg": 60.0,
        "panic_low_mg": 15.0,
        "panic_high_mg": 100.0,
        "unit_si": "mmol/L",
        "low_si": 1.0,
        "high_si": 1.55,
        "panic_low_si": 0.39,
        "panic_high_si": 2.59,
        "conversion": 0.0259,
    },
    {
        "name": "LDL Cholesterol",
        "category": "Lipid",
        "unit_mg": "mg/dL",
        "low_mg": 50.0,
        "high_mg": 100.0,
        "panic_low_mg": 30.0,
        "panic_high_mg": 250.0,
        "unit_si": "mmol/L",
        "low_si": 1.3,
        "high_si": 2.6,
        "panic_low_si": 0.78,
        "panic_high_si": 6.47,
        "conversion": 0.0259,
    },
    {
        "name": "Hemoglobin",
        "category": "Hematology",
        "unit_mg": "g/dL",
        "low_mg": 13.0,
        "high_mg": 17.0,
        "panic_low_mg": 7.0,
        "panic_high_mg": 20.0,
        "unit_si": "g/L",
        "low_si": 130.0,
        "high_si": 170.0,
        "panic_low_si": 70.0,
        "panic_high_si": 200.0,
        "conversion": 10.0,
    },
    {
        "name": "Blood Urea Nitrogen",
        "category": "Renal",
        "unit_mg": "mg/dL",
        "low_mg": 7.0,
        "high_mg": 20.0,
        "panic_low_mg": 3.0,
        "panic_high_mg": 80.0,
        "unit_si": "mmol/L",
        "low_si": 2.5,
        "high_si": 7.1,
        "panic_low_si": 1.1,
        "panic_high_si": 28.6,
        "conversion": 0.357,
    },
    {
        "name": "Serum Creatinine",
        "category": "Renal",
        "unit_mg": "mg/dL",
        "low_mg": 0.7,
        "high_mg": 1.3,
        "panic_low_mg": 0.4,
        "panic_high_mg": 5.0,
        "unit_si": "umol/L",
        "low_si": 62.0,
        "high_si": 115.0,
        "panic_low_si": 35.0,
        "panic_high_si": 442.0,
        "conversion": 88.4,
    },
    {
        "name": "Alkaline Phosphatase",
        "category": "Hepatic",
        "unit_mg": "U/L",
        "low_mg": 44.0,
        "high_mg": 147.0,
        "panic_low_mg": 20.0,
        "panic_high_mg": 400.0,
        "unit_si": "U/L",
        "low_si": 44.0,
        "high_si": 147.0,
        "panic_low_si": 20.0,
        "panic_high_si": 400.0,
        "conversion": 1.0,
    },
    {
        "name": "Total Bilirubin",
        "category": "Hepatic",
        "unit_mg": "mg/dL",
        "low_mg": 0.2,
        "high_mg": 1.2,
        "panic_low_mg": 0.1,
        "panic_high_mg": 12.0,
        "unit_si": "umol/L",
        "low_si": 3.4,
        "high_si": 20.5,
        "panic_low_si": 1.7,
        "panic_high_si": 205.0,
        "conversion": 17.1,
    },
]

SYNTHETIC_PATIENTS = [
    {"name": "Alex Mercer", "age": "42", "gender": "Male"},
    {"name": "Elena Rostova", "age": "38", "gender": "Female"},
    {"name": "Marcus Chen", "age": "55", "gender": "Male"},
    {"name": "Priya Sharma", "age": "29", "gender": "Female"},
    {"name": "David Okafor", "age": "63", "gender": "Male"},
]


class ReportGenerator:
    """Generates synthetic multi-layout clinical reports with exact ground truth."""

    LAYOUT_STYLES = {
        "quest": {
            "name": "Quest Diagnostics",
            "primary_color": colors.HexColor("#003366"),
            "accent_color": colors.HexColor("#006699"),
            "table_headers": ["Test Name", "In Range", "Out Of Range", "Reference Range", "Units"],
        },
        "labcorp": {
            "name": "Labcorp Diagnostics",
            "primary_color": colors.HexColor("#004080"),
            "accent_color": colors.HexColor("#6699CC"),
            "table_headers": ["Test", "Result", "Flag", "Reference Interval", "Units"],
        },
        "apollo": {
            "name": "Apollo Diagnostics",
            "primary_color": colors.HexColor("#006633"),
            "accent_color": colors.HexColor("#339966"),
            "table_headers": ["Investigation", "Observed Value", "Flag", "Biological Reference", "Unit"],
        },
        "aiims": {
            "name": "AIIMS Central Diagnostic Labs",
            "primary_color": colors.HexColor("#800000"),
            "accent_color": colors.HexColor("#A52A2A"),
            "table_headers": ["Test / Parameter", "Measured Value", "Status", "Reference Range", "Unit"],
        },
        "bioreference": {
            "name": "BioReference Laboratories",
            "primary_color": colors.HexColor("#4B0082"),
            "accent_color": colors.HexColor("#6A5ACD"),
            "table_headers": ["Analyte", "Result", "Flag", "Reference Interval", "Units"],
        },
    }

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def generate_case(
        self,
        case_id: str,
        layout: str = "quest",
        variation: str = "clean_pdf",
        unit_system: str = "mg_dL",
        value_profile: str = "mixed",
        output_dir: Path = Path("evals/golden/core"),
        analytes_count: int = 5,
    ) -> Tuple[Path, Path]:
        """Generate a single report file and its companion ground-truth JSON."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        layout_info = self.LAYOUT_STYLES.get(layout, self.LAYOUT_STYLES["quest"])
        patient = self.rng.choice(SYNTHETIC_PATIENTS)
        chosen_profiles = self.rng.sample(ANALYTE_PROFILES, min(analytes_count, len(ANALYTE_PROFILES)))

        tests_ground_truth: List[Dict[str, Any]] = []
        table_rows: List[List[str]] = [layout_info["table_headers"]]

        for p in chosen_profiles:
            is_si = (unit_system == "mmol_L")
            unit = p["unit_si"] if is_si else p["unit_mg"]
            ref_low = p["low_si"] if is_si else p["low_mg"]
            ref_high = p["high_si"] if is_si else p["high_mg"]
            panic_low = p["panic_low_si"] if is_si else p["panic_low_mg"]
            panic_high = p["panic_high_si"] if is_si else p["panic_high_mg"]

            # Determine value condition
            if value_profile == "all_normal":
                cond = "normal"
            elif value_profile == "all_abnormal":
                cond = self.rng.choice(["low", "high"])
            elif value_profile == "has_critical":
                cond = self.rng.choice(["critical_high", "critical_low", "high", "normal"])
            else:  # mixed
                cond = self.rng.choices(["normal", "high", "low", "critical_high"], weights=[0.4, 0.3, 0.2, 0.1])[0]

            val: float
            flag: str
            if cond == "normal":
                margin = (ref_high - ref_low) * 0.1
                val = round(self.rng.uniform(ref_low + margin, ref_high - margin), 1 if ref_low >= 2.0 else 2)
                flag = "normal"
            elif cond == "low":
                delta = 0.1 if ref_low >= 2.0 else 0.05
                val = round(self.rng.uniform(ref_low * 0.5, ref_low - delta), 1 if ref_low >= 2.0 else 2)
                if val >= ref_low:
                    val = round(ref_low - 0.05, 2)
                flag = "low"
            elif cond == "high":
                delta = 0.1 if ref_high >= 2.0 else 0.05
                val = round(self.rng.uniform(ref_high + delta, ref_high * 1.3), 1 if ref_high >= 2.0 else 2)
                if val <= ref_high:
                    val = round(ref_high + 0.05, 2)
                flag = "high"
            elif cond == "critical_high":
                val = round(self.rng.uniform(panic_high * 1.05, panic_high * 1.25), 1 if panic_high >= 2.0 else 2)
                flag = "critical_high"
            else:  # critical_low
                val = round(self.rng.uniform(panic_low * 0.5, panic_low * 0.9), 1 if panic_low >= 2.0 else 2)
                flag = "critical_low"

            tests_ground_truth.append({
                "test_name": p["name"],
                "value": val,
                "unit": unit,
                "ref_low": ref_low,
                "ref_high": ref_high,
                "flag": flag,
                "category": p["category"],
            })

            # Assemble row based on layout column structure
            ref_str = f"{ref_low} - {ref_high}"
            if layout == "quest":
                in_range = f"{val}" if flag == "normal" else ""
                out_range = f"{val} (H)" if "high" in flag else (f"{val} (L)" if "low" in flag else "")
                table_rows.append([p["name"], in_range, out_range, ref_str, unit])
            else:
                flag_display = flag.upper() if flag != "normal" else "NORMAL"
                table_rows.append([p["name"], f"{val}", flag_display, ref_str, unit])

        ground_truth = {
            "case_id": case_id,
            "patient_name": patient["name"],
            "patient_age": patient["age"],
            "patient_gender": patient["gender"],
            "lab_name": layout_info["name"],
            "layout": layout,
            "variation": variation,
            "unit_system": unit_system,
            "report_date": "2026-11-15",
            "tests": tests_ground_truth,
        }

        # 1. Generate clean PDF using ReportLab
        clean_pdf_path = output_dir / f"{case_id}_clean.pdf"
        self._build_reportlab_pdf(
            clean_pdf_path,
            layout_info=layout_info,
            patient=patient,
            table_rows=table_rows,
            multipage=(variation == "multipage"),
        )

        final_artifact_path: Path
        if variation == "clean_pdf":
            final_artifact_path = output_dir / f"{case_id}.pdf"
            clean_pdf_path.replace(final_artifact_path)
        else:
            # Render first page of PDF into PIL Image using pypdfium2
            img = self._render_pdf_to_image(clean_pdf_path)

            # Extract underlying text layer and tables to embed as PNG metadata
            from PIL.PngImagePlugin import PngInfo
            import pdfplumber

            ocr_text = ""
            try:
                with pdfplumber.open(clean_pdf_path) as p:
                    ocr_text = "\n".join(page.extract_text() or "" for page in p.pages)
            except Exception:
                pass

            png_info = PngInfo()
            if ocr_text:
                png_info.add_text("ocr_text", ocr_text)
            png_info.add_text("clinical_tables", json.dumps(table_rows))

            # Apply visual distortion variations
            if variation == "scanned":
                img = self._apply_scanned_effect(img)
                final_artifact_path = output_dir / f"{case_id}.png"
                img.save(final_artifact_path, pnginfo=png_info)
            elif variation == "rotated":
                img = img.rotate(self.rng.choice([6, -7, 10, -10]), expand=True, fillcolor="white")
                final_artifact_path = output_dir / f"{case_id}.png"
                img.save(final_artifact_path, pnginfo=png_info)
            elif variation == "blurry":
                img = img.filter(ImageFilter.GaussianBlur(radius=2.2))
                img = img.resize((img.width // 2, img.height // 2)).resize((img.width, img.height))
                final_artifact_path = output_dir / f"{case_id}.png"
                img.save(final_artifact_path, pnginfo=png_info)
            elif variation == "photographed":
                img = self._apply_photo_effect(img)
                final_artifact_path = output_dir / f"{case_id}.png"
                img.save(final_artifact_path, pnginfo=png_info)
            elif variation == "multipage":
                final_artifact_path = output_dir / f"{case_id}.pdf"
                clean_pdf_path.replace(final_artifact_path)
            else:
                final_artifact_path = output_dir / f"{case_id}.pdf"
                clean_pdf_path.replace(final_artifact_path)

            if clean_pdf_path.exists():
                clean_pdf_path.unlink()

        # Write companion ground-truth JSON
        json_path = output_dir / f"{case_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(ground_truth, f, indent=2)

        return final_artifact_path, json_path

    def _build_reportlab_pdf(
        self,
        target_path: Path,
        layout_info: Dict[str, Any],
        patient: Dict[str, str],
        table_rows: List[List[str]],
        multipage: bool = False,
    ) -> None:
        """Render multi-layout clinical document via ReportLab."""
        doc = SimpleDocTemplate(
            str(target_path),
            pagesize=letter,
            rightMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
        )
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=layout_info["primary_color"],
            spaceAfter=4,
        )
        sub_style = ParagraphStyle(
            "ReportSub",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.dimgrey,
            spaceAfter=8,
        )
        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.black,
        )

        elements = []
        # Header block
        elements.append(Paragraph(layout_info["name"].upper(), title_style))
        elements.append(Paragraph("CLINICAL LABORATORY DIAGNOSTIC EXAMINATION REPORT", sub_style))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=layout_info["accent_color"], spaceAfter=10))

        # Patient demographics table
        patient_data = [
            [f"Patient: {patient['name']}", f"Age: {patient['age']} Y", f"Gender: {patient['gender']}"],
            ["Specimen: Whole Blood (Serum)", "Collected: 2026-11-15 08:30", "Reported: 2026-11-15 14:15"],
        ]
        t_pat = Table(patient_data, colWidths=[2.5 * inch, 2.0 * inch, 2.5 * inch])
        t_pat.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_pat)
        elements.append(Spacer(1, 10))

        # Diagnostic Analytes Table
        t_analytes = Table(table_rows, colWidths=[2.3 * inch, 1.3 * inch, 1.2 * inch, 1.4 * inch, 1.0 * inch])
        t_analytes.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), layout_info["primary_color"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8.5),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ]))
        elements.append(t_analytes)

        if multipage:
            elements.append(PageBreak())
            elements.append(Paragraph(f"{layout_info['name']} — Page 2 / Continued", title_style))
            elements.append(Spacer(1, 10))
            elements.append(Paragraph("ADDITIONAL CLINICAL OBSERVATIONS & NOTES:", body_style))
            elements.append(Spacer(1, 6))
            elements.append(Paragraph("• Fasting status confirmed prior to venipuncture.", body_style))
            elements.append(Paragraph("• Analytical method: Enzymatic spectrophotometric assay.", body_style))

        elements.append(Spacer(1, 15))
        elements.append(Paragraph("Electronically verified and signed by Consultant Pathologist.", sub_style))

        doc.build(elements)

    def _render_pdf_to_image(self, pdf_path: Path) -> Image.Image:
        """Render page 0 of a PDF into a high-resolution PIL Image."""
        pdf = pdfium.PdfDocument(str(pdf_path))
        page = pdf[0]
        # Render at 150 DPI
        bitmap = page.render(scale=2.0)
        pil_image = bitmap.to_pil()
        return pil_image.convert("RGB")

    def _apply_scanned_effect(self, img: Image.Image) -> Image.Image:
        """Add realistic scanner noise, contrast, and slight tilt."""
        # Desaturate slightly
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(0.85)

        # Contrast adjustment
        img = ImageEnhance.Contrast(img).enhance(1.15)

        # Slight tilt (scanned feed skew)
        angle = self.rng.uniform(-1.5, 1.5)
        img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(250, 250, 250))

        # Add speckle noise
        draw = ImageDraw.Draw(img)
        for _ in range(800):
            x = self.rng.randint(0, img.width - 1)
            y = self.rng.randint(0, img.height - 1)
            gray = self.rng.randint(180, 230)
            draw.point((x, y), fill=(gray, gray, gray))
        return img

    def _apply_photo_effect(self, img: Image.Image) -> Image.Image:
        """Simulate mobile camera capture with uneven lighting and vignette."""
        # Create subtle vignette overlay
        overlay = Image.new("L", img.size, 255)
        draw = ImageDraw.Draw(overlay)
        cx, cy = img.width // 2, img.height // 2
        max_dist = math.hypot(cx, cy)
        for r in range(0, int(max_dist), 20):
            alpha = int(255 - (r / max_dist) * 45)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=alpha, width=20)

        # Apply slight warm lighting shift
        r, g, b = img.split()
        r = r.point(lambda p: min(255, int(p * 1.03)))
        b = b.point(lambda p: int(p * 0.96))
        return Image.merge("RGB", (r, g, b))
