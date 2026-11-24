"""Synthetic Scanned Laboratory Report Fixture Generator.

Creates realistic, fully anonymized synthetic lab reports in various degraded/scanned formats:
1. Image-only PDF (no text layer)
2. Noisy / photographed image (PNG with Gaussian noise and luminance artifacts)
3. Rotated image (PNG rotated 90 degrees)
4. Skewed image (PNG tilted by 7 degrees)
5. Low-resolution image (PNG downsampled to low DPI)
6. Multi-page image-only PDF (2 pages, no text layer)

Each fixture has an identical ground-truth JSON file alongside it.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont


FIXTURES_DIR = Path(__file__).parent / "scanned"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def draw_table_page(
    title: str,
    patient_name: str,
    rows: list[dict],
    page_num: int = 1,
    total_pages: int = 1,
    width: int = 1240,   # ~150 DPI A4
    height: int = 1754,
) -> Image.Image:
    """Renders a realistic synthetic laboratory report page with clean tabular typography."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Optional default font
    try:
        font_title = ImageFont.truetype("arial.ttf", 32)
        font_header = ImageFont.truetype("arial.ttf", 20)
        font_body = ImageFont.truetype("arial.ttf", 20)
        font_small = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font_title = ImageFont.load_default()
        font_header = font_title
        font_body = font_title
        font_small = font_title

    # Header banner
    draw.rectangle([(60, 40), (width - 60, 110)], fill=(245, 247, 250), outline=(200, 205, 215), width=2)
    draw.text((80, 55), "METROPOLITAN CLINICAL LABORATORY (SYNTHETIC)", fill=(20, 35, 60), font=font_title)
    draw.text((80, 92), "Accreditation: CLIA / CAP Synthetic Benchmark | Automated Hematology & Chemistry", fill=(100, 115, 130), font=font_small)

    # Patient Details Bar
    draw.rectangle([(60, 130), (width - 60, 210)], outline=(220, 225, 230), width=1)
    draw.text((80, 145), f"Patient Name: {patient_name}", fill=(30, 40, 50), font=font_header)
    draw.text((80, 175), f"Patient ID: SYNTH-{abs(hash(patient_name)) % 1000000:06d}   Age: 42 Y   Sex: M", fill=(80, 90, 100), font=font_body)
    draw.text((width - 320, 145), f"Report Date: 2026-11-20", fill=(50, 60, 70), font=font_body)
    draw.text((width - 320, 175), f"Page: {page_num} of {total_pages}", fill=(80, 90, 100), font=font_body)

    # Table Title
    draw.text((60, 235), title.upper(), fill=(15, 23, 42), font=font_header)

    # Table Header
    y_start = 275
    row_height = 45
    draw.rectangle([(60, y_start), (width - 60, y_start + row_height)], fill=(230, 235, 245), outline=(180, 190, 205), width=1)
    draw.text((80, y_start + 12), "INVESTIGATION / TEST NAME", fill=(15, 23, 42), font=font_header)
    draw.text((550, y_start + 12), "RESULT", fill=(15, 23, 42), font=font_header)
    draw.text((720, y_start + 12), "UNIT", fill=(15, 23, 42), font=font_header)
    draw.text((870, y_start + 12), "REFERENCE RANGE", fill=(15, 23, 42), font=font_header)
    draw.text((1100, y_start + 12), "FLAG", fill=(15, 23, 42), font=font_header)

    y = y_start + row_height
    for idx, row in enumerate(rows):
        bg_col = (255, 255, 255) if idx % 2 == 0 else (248, 250, 252)
        draw.rectangle([(60, y), (width - 60, y + row_height)], fill=bg_col, outline=(226, 232, 240), width=1)

        draw.text((80, y + 12), row["test_name"], fill=(15, 23, 42), font=font_body)
        draw.text((550, y + 12), str(row["value"]), fill=(15, 23, 42), font=font_body)
        draw.text((720, y + 12), row["unit"], fill=(71, 85, 105), font=font_body)

        ref_str = f"{row['ref_low']} - {row['ref_high']}" if row['ref_low'] is not None and row['ref_high'] is not None else ""
        draw.text((870, y + 12), ref_str, fill=(71, 85, 105), font=font_body)

        flag = row.get("flag", "normal").upper()
        flag_col = (220, 38, 38) if flag in ("HIGH", "LOW", "CRITICAL") else (22, 101, 52)
        draw.text((1100, y + 12), flag if flag != "NORMAL" else "", fill=flag_col, font=font_body)

        y += row_height

    # Footer Disclaimer
    draw.line([(60, height - 100), (width - 60, height - 100)], fill=(200, 205, 215), width=1)
    draw.text((60, height - 80), "SYNTHETIC TEST BENCHMARK • FOR AI VALIDATION AND EVALUATION ONLY • NOT A REAL PATIENT REPORT", fill=(120, 130, 140), font=font_small)

    return img


def add_gaussian_noise(image: Image.Image, sigma: float = 25.0) -> Image.Image:
    """Adds realistic photographic noise and uneven lighting."""
    arr = np.array(image).astype(np.float32)
    noise = np.random.normal(0, sigma, arr.shape)
    # Add non-uniform gradient (simulating shadow / phone camera angle)
    h, w, _ = arr.shape
    y_grad = np.linspace(-15, 15, h)[:, None, None]
    noisy_arr = np.clip(arr + noise + y_grad, 0, 255).astype(np.uint8)
    return Image.fromarray(noisy_arr)


def add_skew(image: Image.Image, angle_degrees: float = 7.0) -> Image.Image:
    """Rotates image slightly simulating a crooked document scanner feed."""
    return image.rotate(angle_degrees, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255))


def generate_all_fixtures():
    # --------------------------------------------------------------------------
    # Fixture 1: Clean Scanned Image-Only PDF (Complete Blood Count)
    # --------------------------------------------------------------------------
    cbc_rows = [
        {"test_name": "Hemoglobin", "value": 14.2, "unit": "g/dL", "ref_low": 13.0, "ref_high": 17.0, "flag": "normal"},
        {"test_name": "White Blood Cell Count", "value": 11.5, "unit": "10^3/uL", "ref_low": 4.0, "ref_high": 10.0, "flag": "high"},
        {"test_name": "Platelets", "value": 130.0, "unit": "10^3/uL", "ref_low": 150.0, "ref_high": 450.0, "flag": "low"},
        {"test_name": "Fasting Blood Glucose", "value": 105.0, "unit": "mg/dL", "ref_low": 70.0, "ref_high": 99.0, "flag": "high"},
    ]
    img1 = draw_table_page("Complete Blood Count (CBC) & Metabolic", "Synthetic Patient A", cbc_rows)
    # Save as image-only PDF (no text layer)
    pdf_path_1 = FIXTURES_DIR / "scanned_clean.pdf"
    img1.save(pdf_path_1, "PDF", resolution=150.0)
    with open(FIXTURES_DIR / "scanned_clean.json", "w", encoding="utf-8") as f:
        json.dump({
            "fixture_id": "scanned_clean",
            "condition": "image_only_pdf",
            "patient_name": "Synthetic Patient A",
            "total_pages": 1,
            "tests": cbc_rows,
        }, f, indent=2)

    # --------------------------------------------------------------------------
    # Fixture 2: Noisy / Photographed PNG (Lipid Panel)
    # --------------------------------------------------------------------------
    lipid_rows = [
        {"test_name": "Total Cholesterol", "value": 225.0, "unit": "mg/dL", "ref_low": 125.0, "ref_high": 200.0, "flag": "high"},
        {"test_name": "Triglycerides", "value": 160.0, "unit": "mg/dL", "ref_low": 50.0, "ref_high": 150.0, "flag": "high"},
        {"test_name": "HDL Cholesterol", "value": 45.0, "unit": "mg/dL", "ref_low": 40.0, "ref_high": 60.0, "flag": "normal"},
        {"test_name": "LDL Cholesterol", "value": 148.0, "unit": "mg/dL", "ref_low": 0.0, "ref_high": 100.0, "flag": "high"},
    ]
    img2 = draw_table_page("Standard Lipid Profile", "Synthetic Patient B", lipid_rows)
    img2_noisy = add_gaussian_noise(img2, sigma=20.0)
    img2_noisy.save(FIXTURES_DIR / "scanned_noisy.png", "PNG")
    with open(FIXTURES_DIR / "scanned_noisy.json", "w", encoding="utf-8") as f:
        json.dump({
            "fixture_id": "scanned_noisy",
            "condition": "photographed_noisy",
            "patient_name": "Synthetic Patient B",
            "total_pages": 1,
            "tests": lipid_rows,
        }, f, indent=2)

    # --------------------------------------------------------------------------
    # Fixture 3: Rotated 90 Degrees PNG (Renal Function Panel)
    # --------------------------------------------------------------------------
    renal_rows = [
        {"test_name": "Serum Creatinine", "value": 1.1, "unit": "mg/dL", "ref_low": 0.7, "ref_high": 1.3, "flag": "normal"},
        {"test_name": "Blood Urea Nitrogen", "value": 24.0, "unit": "mg/dL", "ref_low": 7.0, "ref_high": 20.0, "flag": "high"},
        {"test_name": "Sodium", "value": 138.0, "unit": "mmol/L", "ref_low": 136.0, "ref_high": 145.0, "flag": "normal"},
        {"test_name": "Potassium", "value": 5.6, "unit": "mmol/L", "ref_low": 3.5, "ref_high": 5.1, "flag": "high"},
    ]
    img3 = draw_table_page("Renal Function & Electrolytes", "Synthetic Patient C", renal_rows)
    img3_rotated = img3.rotate(270, expand=True)  # 90 degrees clockwise (270 counter-clockwise)
    img3_rotated.save(FIXTURES_DIR / "scanned_rotated.png", "PNG")
    with open(FIXTURES_DIR / "scanned_rotated.json", "w", encoding="utf-8") as f:
        json.dump({
            "fixture_id": "scanned_rotated",
            "condition": "rotated_90_deg",
            "patient_name": "Synthetic Patient C",
            "total_pages": 1,
            "tests": renal_rows,
        }, f, indent=2)

    # --------------------------------------------------------------------------
    # Fixture 4: Skewed PNG (Liver Function Tests)
    # --------------------------------------------------------------------------
    liver_rows = [
        {"test_name": "ALT", "value": 55.0, "unit": "U/L", "ref_low": 7.0, "ref_high": 56.0, "flag": "normal"},
        {"test_name": "AST", "value": 68.0, "unit": "U/L", "ref_low": 10.0, "ref_high": 40.0, "flag": "high"},
        {"test_name": "Total Bilirubin", "value": 1.4, "unit": "mg/dL", "ref_low": 0.2, "ref_high": 1.2, "flag": "high"},
        {"test_name": "Albumin", "value": 4.2, "unit": "g/dL", "ref_low": 3.5, "ref_high": 5.0, "flag": "normal"},
    ]
    img4 = draw_table_page("Hepatic Function Panel", "Synthetic Patient D", liver_rows)
    img4_skewed = add_skew(img4, angle_degrees=7.5)
    img4_skewed.save(FIXTURES_DIR / "scanned_skewed.png", "PNG")
    with open(FIXTURES_DIR / "scanned_skewed.json", "w", encoding="utf-8") as f:
        json.dump({
            "fixture_id": "scanned_skewed",
            "condition": "skewed_7_deg",
            "patient_name": "Synthetic Patient D",
            "total_pages": 1,
            "tests": liver_rows,
        }, f, indent=2)

    # --------------------------------------------------------------------------
    # Fixture 5: Low-Resolution PNG (Thyroid Panel)
    # --------------------------------------------------------------------------
    thyroid_rows = [
        {"test_name": "TSH", "value": 4.8, "unit": "uIU/mL", "ref_low": 0.4, "ref_high": 4.0, "flag": "high"},
        {"test_name": "Free T4", "value": 1.1, "unit": "ng/dL", "ref_low": 0.8, "ref_high": 1.8, "flag": "normal"},
        {"test_name": "Total T3", "value": 110.0, "unit": "ng/dL", "ref_low": 80.0, "ref_high": 200.0, "flag": "normal"},
    ]
    img5 = draw_table_page("Thyroid Function Panel", "Synthetic Patient E", thyroid_rows)
    # Downsample to low-res (e.g. 1/3 scale) then scale back up
    low_w, low_h = img5.width // 3, img5.height // 3
    img5_low = img5.resize((low_w, low_h), Image.Resampling.BILINEAR).resize((img5.width, img5.height), Image.Resampling.NEAREST)
    img5_low.save(FIXTURES_DIR / "scanned_lowres.png", "PNG")
    with open(FIXTURES_DIR / "scanned_lowres.json", "w", encoding="utf-8") as f:
        json.dump({
            "fixture_id": "scanned_lowres",
            "condition": "low_resolution_downsampled",
            "patient_name": "Synthetic Patient E",
            "total_pages": 1,
            "tests": thyroid_rows,
        }, f, indent=2)

    # --------------------------------------------------------------------------
    # Fixture 6: Multi-Page Image-Only PDF (2 Pages)
    # --------------------------------------------------------------------------
    p1_rows = [
        {"test_name": "Hemoglobin", "value": 13.5, "unit": "g/dL", "ref_low": 12.0, "ref_high": 15.5, "flag": "normal"},
        {"test_name": "Hematocrit", "value": 41.0, "unit": "%", "ref_low": 36.0, "ref_high": 46.0, "flag": "normal"},
    ]
    p2_rows = [
        {"test_name": "Serum Calcium", "value": 9.4, "unit": "mg/dL", "ref_low": 8.5, "ref_high": 10.2, "flag": "normal"},
        {"test_name": "Total Protein", "value": 7.1, "unit": "g/dL", "ref_low": 6.4, "ref_high": 8.3, "flag": "normal"},
    ]
    img_p1 = draw_table_page("Complete Blood Count (Page 1)", "Synthetic Patient F", p1_rows, page_num=1, total_pages=2)
    img_p2 = draw_table_page("Comprehensive Metabolic (Page 2)", "Synthetic Patient F", p2_rows, page_num=2, total_pages=2)

    pdf_multi_path = FIXTURES_DIR / "scanned_multipage.pdf"
    img_p1.save(pdf_multi_path, "PDF", resolution=150.0, save_all=True, append_images=[img_p2])

    with open(FIXTURES_DIR / "scanned_multipage.json", "w", encoding="utf-8") as f:
        json.dump({
            "fixture_id": "scanned_multipage",
            "condition": "multipage_image_only_pdf",
            "patient_name": "Synthetic Patient F",
            "total_pages": 2,
            "tests": p1_rows + p2_rows,
        }, f, indent=2)

    print(f"Generated 6 synthetic scanned fixtures in {FIXTURES_DIR}")


if __name__ == "__main__":
    generate_all_fixtures()
