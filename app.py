"""AI Clinical Lab Report Explainer — Streamlit Web Application.

Industry-grade Clinical Decision Support (CDS) & Laboratory Diagnostic Explainer.
Features:
- Public SaaS Landing Page with Linear/Stripe design aesthetics.
- Interactive Synthetic Live Demo Preview with visual range gauges.
- Split-Layout Sign In & Sign Up pages with client validation.
- Authenticated Clinical Dashboard with persistent SQLite report history.
- Multi-tier PDF/OCR extraction with Human-in-the-Loop review editor.
- Deterministic reference interval flagging & MedlinePlus RAG clinical grounding.
- Bilingual output (English default + Hindi toggle).
- One-click Doctor Discussion Brief PDF generation and grounded Q&A chat.
"""

from __future__ import annotations

from datetime import datetime
import io
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.frontend.api_client import CDSAPIClient

PROJECT_ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_reports"

SAMPLE_OPTIONS = {
    "SRL Lipid Panel (Lipid Profile)": "srl_lipid_panel.pdf",
    "Thyrocare CBC (Complete Blood Count)": "thyrocare_cbc.pdf",
    "Metropolis Liver Function Test (LFT)": "metropolis_liver.pdf",
    "Thyrocare Kidney Function Test (KFT)": "thyrocare_kidney.pdf",
    "SRL Diabetes & Glycemic Panel": "srl_diabetes.pdf",
    "Dr. Lal PathLabs Thyroid Profile": "lal_pathlabs_thyroid.pdf",
    "Max Healthcare Full Body Checkup (Multi-Page)": "multipage_full_body.pdf",
    "Apollo Diagnostics Serology (Non-Numeric)": "non_numeric.pdf",
}

FLAG_COLORS = {
    FlagStatus.CRITICAL_HIGH: "#dc2626",  # Red
    FlagStatus.CRITICAL_LOW: "#dc2626",   # Red
    FlagStatus.HIGH: "#d97706",           # Amber
    FlagStatus.LOW: "#d97706",            # Amber
    FlagStatus.NORMAL: "#16a34a",         # Green
    FlagStatus.ABNORMAL: "#ea580c",       # Orange
    FlagStatus.UNKNOWN: "#64748b",        # Slate
}

FLAG_BADGES = {
    FlagStatus.CRITICAL_HIGH: ("CRITICAL HIGH", "🔴", "#fef2f2", "#b91c1c", "#fca5a5"),
    FlagStatus.CRITICAL_LOW: ("CRITICAL LOW", "🔴", "#fef2f2", "#b91c1c", "#fca5a5"),
    FlagStatus.HIGH: ("HIGH", "🟡", "#fffbeb", "#b45309", "#fcd34d"),
    FlagStatus.LOW: ("LOW", "🟡", "#fffbeb", "#b45309", "#fcd34d"),
    FlagStatus.NORMAL: ("NORMAL", "🟢", "#f0fdf4", "#15803d", "#86efac"),
    FlagStatus.ABNORMAL: ("ABNORMAL", "🟠", "#fff7ed", "#c2410c", "#fdba74"),
    FlagStatus.UNKNOWN: ("INCONCLUSIVE", "⚪", "#f8fafc", "#475569", "#cbd5e1"),
}


def _clean_html_str(html_text: str) -> str:
    """Strip leading indentation from multiline HTML templates to prevent markdown code block glitches."""
    return "\n".join(line.lstrip() for line in html_text.strip().splitlines())


def render_range_gauge_html(test: TestResult) -> str:
    """Generate an intuitive visual horizontal range gauge for a numeric analyte."""
    if test.value is None or (test.ref_low is None and test.ref_high is None):
        return ""

    val = test.value
    low = test.ref_low
    high = test.ref_high

    # Two-sided interval [low, high]
    if low is not None and high is not None and high > low:
        span = high - low
        d_min = max(0.0, low - span * 0.6)
        d_max = high + span * 0.6
        if val < d_min:
            d_min = max(0.0, val * 0.85)
        if val > d_max:
            d_max = val * 1.15

        total = d_max - d_min
        if total <= 0:
            return ""

        p_low = max(5.0, ((low - d_min) / total) * 100)
        p_norm = max(10.0, ((high - low) / total) * 100)
        p_high = max(5.0, 100.0 - p_low - p_norm)
        p_val = max(2.0, min(97.0, ((val - d_min) / total) * 100))

        if test.flag in (FlagStatus.CRITICAL_HIGH, FlagStatus.CRITICAL_LOW):
            marker_color = "#dc2626"
        elif test.flag in (FlagStatus.HIGH, FlagStatus.LOW):
            marker_color = "#d97706"
        else:
            marker_color = "#16a34a"

        return _clean_html_str(
            f"""
            <div style="margin-top: 10px; margin-bottom: 6px; padding: 0 4px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 3px;">
                    <span>Min: {d_min:.1f}</span>
                    <span style="color: #15803d; font-weight: 600;">Optimal Range: {low} - {high} {test.unit}</span>
                    <span>Max: {d_max:.1f}</span>
                </div>
                <div style="position: relative; height: 12px; background: #e2e8f0; border-radius: 6px; overflow: visible; display: flex;">
                    <div style="width: {p_low:.1f}%; background: #fef08a; border-top-left-radius: 6px; border-bottom-left-radius: 6px;" title="Low zone (< {low})"></div>
                    <div style="width: {p_norm:.1f}%; background: #86efac;" title="Normal optimal range ({low} - {high})"></div>
                    <div style="width: {p_high:.1f}%; background: #fca5a5; border-top-right-radius: 6px; border-bottom-right-radius: 6px;" title="High zone (> {high})"></div>
                    <div style="position: absolute; left: {p_val:.1f}%; top: -4px; width: 4px; height: 20px; background: {marker_color}; border: 1.5px solid #ffffff; border-radius: 2px; box-shadow: 0 1px 4px rgba(0,0,0,0.4); transform: translateX(-50%); z-index: 10;" title="Patient Result: {val} {test.unit}"></div>
                </div>
                <div style="position: relative; height: 16px; margin-top: 2px;">
                    <span style="position: absolute; left: {p_val:.1f}%; transform: translateX(-50%); font-size: 11px; font-weight: 700; color: {marker_color};">
                        ▲ {val}
                    </span>
                </div>
            </div>
            """
        )

    # One-sided upper bound (< high)
    if high is not None and low is None:
        d_min = 0.0
        d_max = max(val * 1.25, high * 1.5)
        total = d_max - d_min
        if total <= 0:
            return ""

        p_norm = max(10.0, (high / total) * 100)
        p_high = max(5.0, 100.0 - p_norm)
        p_val = max(2.0, min(97.0, (val / total) * 100))
        marker_color = "#d97706" if val > high else "#16a34a"

        return _clean_html_str(
            f"""
            <div style="margin-top: 10px; margin-bottom: 6px; padding: 0 4px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 3px;">
                    <span>0.0</span>
                    <span style="color: #15803d; font-weight: 600;">Desirable: &lt; {high} {test.unit}</span>
                    <span>Max: {d_max:.1f}</span>
                </div>
                <div style="position: relative; height: 12px; background: #e2e8f0; border-radius: 6px; overflow: visible; display: flex;">
                    <div style="width: {p_norm:.1f}%; background: #86efac; border-top-left-radius: 6px; border-bottom-left-radius: 6px;" title="Optimal range (< {high})"></div>
                    <div style="width: {p_high:.1f}%; background: #fca5a5; border-top-right-radius: 6px; border-bottom-right-radius: 6px;" title="High zone (> {high})"></div>
                    <div style="position: absolute; left: {p_val:.1f}%; top: -4px; width: 4px; height: 20px; background: {marker_color}; border: 1.5px solid #ffffff; border-radius: 2px; box-shadow: 0 1px 4px rgba(0,0,0,0.4); transform: translateX(-50%); z-index: 10;" title="Patient Result: {val} {test.unit}"></div>
                </div>
                <div style="position: relative; height: 16px; margin-top: 2px;">
                    <span style="position: absolute; left: {p_val:.1f}%; transform: translateX(-50%); font-size: 11px; font-weight: 700; color: {marker_color};">
                        ▲ {val}
                    </span>
                </div>
            </div>
            """
        )

    # One-sided lower bound (> low)
    if low is not None and high is None:
        d_min = 0.0
        d_max = max(val * 1.35, low * 1.8)
        total = d_max - d_min
        if total <= 0:
            return ""

        p_low = max(5.0, (low / total) * 100)
        p_norm = max(10.0, 100.0 - p_low)
        p_val = max(2.0, min(97.0, (val / total) * 100))
        marker_color = "#d97706" if val < low else "#16a34a"

        return _clean_html_str(
            f"""
            <div style="margin-top: 10px; margin-bottom: 6px; padding: 0 4px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 3px;">
                    <span>0.0</span>
                    <span style="color: #15803d; font-weight: 600;">Desirable: &gt; {low} {test.unit}</span>
                    <span>Max: {d_max:.1f}</span>
                </div>
                <div style="position: relative; height: 12px; background: #e2e8f0; border-radius: 6px; overflow: visible; display: flex;">
                    <div style="width: {p_low:.1f}%; background: #fef08a; border-top-left-radius: 6px; border-bottom-left-radius: 6px;" title="Low zone (< {low})"></div>
                    <div style="width: {p_norm:.1f}%; background: #86efac; border-top-right-radius: 6px; border-bottom-right-radius: 6px;" title="Normal optimal range (> {low})"></div>
                    <div style="position: absolute; left: {p_val:.1f}%; top: -4px; width: 4px; height: 20px; background: {marker_color}; border: 1.5px solid #ffffff; border-radius: 2px; box-shadow: 0 1px 4px rgba(0,0,0,0.4); transform: translateX(-50%); z-index: 10;" title="Patient Result: {val} {test.unit}"></div>
                </div>
                <div style="position: relative; height: 16px; margin-top: 2px;">
                    <span style="position: absolute; left: {p_val:.1f}%; transform: translateX(-50%); font-size: 11px; font-weight: 700; color: {marker_color};">
                        ▲ {val}
                    </span>
                </div>
            </div>
            """
        )

    return ""


def generate_audio_summary(text: str, lang: str) -> Optional[bytes]:
    """Generate MP3 audio bytes for diagnostic text summary using gTTS."""
    try:
        from gtts import gTTS

        buf = io.BytesIO()
        tts = gTTS(text=text, lang="hi" if lang == "hi" else "en", slow=False)
        tts.write_to_fp(buf)
        return buf.getvalue()
    except Exception:
        return None


def set_custom_styles():
    """Inject Linear/Stripe-inspired modern SaaS CSS tokens and component styles."""
    st.markdown(
        """
        <style>
        /* Base typography & page resets */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #0f172a;
        }

        /* Top Navigation Bar */
        .saas-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 14px 20px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }
        .saas-nav-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 19px;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: -0.3px;
        }
        .saas-nav-tag {
            background: #f1f5f9;
            color: #475569;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
            letter-spacing: 0.5px;
        }

        /* Hero Section */
        .hero-left-container {
            padding: 10px 10px 20px 0;
        }
        .hero-badge-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #f0fdf4;
            color: #166534;
            border: 1px solid #bbf7d0;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 12px;
            border-radius: 9999px;
            letter-spacing: 0.3px;
            margin-bottom: 16px;
        }
        .hero-main-title {
            font-size: 42px;
            font-weight: 800;
            color: #0f172a;
            line-height: 1.15;
            letter-spacing: -1px;
            margin-bottom: 16px;
        }
        .hero-main-subtitle {
            font-size: 17px;
            color: #475569;
            line-height: 1.6;
            margin-bottom: 24px;
        }
        .hero-features-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-top: 18px;
        }
        .hero-feature-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            color: #334155;
            font-weight: 500;
        }

        /* Interactive Preview Frame (Linear / Stripe macOS Window) */
        .preview-window-frame {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 14px;
            box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.12), 0 8px 10px -6px rgba(15, 23, 42, 0.08);
            overflow: hidden;
            margin-bottom: 20px;
        }
        .preview-window-header {
            background: #f8fafc;
            border-bottom: 1px solid #e2e8f0;
            padding: 10px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .preview-window-dots {
            display: flex;
            gap: 6px;
        }
        .preview-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }
        .dot-red { background: #ef4444; }
        .dot-amber { background: #f59e0b; }
        .dot-green { background: #10b981; }

        .preview-window-title {
            font-size: 12px;
            font-weight: 600;
            color: #64748b;
        }
        .preview-window-body {
            padding: 16px;
            background: #fafafa;
        }

        /* Section Headings */
        .section-header-block {
            text-align: center;
            margin: 40px 0 24px 0;
        }
        .section-eyebrow {
            font-size: 12px;
            font-weight: 700;
            color: #0d9488;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 6px;
        }
        .section-headline {
            font-size: 28px;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
        }
        .section-subtext {
            font-size: 15px;
            color: #64748b;
            max-width: 680px;
            margin: 0 auto;
            line-height: 1.5;
        }

        /* Step & Feature Cards */
        .saas-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 22px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
            height: 100%;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .saas-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px -2px rgba(15, 23, 42, 0.08);
        }
        .step-number-badge {
            display: inline-block;
            background: #0f172a;
            color: #ffffff;
            font-size: 12px;
            font-weight: 800;
            padding: 2px 10px;
            border-radius: 6px;
            margin-bottom: 12px;
        }
        .card-icon-lg {
            font-size: 28px;
            margin-bottom: 10px;
        }
        .card-title-lg {
            font-size: 16px;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 6px;
        }
        .card-desc-lg {
            font-size: 13px;
            color: #64748b;
            line-height: 1.5;
        }

        /* Safety & Trust Box */
        .trust-banner-container {
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 14px;
            padding: 28px;
            margin: 30px 0;
        }

        /* Final CTA Banner */
        .final-cta-container {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border-radius: 16px;
            padding: 36px 28px;
            text-align: center;
            color: #ffffff;
            margin: 36px 0 24px 0;
            box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.2);
        }
        .final-cta-title {
            font-size: 28px;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 8px;
            letter-spacing: -0.4px;
        }
        .final-cta-sub {
            font-size: 15px;
            color: #cbd5e1;
            max-width: 620px;
            margin: 0 auto 20px auto;
            line-height: 1.5;
        }

        /* Split Layout Authentication Card */
        .auth-split-showcase {
            background: linear-gradient(145deg, #0f172a 0%, #1e293b 60%, #0f172a 100%);
            color: #ffffff;
            border-radius: 16px;
            padding: 36px 30px;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .auth-split-form-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 16px;
            padding: 28px 26px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        }

        /* Workspace Header */
        .workspace-header {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .workspace-title {
            font-size: 24px;
            font-weight: 800;
            color: #0f172a;
            margin: 0;
            letter-spacing: -0.3px;
        }
        .workspace-sub {
            font-size: 14px;
            color: #64748b;
            margin: 4px 0 0 0;
        }

        /* Metric Cards */
        .metric-card {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 16px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
        }
        .metric-card .value {
            font-size: 24px;
            font-weight: 800;
            color: #0f172a;
        }
        .metric-card .label {
            font-size: 11px;
            color: #64748b;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-top: 2px;
        }

        /* Analyte Card */
        .test-card {
            border-radius: 10px;
            padding: 18px;
            margin-bottom: 16px;
            border: 1px solid #e2e8f0;
            background: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .badge {
            display: inline-block;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: 700;
            border-radius: 9999px;
            letter-spacing: 0.3px;
        }
        .panic-banner {
            background-color: #fef2f2;
            border-left: 5px solid #dc2626;
            padding: 16px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(220, 38, 38, 0.08);
        }
        .disclaimer-banner {
            background-color: #f8fafc;
            border-left: 4px solid #0d9488;
            padding: 14px 18px;
            border-radius: 6px;
            color: #334155;
            font-size: 13px;
            margin-bottom: 20px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state():
    """Initialize persistent session variables."""
    defaults = {
        "access_token": None,
        "current_user": None,
        "current_job_id": None,
        "job_status": None,
        "extracted_report": None,
        "explanation": None,
        "pdf_bytes": None,
        "chat_history": [],
        "language": "en",
        "human_review_mode": True,
        "view": "landing",  # 'landing', 'login', 'register', 'dashboard'
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def get_api_client() -> CDSAPIClient:
    """Instantiate API client with current JWT Bearer token if logged in."""
    token = st.session_state.get("access_token")
    return CDSAPIClient(token=token)


def check_api_health() -> bool:
    """Verify backend FastAPI connectivity."""
    try:
        import httpx

        client = get_api_client()
        with httpx.Client(timeout=2.0) as hc:
            r = hc.get(f"{client.base_url}/healthz")
            return r.status_code == 200
    except Exception:
        return False


# =====================================================================
# SPLIT-LAYOUT AUTHENTICATION PAGES (SIGN IN & SIGN UP)
# =====================================================================

def render_login_page(client: CDSAPIClient):
    """Render modern split-layout Sign In page with brand preview card on left and form on right."""
    col_left, col_right = st.columns([1.1, 1], gap="large")

    with col_left:
        st.markdown(
            """
            <div class="auth-split-showcase">
                <div>
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 24px;">
                        <span style="font-size: 32px;">🧬</span>
                        <span style="font-size: 20px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;">AI Clinical Lab Explainer</span>
                    </div>
                    <h2 style="font-size: 30px; font-weight: 800; color: #ffffff; line-height: 1.25; margin-bottom: 14px;">
                        Welcome Back to Clinical Intelligence.
                    </h2>
                    <p style="font-size: 15px; color: #cbd5e1; line-height: 1.6; margin-bottom: 24px;">
                        Sign in to access your persistent laboratory report history, review past biomarker evaluations, 
                        and formulate doctor consultation questions with clinical decision support.
                    </p>
                    <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; color: #f1f5f9;">
                            <span style="color: #34d399; font-weight: bold;">✓</span> Multi-Tier OCR & Layout Extraction
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; color: #f1f5f9;">
                            <span style="color: #34d399; font-weight: bold;">✓</span> Deterministic Reference Range Flagging
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; color: #f1f5f9;">
                            <span style="color: #34d399; font-weight: bold;">✓</span> Grounded MedlinePlus Clinical Guidelines
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; color: #f1f5f9;">
                            <span style="color: #34d399; font-weight: bold;">✓</span> 100% Local SQLite Data Privacy & Audit Logs
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid rgba(255,255,255,0.12); padding-top: 18px; margin-top: 30px; font-size: 12px; color: #94a3b8;">
                    🔒 Enterprise Clinical Decision Support • Strict Patient Privacy Protection
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_right:
        # Back to Home link
        if st.button("← Back to Home", key="btn_login_back_home"):
            st.session_state["view"] = "landing"
            st.rerun()

        st.markdown(
            """
            <div style="margin-top: 8px; margin-bottom: 16px;">
                <h3 style="font-size: 24px; font-weight: 800; color: #0f172a; margin-bottom: 4px;">Sign In to Your Workspace</h3>
                <p style="font-size: 14px; color: #64748b; margin: 0;">Enter your verified credentials to continue.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        email = st.text_input("Email Address", key="login_field_email", placeholder="name@example.com")
        show_pw = st.checkbox("Show password", key="login_show_pw")
        password = st.text_input("Password", type="default" if show_pw else "password", key="login_field_pw", placeholder="••••••••")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Sign In", type="primary", use_container_width=True, key="login_btn_submit"):
            if not email or not password:
                st.error("Please enter both email address and password.")
            else:
                with st.spinner("Authenticating with Clinical CDS Engine..."):
                    try:
                        res = client.login(email=email.strip(), password=password)
                        st.session_state["access_token"] = res.get("access_token")
                        st.session_state["current_user"] = res.get("user")
                        st.session_state["view"] = "dashboard"
                        st.success("Authenticated successfully! Loading workspace...")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Sign in failed: {exc}")

        st.divider()
        col_switch_text, col_switch_btn = st.columns([2, 1])
        with col_switch_text:
            st.caption("Don't have an account yet?")
        with col_switch_btn:
            if st.button("Create Account", use_container_width=True, key="login_goto_register"):
                st.session_state["view"] = "register"
                st.rerun()


def render_register_page(client: CDSAPIClient):
    """Render modern split-layout Sign Up page with brand showcase card on left and registration form on right."""
    col_left, col_right = st.columns([1.1, 1], gap="large")

    with col_left:
        st.markdown(
            """
            <div class="auth-split-showcase">
                <div>
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 24px;">
                        <span style="font-size: 32px;">🧬</span>
                        <span style="font-size: 20px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;">AI Clinical Lab Explainer</span>
                    </div>
                    <h2 style="font-size: 30px; font-weight: 800; color: #ffffff; line-height: 1.25; margin-bottom: 14px;">
                        Transform Complex Reports Into Clear Knowledge.
                    </h2>
                    <p style="font-size: 15px; color: #cbd5e1; line-height: 1.6; margin-bottom: 24px;">
                        Create your free clinical account to upload laboratory reports, track your biomarker history, 
                        and generate concise physician-aligned discussion guides.
                    </p>
                    <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; color: #f1f5f9;">
                            <span style="color: #34d399; font-weight: bold;">✓</span> Instant Multi-Format Analysis (PDF, JPG, PNG)
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; color: #f1f5f9;">
                            <span style="color: #34d399; font-weight: bold;">✓</span> Interactive Reference Range Gauges
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; color: #f1f5f9;">
                            <span style="color: #34d399; font-weight: bold;">✓</span> Downloadable Printable Doctor Briefs (PDF)
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; color: #f1f5f9;">
                            <span style="color: #34d399; font-weight: bold;">✓</span> Free, Open Source & 100% Locally Stored
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid rgba(255,255,255,0.12); padding-top: 18px; margin-top: 30px; font-size: 12px; color: #94a3b8;">
                    🛡️ Zero PHI Sold or Shared • SHA-256 Cryptographic Audit Logs
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_right:
        # Back to Home link
        if st.button("← Back to Home", key="btn_reg_back_home"):
            st.session_state["view"] = "landing"
            st.rerun()

        st.markdown(
            """
            <div style="margin-top: 8px; margin-bottom: 16px;">
                <h3 style="font-size: 24px; font-weight: 800; color: #0f172a; margin-bottom: 4px;">Create Your Free Account</h3>
                <p style="font-size: 14px; color: #64748b; margin: 0;">Get started with intelligent diagnostic interpretation in seconds.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        full_name = st.text_input("Full Name", key="reg_field_name", placeholder="Dr. Jane Doe / John Smith")
        email = st.text_input("Email Address", key="reg_field_email", placeholder="name@example.com")
        role = st.selectbox("I am using this as a:", ["patient", "clinician"], key="reg_field_role")
        show_pw = st.checkbox("Show passwords", key="reg_show_pw")
        password = st.text_input("Password (min 8 characters)", type="default" if show_pw else "password", key="reg_field_pw", placeholder="••••••••")
        confirm_pw = st.text_input("Confirm Password", type="default" if show_pw else "password", key="reg_field_confirm_pw", placeholder="••••••••")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Create Account", type="primary", use_container_width=True, key="reg_btn_submit"):
            if not email or not password:
                st.error("Please provide both email address and password.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters long.")
            elif password != confirm_pw:
                st.error("Passwords do not match. Please verify your entries.")
            else:
                with st.spinner("Setting up your clinical workspace..."):
                    try:
                        res = client.register(
                            email=email.strip(),
                            password=password,
                            full_name=full_name.strip() if full_name else None,
                            role=role,
                        )
                        st.session_state["access_token"] = res.get("access_token")
                        st.session_state["current_user"] = res.get("user")
                        st.session_state["view"] = "dashboard"
                        st.success("Account created successfully! Loading workspace...")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Registration failed: {exc}")

        st.divider()
        col_switch_text, col_switch_btn = st.columns([2, 1])
        with col_switch_text:
            st.caption("Already have an account?")
        with col_switch_btn:
            if st.button("Sign In", use_container_width=True, key="reg_goto_login"):
                st.session_state["view"] = "login"
                st.rerun()


# =====================================================================
# PUBLIC SAAS LANDING PAGE
# =====================================================================

def render_landing_page(client: CDSAPIClient, backend_online: bool):
    """Render the public SaaS landing page with Navigation, Hero, Option B Preview, Features, Safety, FAQ, and Footer."""
    # Section A: Navigation Bar
    nav_col1, nav_col2 = st.columns([3, 2])
    with nav_col1:
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 10px; padding-top: 6px;">
                <span style="font-size: 26px;">🧬</span>
                <span style="font-size: 20px; font-weight: 800; color: #0f172a; letter-spacing: -0.3px;">AI Clinical Lab Explainer</span>
                <span class="saas-nav-tag">CLINICAL CDS</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with nav_col2:
        btn_c1, btn_c2, btn_c3 = st.columns([1, 1, 1])
        with btn_c1:
            if backend_online:
                st.caption("🟢 CDS API Online")
            else:
                st.caption("⚠️ API Offline")
        with btn_c2:
            if st.button("Sign In", key="nav_btn_signin", use_container_width=True):
                st.session_state["view"] = "login"
                st.rerun()
        with btn_c3:
            if st.button("Get Started", type="primary", key="nav_btn_getstarted", use_container_width=True):
                st.session_state["view"] = "register"
                st.rerun()

    st.markdown("<hr style='margin: 12px 0 24px 0; border: none; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

    # Section B: Hero Section (Split 2-Column with Option B Live Interactive Preview)
    hero_col_left, hero_col_right = st.columns([1.1, 1.2], gap="large")

    with hero_col_left:
        st.markdown(
            """
            <div class="hero-left-container">
                <div class="hero-badge-pill">
                    <span>🔬</span> Enterprise Clinical Decision Support
                </div>
                <h1 class="hero-main-title">
                    Your Lab Reports,<br>Easier to Understand.
                </h1>
                <p class="hero-main-subtitle">
                    Upload your laboratory report and understand your test results through simple explanations, 
                    reference ranges and helpful medical information.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        cta_col1, cta_col2 = st.columns([1.2, 1])
        with cta_col1:
            if st.button("🚀 Analyze My Report", type="primary", use_container_width=True, key="hero_cta_analyze"):
                st.session_state["view"] = "register"
                st.rerun()
        with cta_col2:
            if st.button("📖 See How It Works", use_container_width=True, key="hero_cta_how"):
                st.session_state["scroll_how_it_works"] = True

        st.markdown(
            """
            <div class="hero-features-list">
                <div class="hero-feature-item">
                    <span style="color: #0d9488; font-weight: bold;">✓</span> Multi-Tier OCR & Table Geometry Parsing
                </div>
                <div class="hero-feature-item">
                    <span style="color: #0d9488; font-weight: bold;">✓</span> Pure Deterministic Reference Range Flagging
                </div>
                <div class="hero-feature-item">
                    <span style="color: #0d9488; font-weight: bold;">✓</span> MedlinePlus Authoritative Clinical Grounding
                </div>
                <div class="hero-feature-item">
                    <span style="color: #0d9488; font-weight: bold;">✓</span> 100% Local SQLite Privacy & Cryptographic Audit Logs
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Right side: Realistic Synthetic Product Preview (Option B Interactive Live Demo)
    with hero_col_right:
        st.markdown(
            """
            <div class="preview-window-frame">
                <div class="preview-window-header">
                    <div class="preview-window-dots">
                        <div class="preview-dot dot-red"></div>
                        <div class="preview-dot dot-amber"></div>
                        <div class="preview-dot dot-green"></div>
                    </div>
                    <div class="preview-window-title">Synthetic Dashboard Preview • Live Interactive Demo</div>
                    <div style="font-size: 11px; color: #15803d; font-weight: 600;">● Active</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        demo_choice = st.selectbox(
            "Select Clinical Sample to Preview Live:",
            ["SRL Lipid Panel (Lipid Profile)", "Thyrocare CBC (Complete Blood Count)", "Metropolis Liver Function Test (LFT)"],
            index=0,
            key="landing_preview_select",
        )

        demo_samples = {
            "SRL Lipid Panel (Lipid Profile)": {
                "patient": "Pooja Patel",
                "date": "14-Nov-2026",
                "lab": "SRL Diagnostics",
                "total": 5,
                "flagged": 2,
                "tests": [
                    {
                        "test_name": "Total Cholesterol",
                        "value": 240.0,
                        "unit": "mg/dL",
                        "ref_high": 200.0,
                        "ref_raw": "< 200.0 mg/dL",
                        "flag": FlagStatus.HIGH,
                        "explanation_en": (
                            "• What It Measures: Total Cholesterol evaluates the cumulative circulating lipid and lipoprotein particles in your bloodstream.\n"
                            "• What This Finding Indicates: Your observed result is 240.0 mg/dL, categorized as HIGH against the reference range (< 200.0 mg/dL). Elevated levels reflect higher circulating lipid density associated with arterial lipid deposition."
                        ),
                        "explanation_hi": (
                            "• यह जांच क्या मापती है: कुल कोलेस्ट्रॉल आपके रक्तप्रवाह में मौजूद समग्र लिपिड और लिपोप्रोटीन कणों की मात्रा को मापता है।\n"
                            "• आपके परिणाम का क्या अर्थ है: आपका परिणाम 240.0 mg/dL है, जो संदर्भ सीमा (< 200.0 mg/dL) के अनुसार HIGH की श्रेणी में आता है। बढ़े हुए स्तर रक्त वाहिकाओं में वसा के जमाव से जुड़े होते हैं।"
                        ),
                        "questions": [
                            "How does this total cholesterol level factor into my overall cardiovascular risk assessment?",
                            "Are any follow-up tests, monitoring intervals, or dietary modifications recommended?",
                        ],
                        "source": "https://medlineplus.gov/cholesterol.html",
                    },
                    {
                        "test_name": "Triglycerides",
                        "value": 195.0,
                        "unit": "mg/dL",
                        "ref_high": 150.0,
                        "ref_raw": "< 150.0 mg/dL",
                        "flag": FlagStatus.HIGH,
                        "explanation_en": (
                            "• What It Measures: Triglycerides evaluate the primary chemical form of circulating fatty acids stored in body fat.\n"
                            "• What This Finding Indicates: Your observed result is 195.0 mg/dL, categorized as HIGH against the reference range (< 150.0 mg/dL). Elevated levels correlate with dietary lipid intake, metabolic regulation, and cardiovascular risk factors."
                        ),
                        "explanation_hi": (
                            "• यह जांच क्या मापती है: ट्राइग्लिसराइड्स शरीर में संचित वसा और रक्त में मौजूद मुख्य वसायुक्त अम्लों के स्तर का मूल्यांकन करते हैं।\n"
                            "• आपके परिणाम का क्या अर्थ है: आपका परिणाम 195.0 mg/dL है, जो संदर्भ सीमा (< 150.0 mg/dL) के अनुसार HIGH की श्रेणी में आता है।"
                        ),
                        "questions": [
                            "What metabolic or dietary factors might be contributing to elevated triglycerides?",
                            "What timeline do you recommend for a repeat lipid evaluation?",
                        ],
                        "source": "https://medlineplus.gov/triglycerides.html",
                    },
                    {
                        "test_name": "HDL Cholesterol",
                        "value": 48.0,
                        "unit": "mg/dL",
                        "ref_low": 40.0,
                        "ref_raw": "> 40.0 mg/dL",
                        "flag": FlagStatus.NORMAL,
                        "explanation_en": (
                            "• What It Measures: HDL (High-Density Lipoprotein) measures the 'protective' cholesterol that transports excess lipids from tissues back to the liver.\n"
                            "• What This Finding Indicates: Your observed result is 48.0 mg/dL, categorized as NORMAL against the reference range (> 40.0 mg/dL). Adequate HDL concentrations support reverse lipid clearance."
                        ),
                        "explanation_hi": (
                            "• यह जांच क्या मापती है: एचडीएल सुरक्षात्मक कोलेस्ट्रॉल है जो अतिरिक्त वसा को ऊतकों से वापस यकृत में स्थानांतरित करने का कार्य करता है।\n"
                            "• आपके परिणाम का क्या अर्थ है: आपका परिणाम 48.0 mg/dL है, जो सामान्य सीमा में है।"
                        ),
                        "questions": [
                            "Is my current HDL level sufficient to maintain a balanced cholesterol ratio?",
                            "What aerobic or lifestyle habits help support healthy protective HDL levels?",
                        ],
                        "source": "https://medlineplus.gov/hdlthegoodcholesterol.html",
                    },
                ],
            },
            "Thyrocare CBC (Complete Blood Count)": {
                "patient": "Kavita Rao",
                "date": "10-Nov-2026",
                "lab": "Thyrocare Technologies",
                "total": 12,
                "flagged": 1,
                "tests": [
                    {
                        "test_name": "Hemoglobin",
                        "value": 10.4,
                        "unit": "g/dL",
                        "ref_low": 12.0,
                        "ref_high": 15.5,
                        "ref_raw": "12.0 - 15.5 g/dL",
                        "flag": FlagStatus.LOW,
                        "explanation_en": (
                            "• What It Measures: Hemoglobin is the iron-rich protein in red blood cells that transports oxygen from your lungs to tissues throughout your body.\n"
                            "• What This Finding Indicates: Your observed result is 10.4 g/dL, categorized as LOW against the standard reference interval (12.0 - 15.5 g/dL). Reduced levels indicate diminished oxygen-carrying capacity in the blood."
                        ),
                        "explanation_hi": (
                            "• यह जांच क्या मापती है: हीमोग्लोबिन लाल रक्त कोशिकाओं में मौजूद वह प्रोटीन है जो फेफड़ों से शरीर के सभी अंगों तक ऑक्सीजन पहुंचाता है।\n"
                            "• आपके परिणाम का क्या अर्थ है: आपका परिणाम 10.4 g/dL है, जो संदर्भ सीमा (12.0 - 15.5 g/dL) के अनुसार LOW है।"
                        ),
                        "questions": [
                            "Could nutritional factors such as iron, ferritin, or vitamin B12 levels be contributing to this finding?",
                            "Would you recommend a peripheral blood smear or serum iron study?",
                        ],
                        "source": "https://medlineplus.gov/lab-tests/hemoglobin-test/",
                    },
                ],
            },
            "Metropolis Liver Function Test (LFT)": {
                "patient": "Amit Saxena",
                "date": "08-Nov-2026",
                "lab": "Metropolis Healthcare",
                "total": 8,
                "flagged": 1,
                "tests": [
                    {
                        "test_name": "SGPT (ALT)",
                        "value": 68.0,
                        "unit": "U/L",
                        "ref_high": 45.0,
                        "ref_raw": "< 45.0 U/L",
                        "flag": FlagStatus.HIGH,
                        "explanation_en": (
                            "• What It Measures: ALT (Alanine Aminotransferase) is an intracellular enzyme found predominantly in liver cells.\n"
                            "• What This Finding Indicates: Your observed result is 68.0 U/L, categorized as HIGH against the reference range (< 45.0 U/L). Elevated levels indicate increased cellular leakage into the bloodstream, reflecting hepatic physiological stress."
                        ),
                        "explanation_hi": (
                            "• यह जांच क्या मापती है: एएलटी (एसजीपीटी) मुख्य रूप से यकृत की कोशिकाओं में पाया जाने वाला एक महत्वपूर्ण एंजाइम है।\n"
                            "• आपके परिणाम का क्या अर्थ है: आपका परिणाम 68.0 U/L है, जो संदर्भ सीमा (< 45.0 U/L) के अनुसार HIGH है।"
                        ),
                        "questions": [
                            "What factors (metabolic, dietary, or recent activity) might have influenced this ALT level?",
                            "Do you recommend repeat liver panel testing or an ultrasound evaluation?",
                        ],
                        "source": "https://medlineplus.gov/lab-tests/alt-blood-test/",
                    },
                ],
            },
        }

        demo_data = demo_samples.get(demo_choice, demo_samples["SRL Lipid Panel (Lipid Profile)"])

        # Preview Metrics Row
        m_c1, m_c2, m_c3 = st.columns(3)
        with m_c1:
            st.markdown(f'<div class="metric-card"><div class="value">{demo_data["total"]}</div><div class="label">Total Parameters</div></div>', unsafe_allow_html=True)
        with m_c2:
            st.markdown(f'<div class="metric-card"><div class="value" style="color: #15803d;">{demo_data["total"] - demo_data["flagged"]}</div><div class="label">Normal Results</div></div>', unsafe_allow_html=True)
        with m_c3:
            st.markdown(f'<div class="metric-card"><div class="value" style="color: #b45309;">{demo_data["flagged"]}</div><div class="label">Out-of-Range</div></div>', unsafe_allow_html=True)

        # Preview language switcher
        demo_lang_choice = st.radio("Preview Language:", ["English", "हिंदी (Hindi)"], horizontal=True, key="landing_demo_lang")
        is_hi = "हिंदी" in demo_lang_choice

        # Render first biomarker preview card
        preview_test = demo_data["tests"][0]
        t_obj = TestResult(
            test_name=preview_test["test_name"],
            value=preview_test["value"],
            unit=preview_test["unit"],
            ref_low=preview_test.get("ref_low"),
            ref_high=preview_test.get("ref_high"),
            ref_raw=preview_test.get("ref_raw", ""),
            flag=preview_test["flag"],
        )
        b_text, b_icon, b_bg, b_fg, b_border = FLAG_BADGES[preview_test["flag"]]

        st.markdown(
            f"""
            <div class="test-card" style="margin-top: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-size: 16px; font-weight: 700; color: #0f172a;">{preview_test['test_name']}</span>
                    <span class="badge" style="background-color: {b_bg}; color: {b_fg}; border: 1px solid {b_border};">
                        {b_icon} {b_text}
                    </span>
                </div>
                <div style="font-size: 14px; margin-bottom: 4px; color: #334155;">
                    <strong>Result:</strong> {preview_test['value']} {preview_test['unit']} &nbsp;|&nbsp; <strong>Reference:</strong> {preview_test['ref_raw']}
                </div>
                {render_range_gauge_html(t_obj)}
                <div style="margin-top: 10px; font-size: 13px; color: #1e293b; background: #f8fafc; padding: 10px 12px; border-radius: 6px; border-left: 3px solid #0d9488;">
                    <strong>Clinical Context:</strong><br>
                    {preview_test['explanation_hi'] if is_hi else preview_test['explanation_en']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Section C: How It Works
    st.markdown("<div id='how-it-works'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="section-header-block">
            <div class="section-eyebrow">Seamless 3-Step Workflow</div>
            <h2 class="section-headline">How It Works</h2>
            <p class="section-subtext">From raw laboratory document to structured, physician-aligned clinical clarity in seconds.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_step1, c_step2, c_step3 = st.columns(3)
    with c_step1:
        st.markdown(
            """
            <div class="saas-card">
                <span class="step-number-badge">STEP 01</span>
                <div class="card-icon-lg">📄</div>
                <div class="card-title-lg">1. Upload Your Report</div>
                <div class="card-desc-lg">
                    Upload a PDF or image of your laboratory report. Supports digital PDFs, document scans, and phone photos (PNG, JPG, WEBP) up to 50MB.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c_step2:
        st.markdown(
            """
            <div class="saas-card">
                <span class="step-number-badge">STEP 02</span>
                <div class="card-icon-lg">🔍</div>
                <div class="card-title-lg">2. Review Your Results</div>
                <div class="card-desc-lg">
                    Extract test names, values, units and reference ranges. Our multi-tier layout engine validates every biomarker with optional Human-in-the-Loop review.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c_step3:
        st.markdown(
            """
            <div class="saas-card">
                <span class="step-number-badge">STEP 03</span>
                <div class="card-icon-lg">💡</div>
                <div class="card-title-lg">3. Understand Your Report</div>
                <div class="card-desc-lg">
                    Read simple explanations, review abnormal results and prepare questions for your doctor. View visual range gauges and download printable PDF briefs.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Section D: Features (6 Core Features)
    st.markdown(
        """
        <div class="section-header-block">
            <div class="section-eyebrow">Enterprise Capabilities</div>
            <h2 class="section-headline">Core Product Features</h2>
            <p class="section-subtext">Built to enterprise diagnostic standards with mathematical rigor and ethical healthcare guardrails.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    feat_row1_c1, feat_row1_c2, feat_row1_c3 = st.columns(3)
    with feat_row1_c1:
        st.markdown(
            """
            <div class="saas-card">
                <div class="card-icon-lg">📑</div>
                <div class="card-title-lg">Smart Report Extraction</div>
                <div class="card-desc-lg">Combines native PDF parsing, table boundary extraction, and OCR to reliably capture biomarker names, numeric values, units, and printed reference ranges.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with feat_row1_c2:
        st.markdown(
            """
            <div class="saas-card">
                <div class="card-icon-lg">⚖️</div>
                <div class="card-title-lg">Normal & Abnormal Result Identification</div>
                <div class="card-desc-lg">Strict deterministic mathematical flagging against laboratory reference bounds. High, Low, and Critical Panic thresholds are verified without guessing.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with feat_row1_c3:
        st.markdown(
            """
            <div class="saas-card">
                <div class="card-icon-lg">🩺</div>
                <div class="card-title-lg">Simple AI-Powered Explanations</div>
                <div class="card-desc-lg">Concise, structured 2-bullet clinical context explaining exactly what each test measures and what your observed finding means in plain language.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    feat_row2_c1, feat_row2_c2, feat_row2_c3 = st.columns(3)
    with feat_row2_c1:
        st.markdown(
            """
            <div class="saas-card">
                <div class="card-icon-lg">📚</div>
                <div class="card-title-lg">Medical Information References</div>
                <div class="card-desc-lg">Retrieval-Augmented Generation (RAG) grounds every explanation strictly in peer-reviewed clinical guidelines from the National Library of Medicine (MedlinePlus).</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with feat_row2_c2:
        st.markdown(
            """
            <div class="saas-card">
                <div class="card-icon-lg">🌐</div>
                <div class="card-title-lg">English & Hindi Explanations</div>
                <div class="card-desc-lg">Seamless bilingual support. Toggle between English and हिंदी with one click to ensure accessible healthcare communication across diverse families.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with feat_row2_c3:
        st.markdown(
            """
            <div class="saas-card">
                <div class="card-icon-lg">📋</div>
                <div class="card-title-lg">Doctor Discussion Summary</div>
                <div class="card-desc-lg">Automatically generates high-yield discussion questions tailored to your out-of-range findings and produces a printable Doctor Discussion Brief PDF.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Section E: Safety and Trust
    st.markdown(
        """
        <div class="trust-banner-container">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                <span style="font-size: 24px;">🛡️</span>
                <span style="font-size: 20px; font-weight: 800; color: #0f172a;">Understand Your Results. Make Informed Conversations Possible.</span>
            </div>
            <p style="font-size: 14px; color: #475569; line-height: 1.6; margin-bottom: 16px;">
                Our platform is engineered as an educational clinical decision support tool designed to demystify complex lab numbers 
                and empower constructive dialogue with your physician:
            </p>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px;">
                <div style="font-size: 13px; color: #334155; line-height: 1.5;">
                    <strong>• Educational Guidance:</strong> The application provides educational explanations, not medical diagnoses or treatment regimens.
                </div>
                <div style="font-size: 13px; color: #334155; line-height: 1.5;">
                    <strong>• Laboratory Reference Ranges:</strong> Specific laboratory-printed reference bounds are used to objectively evaluate your reported values.
                </div>
                <div style="font-size: 13px; color: #334155; line-height: 1.5;">
                    <strong>• Qualified Healthcare Consultation:</strong> AI explanations are not medical diagnoses. Users should always consult qualified healthcare professionals for clinical decisions.
                </div>
                <div style="font-size: 13px; color: #334155; line-height: 1.5;">
                    <strong>• Real Privacy & Security:</strong> All patient records, extraction data, and audit trails reside in your isolated local SQLite database with Merkle SHA-256 logs. Zero PHI is sold or sent to third-party ad networks.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Section F: Frequently Asked Questions (FAQ)
    st.markdown(
        """
        <div class="section-header-block">
            <div class="section-eyebrow">Got Questions?</div>
            <h2 class="section-headline">Frequently Asked Questions</h2>
            <p class="section-subtext">Accurate, transparent details about our clinical interpretation capabilities.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("What types of reports can I upload?", expanded=False):
        st.write(
            "You can upload routine blood tests, Complete Blood Counts (CBC), Lipid Panels, Liver Function Tests (LFT), "
            "Kidney Function Tests (KFT), Glycemic / HbA1c panels, Thyroid profiles, and multi-page comprehensive checkups. "
            "Supported file formats include PDF, JPG, JPEG, PNG, and WEBP documents up to 50MB."
        )

    with st.expander("How does the application explain laboratory results?", expanded=False):
        st.write(
            "Our multi-tier engine extracts biomarker names, observed values, measurement units, and reference ranges. "
            "It computes deterministic mathematical flags against the laboratory's printed reference bounds, retrieves relevant clinical context "
            "from the National Library of Medicine (MedlinePlus), and synthesizes a concise 2-bullet explanation focusing on what the test measures "
            "and what your result indicates."
        )

    with st.expander("Can it diagnose medical conditions or prescribe medicine?", expanded=False):
        st.write(
            "No. The platform strictly enforces clinical safety guardrails. It never provides medical diagnoses, never recommends drugs or medications, "
            "and never suggests dosages. Its sole purpose is educational clinical decision support to help you understand your data and prepare questions for your physician."
        )

    with st.expander("Can I ask questions about my report?", expanded=False):
        st.write(
            "Yes! Once your report is analyzed, an interactive conversational clinical Q&A interface becomes available. "
            "You can ask clarifying questions about your biomarkers, biological functions, and reference intervals. "
            "All responses are grounded strictly in your uploaded report findings and MedlinePlus medical literature."
        )

    with st.expander("Can I download a report summary?", expanded=False):
        st.write(
            "Yes. You can download a clean, professionally formatted Doctor Discussion Brief PDF with one click. "
            "It summarizes all out-of-range biomarkers, includes reference ranges, and lists high-yield questions for your next clinic visit."
        )

    # Section G: Final CTA & Footer
    st.markdown(
        """
        <div class="final-cta-container">
            <h2 class="final-cta-title">Start Understanding Your Lab Reports Today.</h2>
            <p class="final-cta-sub">
                Join patients and clinicians making informed diagnostic conversations possible with intelligent clinical decision support.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_cta_btn_l, col_cta_btn_c, col_cta_btn_r = st.columns([1, 1, 1])
    with col_cta_btn_c:
        if st.button("🚀 Get Started Now", type="primary", use_container_width=True, key="landing_final_cta_btn"):
            st.session_state["view"] = "register"
            st.rerun()

    # Footer
    st.markdown("<hr style='margin: 40px 0 20px 0; border: none; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #64748b; padding-bottom: 24px;">
            <div>
                <strong>AI Clinical Lab Report Explainer</strong> • Educational Clinical Decision Support Platform
            </div>
            <div style="display: flex; gap: 16px;">
                <span>Home</span>
                <span>How It Works</span>
                <span>Safety & Trust</span>
                <span>Privacy Notice</span>
                <span>Medical Disclaimer</span>
            </div>
        </div>
        <div style="font-size: 11px; color: #94a3b8; text-align: center; padding-bottom: 16px;">
            ⚠️ <em>Medical Notice: This application is for educational and informational purposes only and does not substitute professional medical consultation, diagnosis, or treatment. Always discuss all laboratory results with your licensed healthcare provider.</em>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =====================================================================
# MAIN AUTHENTICATED USER DASHBOARD
# =====================================================================

def render_auth_sidebar(client: CDSAPIClient):
    """Render User Profile and Sign Out action in the sidebar when authenticated."""
    user = st.session_state.get("current_user")
    if user:
        st.sidebar.markdown(f"👤 **{user.get('full_name') or user.get('email')}**")
        st.sidebar.caption(f"Role: **{user.get('role', 'patient').capitalize()}** | Status: Active 🟢")
        if st.sidebar.button("🚪 Sign Out", use_container_width=True, key="btn_signout"):
            st.session_state["access_token"] = None
            st.session_state["current_user"] = None
            st.session_state["current_job_id"] = None
            st.session_state["job_status"] = None
            st.session_state["extracted_report"] = None
            st.session_state["explanation"] = None
            st.session_state["chat_history"] = []
            st.session_state["view"] = "landing"
            st.rerun()
        st.sidebar.divider()


def render_history_sidebar(client: CDSAPIClient):
    """Render persistent historical reports in sidebar with reload and delete actions."""
    if not st.session_state.get("access_token"):
        return

    st.sidebar.markdown("### 🗂️ My Reports")

    if st.sidebar.button("➕ Analyze New Report", use_container_width=True, key="btn_new_analysis"):
        st.session_state["current_job_id"] = None
        st.session_state["job_status"] = None
        st.session_state["extracted_report"] = None
        st.session_state["explanation"] = None
        st.session_state["chat_history"] = []
        st.rerun()

    try:
        reports = client.list_reports(limit=25)
        if not reports:
            st.sidebar.caption("No historical reports found for this account.")
        else:
            for rep in reports:
                jid = rep.get("job_id")
                date_str = (rep.get("created_at") or "")[:10]
                status_icon = "🟢" if rep.get("status") == "ready" else "🟡"
                fname = rep.get("filename") or "report.pdf"
                pname = rep.get("patient_name") or ""
                pname_disp = f" ({pname})" if pname else ""

                col_meta, col_load, col_del = st.sidebar.columns([3, 1, 1])
                with col_meta:
                    st.caption(f"{status_icon} **{fname[:14]}**{pname_disp}\n_{date_str}_")
                with col_load:
                    if st.button("Load", key=f"load_job_{jid}", help="Load this past analysis"):
                        st.session_state["current_job_id"] = jid
                        st.session_state["job_status"] = rep.get("status")
                        if rep.get("status") == "ready":
                            try:
                                exp = client.get_explanation(jid)
                                st.session_state["explanation"] = exp
                            except Exception:
                                pass
                        st.rerun()
                with col_del:
                    if st.button("🗑️", key=f"del_job_{jid}", help="Delete report"):
                        try:
                            client.delete_report(jid)
                            if st.session_state.get("current_job_id") == jid:
                                st.session_state["current_job_id"] = None
                                st.session_state["job_status"] = None
                                st.session_state["extracted_report"] = None
                                st.session_state["explanation"] = None
                            st.sidebar.success("Deleted!")
                            st.rerun()
                        except Exception as e:
                            st.sidebar.error(f"Delete failed: {e}")
    except Exception as exc:
        st.sidebar.caption(f"Could not load history: {exc}")
    st.sidebar.divider()


def render_authenticated_workspace(client: CDSAPIClient, backend_online: bool):
    """Render the full authenticated clinical CDS workspace."""
    # Sidebar
    st.sidebar.image("https://img.icons8.com/fluency/96/dna-helix.png", width=42)
    st.sidebar.title("Clinical CDS")

    if backend_online:
        st.sidebar.caption("🟢 **CDS Backend:** Online (:8000)")
    else:
        st.sidebar.warning("⚠️ **CDS Backend:** Offline (:8000)")

    render_auth_sidebar(client)
    render_history_sidebar(client)

    # Preferences in sidebar
    st.sidebar.markdown("### ⚙️ Preferences")
    lang_choice = st.sidebar.radio("Display Language", ["English", "हिंदी (Hindi)"], index=0)
    st.session_state["language"] = "hi" if "हिंदी" in lang_choice else "en"

    human_review = st.sidebar.checkbox(
        "Enable Human-in-the-Loop Review",
        value=st.session_state.get("human_review_mode", True),
        help="Review and edit extracted values & reference ranges before generating AI explanations",
    )
    st.session_state["human_review_mode"] = human_review

    explain_all_opt = st.sidebar.checkbox(
        "Explain All Analytes (Normal + Abnormal)",
        value=False,
        help="By default, AI clinical explanations focus on abnormal biomarkers",
    )

    # Dashboard Header
    user = st.session_state.get("current_user") or {}
    user_name = user.get("full_name") or user.get("email") or "Clinician"
    role_tag = user.get("role", "patient").capitalize()
    lang = st.session_state["language"]

    header_col_left, header_col_right = st.columns([3, 1])
    with header_col_left:
        greeting_text = f"Welcome back, {user_name}" if lang == "en" else f"नमस्ते, {user_name}"
        st.markdown(
            f"""
            <div style="margin-bottom: 20px;">
                <h1 style="font-size: 28px; font-weight: 800; color: #0f172a; margin: 0; letter-spacing: -0.4px;">
                    🧬 {greeting_text}
                </h1>
                <p style="font-size: 14px; color: #64748b; margin: 4px 0 0 0;">
                    Clinical Decision Support • Deterministic Flagging & MedlinePlus Medical Grounding
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with header_col_right:
        st.markdown(
            f"""
            <div style="text-align: right; padding-top: 8px;">
                <span class="badge" style="background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; font-size: 12px;">
                    👤 {role_tag} Mode
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Educational Disclaimer Banner
    disclaimer_msg = (
        "⚠️ **Clinical Educational Notice:** This tool is an educational diagnostic explainer. "
        "It does not provide medical diagnoses or prescribe treatment. Always discuss all laboratory results with your licensed healthcare provider."
        if lang == "en"
        else "⚠️ **क्लिनिकल शैक्षिक सूचना:** यह उपकरण केवल शैक्षिक मार्गदर्शन के लिए है। यह कोई मेडिकल निदान या उपचार निर्धारित नहीं करता है। हमेशा अपने चिकित्सक से परामर्श लें।"
    )
    st.markdown(f'<div class="disclaimer-banner">{disclaimer_msg}</div>', unsafe_allow_html=True)

    # Empty State & Ingestion Section (Shown when no report is actively loaded or being processed)
    curr_job_id = st.session_state.get("current_job_id")
    curr_status = st.session_state.get("job_status")

    if not curr_job_id or curr_status is None:
        st.markdown("### 📄 Analyze New Laboratory Report")
        st.caption("Upload your digital lab report or choose a pre-loaded clinical sample to begin intelligent extraction.")

        col_up, col_sample = st.columns([2, 1])

        uploaded_file = None
        with col_up:
            file_input = st.file_uploader(
                "Drag and drop laboratory report (PDF, PNG, JPG, JPEG, WEBP)",
                type=["pdf", "png", "jpg", "jpeg", "webp"],
                help="High-resolution digital PDFs and clinical document scans up to 50MB",
                key="uploader_main",
            )
            if file_input:
                uploaded_file = file_input

        with col_sample:
            st.markdown("**Or Select a Clinical Sample:**")
            sample_choice = st.selectbox(
                "Pre-loaded Patient Panels",
                ["-- Select a Sample Report --"] + list(SAMPLE_OPTIONS.keys()),
                key="sample_select_main",
            )
            if sample_choice != "-- Select a Sample Report --":
                sample_path = SAMPLE_DIR / SAMPLE_OPTIONS[sample_choice]
                if sample_path.exists():
                    st.caption(f"Selected: `{SAMPLE_OPTIONS[sample_choice]}` ({sample_path.stat().st_size // 1024} KB)")

        if st.button("🚀 Analyze Lab Report", type="primary", use_container_width=True, key="btn_run_analysis"):
            if not backend_online:
                st.error("Cannot analyze report: FastAPI CDS Backend is currently offline. Please launch the backend service.")
                return

            file_bytes = None
            filename = "lab_report.pdf"

            if uploaded_file:
                file_bytes = uploaded_file.getvalue()
                filename = uploaded_file.name
            elif sample_choice != "-- Select a Sample Report --":
                sample_path = SAMPLE_DIR / SAMPLE_OPTIONS[sample_choice]
                file_bytes = sample_path.read_bytes()
                filename = sample_path.name
            else:
                st.warning("Please upload a file or select a clinical sample report to begin.")
                return

            with st.spinner("Uploading document to clinical processing pipeline..."):
                try:
                    auto_conf = not st.session_state["human_review_mode"]
                    upload_res = client.upload_report(
                        file_bytes=file_bytes,
                        filename=filename,
                        explain_all=explain_all_opt,
                        auto_confirm=auto_conf,
                    )
                    st.session_state["current_job_id"] = upload_res["job_id"]
                    st.session_state["job_status"] = upload_res["status"]
                    st.session_state["extracted_report"] = None
                    st.session_state["explanation"] = None
                    st.session_state["chat_history"] = []
                    st.success(f"Report accepted! Job ID: `{upload_res['job_id'][:8]}...`")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")

    # Polling & Workflow State Management
    job_id = st.session_state.get("current_job_id")
    if job_id and backend_online:
        try:
            status_data = client.get_job_status(job_id)
            current_status = status_data.get("status")
            st.session_state["job_status"] = current_status

            # Handle IN-PROGRESS polling with real backend stages
            if current_status in ("queued", "extracting", "flagging", "rag_retrieval", "generating"):
                progress_pct = status_data.get("progress_pct", 10)
                current_step = status_data.get("current_step", "Processing report...")
                st.info(f"⏳ **Clinical Pipeline Active:** {current_step}")
                st.progress(progress_pct / 100.0)
                time.sleep(1.5)
                st.rerun()

            elif current_status == "failed":
                st.error(f"❌ Processing failed: {status_data.get('error', 'Unknown error')}")

        except Exception as exc:
            st.caption(f"Status check note: {exc}")

    # Step 2: Human-in-the-Loop Extraction Review Screen
    if st.session_state.get("job_status") == "review_needed":
        st.divider()
        st.markdown("### 📋 Step 2: Human-in-the-Loop Review — Inspect Extracted Parameters")
        st.info(
            "💡 **Verification Check:** Below are the exact laboratory parameters extracted by our multi-tier OCR engine. "
            "Please review the values and reference ranges before generating AI clinical explanations. You can edit any parameter directly in the table."
        )

        extracted_resp = None
        try:
            extracted_resp = client.get_extracted_report(job_id)
        except Exception as exc:
            st.error(f"Could not load extraction data for review: {exc}")

        if extracted_resp:
            tests_data = extracted_resp.get("tests", [])

            patient_name_input = st.text_input(
                "Patient Identifier",
                value=extracted_resp.get("patient_name") or "Patient",
                key="input_review_patient_name",
            )

            df_tests = pd.DataFrame(tests_data)
            col_order = ["test_name", "value", "unit", "ref_low", "ref_high", "ref_raw", "flag"]
            available_cols = [c for c in col_order if c in df_tests.columns]
            df_tests = df_tests[available_cols]

            edited_df = st.data_editor(
                df_tests,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "test_name": st.column_config.TextColumn("Test / Biomarker Name", required=True),
                    "value": st.column_config.NumberColumn("Result Value", format="%.2f"),
                    "unit": st.column_config.TextColumn("Measurement Unit"),
                    "ref_low": st.column_config.NumberColumn("Reference Low", format="%.2f"),
                    "ref_high": st.column_config.NumberColumn("Reference High", format="%.2f"),
                    "ref_raw": st.column_config.TextColumn("Raw Reference String"),
                    "flag": st.column_config.SelectboxColumn("Flag", options=["normal", "low", "high", "critical_low", "critical_high", "unknown"]),
                },
                key="editor_biomarkers",
            )

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("✅ Confirm Parameters & Generate Explanations", type="primary", use_container_width=True, key="btn_confirm_edited"):
                    raw_records = edited_df.to_dict(orient="records")
                    confirmed_records = [
                        {k: (None if pd.isna(v) or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v) for k, v in r.items()}
                        for r in raw_records
                    ]
                    with st.spinner("Submitting verified parameters and synthesizing clinical explanations..."):
                        try:
                            client.confirm_report(
                                job_id=job_id,
                                tests=confirmed_records,
                                patient_name=patient_name_input,
                                explain_all=explain_all_opt,
                            )
                            st.session_state["job_status"] = "flagging"
                            st.rerun()
                        except Exception as submit_err:
                            st.error(f"Failed to submit confirmed parameters: {submit_err}")

            with col_btn2:
                if st.button("⚡ Confirm As-Is (Skip Editing)", use_container_width=True, key="btn_confirm_asis"):
                    with st.spinner("Synthesizing clinical explanations..."):
                        try:
                            client.confirm_report(
                                job_id=job_id,
                                tests=tests_data,
                                patient_name=patient_name_input,
                                explain_all=explain_all_opt,
                            )
                            st.session_state["job_status"] = "flagging"
                            st.rerun()
                        except Exception as submit_err:
                            st.error(f"Failed to confirm parameters: {submit_err}")

    # Step 3: Complete Clinical Findings Dashboard
    if st.session_state.get("job_status") == "ready":
        if not st.session_state.get("explanation"):
            try:
                st.session_state["explanation"] = client.get_explanation(job_id)
            except Exception as exc:
                st.error(f"Failed to load explanation: {exc}")

        exp = st.session_state.get("explanation")
        if exp:
            render_findings_dashboard(client, job_id, exp, lang)


def render_findings_dashboard(client: CDSAPIClient, job_id: str, exp: Dict[str, Any], lang: str):
    """Render the full interactive clinical findings dashboard with gauges, 2-bullet context, and chat."""
    st.divider()

    patient_name = exp.get("patient_name") or "Patient"
    report_summary = exp.get(f"report_summary_{lang}") or exp.get("report_summary_en", "")

    # Panic / Critical Value Alert Banner
    panic_alerts = exp.get("panic_alerts", [])
    if panic_alerts:
        st.markdown(
            f"""
            <div class="panic-banner">
                <h3 style="color: #b91c1c; margin: 0 0 8px 0; font-size: 18px;">
                    🚨 Critical Clinical Panic Alert Detected ({len(panic_alerts)} Finding{'s' if len(panic_alerts) > 1 else ''})
                </h3>
                <p style="color: #7f1d1d; margin: 0; font-size: 14px;">
                    One or more laboratory analytes fall into clinically recognized critical panic intervals.
                    Immediate medical evaluation by a licensed physician or emergency clinical care is strongly advised.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Overview Metrics Row
    total_tests = exp.get("total_tests", 0)
    flagged_count = exp.get("flagged_count", 0)
    normal_count = max(0, total_tests - flagged_count)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f'<div class="metric-card"><div class="value">{total_tests}</div><div class="label">Total Analytes</div></div>',
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f'<div class="metric-card"><div class="value" style="color: #16a34a;">{normal_count}</div><div class="label">In Normal Range</div></div>',
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f'<div class="metric-card"><div class="value" style="color: #d97706;">{flagged_count}</div><div class="label">Abnormal / Flagged</div></div>',
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f'<div class="metric-card"><div class="value" style="color: #dc2626;">{len(panic_alerts)}</div><div class="label">Critical Alerts</div></div>',
            unsafe_allow_html=True,
        )

    # Executive Diagnostic Summary
    st.markdown("### 📋 Executive Diagnostic Summary")
    st.info(report_summary)

    # Audio synthesis player
    audio_bytes = generate_audio_summary(report_summary, lang)
    if audio_bytes:
        st.audio(audio_bytes, format="audio/mp3")

    # Biomarker Analysis with Visual Range Gauges
    st.markdown("### 🔬 Biomarker Analysis & Reference Ranges")
    test_explanations = exp.get("test_explanations", [])

    if not test_explanations:
        st.caption("No individual analyte explanations available.")
    else:
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            status_filter = st.selectbox("Filter by Status", ["All Results", "Flagged Abnormal Only", "Normal Only"], key="filter_status")
        with filter_col2:
            search_query = st.text_input("🔍 Search Biomarker by Name", "", key="search_biomarker").lower().strip()

        for t in test_explanations:
            t_name = t.get("test_name", "")
            t_flag = t.get("flag", "unknown").lower()

            if status_filter == "Flagged Abnormal Only" and t_flag in ("normal", "unknown"):
                continue
            if status_filter == "Normal Only" and t_flag != "normal":
                continue
            if search_query and search_query not in t_name.lower():
                continue

            badge_text = t_flag.upper()
            badge_bg = "#f0fdf4" if t_flag == "normal" else ("#fef2f2" if "critical" in t_flag else "#fffbeb")
            badge_color = "#15803d" if t_flag == "normal" else ("#b91c1c" if "critical" in t_flag else "#b45309")
            val_display = f"{t.get('value')} {t.get('unit') or ''}".strip() if t.get("value") is not None else "Recorded"

            with st.container():
                st.markdown(
                    f"""
                    <div class="test-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <h4 style="margin: 0; color: #0f172a; font-size: 17px;">
                                {t_name}
                                <span class="badge" style="background: {badge_bg}; color: {badge_color};">
                                    {badge_text}
                                </span>
                            </h4>
                            <span style="font-size: 16px; font-weight: 700; color: #0f172a;">
                                {val_display}
                            </span>
                        </div>
                    """,
                    unsafe_allow_html=True,
                )

                t_obj = TestResult(
                    test_name=t_name,
                    value=t.get("value"),
                    unit=t.get("unit") or "",
                    ref_low=t.get("ref_low"),
                    ref_high=t.get("ref_high"),
                    flag=FlagStatus(t_flag) if t_flag in FlagStatus._value2member_map_ else FlagStatus.UNKNOWN,
                )
                gauge_html = render_range_gauge_html(t_obj)
                if gauge_html:
                    st.markdown(gauge_html, unsafe_allow_html=True)

                explanation_str = t.get(f"explanation_{lang}") or t.get("explanation_en", "")
                clean_exp_html = explanation_str.replace("\n", "<br>")
                st.markdown(
                    f"""
                    <div style="background: #f8fafc; border-left: 3px solid #0d9488; border-radius: 6px; padding: 12px 14px; margin-top: 10px; font-size: 14px; line-height: 1.6; color: #1e293b;">
                        {clean_exp_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                t_questions = t.get("doctor_questions", [])
                if t_questions:
                    st.markdown(
                        f"""
                        <div style="margin-top: 8px; font-size: 13px; color: #475569;">
                            <strong>Suggested Questions for Your Physician:</strong>
                            <ul style="margin: 4px 0 0 16px; padding: 0;">
                                {''.join(f'<li>{q}</li>' for q in t_questions)}
                            </ul>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                sources = t.get("source_urls", [])
                if sources:
                    links = " | ".join([f"[MedlinePlus Reference Source]({s})" for s in sources[:2]])
                    st.caption(f"📚 {links}")

                st.markdown("</div>", unsafe_allow_html=True)

    # Doctor Discussion Brief PDF Download
    st.markdown("### 📥 Doctor Discussion Preparation")
    doc_col1, doc_col2 = st.columns([2, 1])
    with doc_col1:
        st.markdown("**Personalized Questions to Ask Your Doctor:**")
        questions = exp.get("doctor_questions", [])
        if not questions:
            questions = [
                "What clinical factors might be contributing to my flagged laboratory values?",
                "Do these results warrant any dietary modifications, lifestyle changes, or follow-up repeat testing?",
                "Could any current medications or supplements have influenced these specific test numbers?",
            ]
        for q in questions:
            st.markdown(f"- ❓ {q}")

    with doc_col2:
        st.markdown("**Export Clinical Document:**")
        try:
            pdf_data = client.download_doctor_brief_pdf(job_id)
            clean_filename = f"doctor_brief_{job_id[:8]}.pdf"
            st.download_button(
                label="📄 Download Doctor Brief PDF",
                data=pdf_data,
                file_name=clean_filename,
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key="btn_download_brief_pdf",
            )
        except Exception as exc:
            st.caption(f"PDF download available once generated: {exc}")

    # Conversational Clinical Q&A
    st.divider()
    st.markdown("### 💬 Ask Questions About Your Lab Report")
    st.caption("Ask educational questions about your biomarkers, reference ranges, or biological functions. Answers are grounded in MedlinePlus clinical guidelines.")

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_query = st.chat_input("Ask a question (e.g. 'What does my low hemoglobin level mean?')", key="chat_input_qa")
    if user_query:
        st.session_state["chat_history"].append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Consulting clinical guidelines and report context..."):
                try:
                    qa_res = client.ask_question(
                        job_id=job_id,
                        question=user_query,
                        chat_history=st.session_state["chat_history"][-6:],
                    )
                    ans = qa_res.get(f"answer_{lang}") or qa_res.get("answer_en", "")
                    disclaimer = qa_res.get("disclaimer", "")
                    full_reply = f"{ans}\n\n*_{disclaimer}_*"

                    st.markdown(full_reply)
                    st.session_state["chat_history"].append({"role": "assistant", "content": full_reply})

                    src_urls = qa_res.get("source_urls", [])
                    if src_urls:
                        st.caption(f"📚 Sources: {', '.join(src_urls[:2])}")

                except Exception as exc:
                    err_msg = f"Sorry, I could not answer that right now: {exc}"
                    st.error(err_msg)
                    st.session_state["chat_history"].append({"role": "assistant", "content": err_msg})


# =====================================================================
# MAIN ROUTER
# =====================================================================

def main():
    """Main Streamlit application entrypoint with state-based routing."""
    init_session_state()
    is_authenticated = bool(st.session_state.get("access_token"))

    st.set_page_config(
        page_title="AI Clinical Lab Report Explainer",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="expanded" if is_authenticated else "collapsed",
    )
    set_custom_styles()

    client = get_api_client()
    backend_online = check_api_health()

    # Route 1: If authenticated, always direct to workspace dashboard
    if is_authenticated:
        render_authenticated_workspace(client, backend_online)
        return

    # Route 2: Unauthenticated view routing based on session state
    view = st.session_state.get("view", "landing")

    if view == "login":
        render_login_page(client)
    elif view == "register":
        render_register_page(client)
    else:
        render_landing_page(client, backend_online)


if __name__ == "__main__":
    main()
