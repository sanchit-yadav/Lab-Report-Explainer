"""AI Clinical Lab Report Explainer — Streamlit Web Application.

Industry-grade Extraction + RAG system with deterministic flagging,
clinical guardrails, bilingual output (English + Hindi), visual range gauges,
multi-turn interactive chat, and downloadable Doctor Discussion Brief PDFs.
"""

from __future__ import annotations

import io
from pathlib import Path
import time
from typing import Dict, List, Optional

import streamlit as st

from src.config import get_config
from src.explainer.pdf_export import generate_doctor_brief_pdf
from src.explainer.schema import ReportExplanation, TestExplanation
from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.pipeline import LabReportPipeline

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


@st.cache_resource(show_spinner="Initializing Clinical Lab Pipeline & Local Models...")
def load_pipeline() -> LabReportPipeline:
    """Cache the pipeline so embeddings and cross-encoders load once on startup."""
    return LabReportPipeline()


def set_custom_styles():
    st.markdown(
        """
        <style>
        .report-header {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            color: #ffffff;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .metric-card {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }
        .metric-card .value {
            font-size: 24px;
            font-weight: 700;
            color: #0f172a;
        }
        .metric-card .label {
            font-size: 13px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .test-card {
            border-radius: 10px;
            padding: 18px;
            margin-bottom: 16px;
            border: 1px solid #e2e8f0;
            background: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .badge {
            display: inline-block;
            padding: 3px 10px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 9999px;
            margin-left: 8px;
        }
        .disclaimer-banner {
            background-color: #eff6ff;
            border-left: 4px solid #3b82f6;
            padding: 14px 18px;
            border-radius: 6px;
            color: #1e40af;
            font-size: 14px;
            margin-bottom: 20px;
        }
        .safety-alert {
            background-color: #fef2f2;
            border-left: 4px solid #ef4444;
            padding: 14px 18px;
            border-radius: 6px;
            color: #991b1b;
            font-size: 14px;
            margin-bottom: 16px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(lang: str):
    title = "🩺 AI Clinical Lab Report Explainer"
    subtitle = (
        "Patient-centered, deterministic laboratory interpretation with MedlinePlus clinical RAG and strict medical safety guardrails."
        if lang == "en"
        else "मरीजों के लिए सरल लैब रिपोर्ट व्याख्याता — मेडिकल संदर्भ, सुरक्षा दिशानिर्देश और हिंदी अनुवाद के साथ।"
    )
    st.markdown(
        f"""
        <div class="report-header">
            <h1 style="margin: 0; font-size: 28px; color: #ffffff;">{title}</h1>
            <p style="margin: 8px 0 0 0; color: #94a3b8; font-size: 15px;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(pipeline: LabReportPipeline):
    with st.sidebar:
        st.header("⚙️ Configuration")

        lang = st.radio(
            "Select Language / भाषा चुनें",
            options=["🇬🇧 English", "🇮🇳 हिन्दी (Hindi)"],
            index=0,
        )
        lang_code = "en" if "English" in lang else "hi"

        st.markdown("---")
        st.subheader("📄 Select Report")
        input_mode = st.radio("Choose Input Mode", ["Sample Reports", "Upload PDF or Image (JPG/PNG)"])

        selected_pdf_source = None
        report_display_name = ""

        if input_mode == "Sample Reports":
            sample_choice = st.selectbox("Select a benchmark sample:", list(SAMPLE_OPTIONS.keys()))
            sample_file = SAMPLE_OPTIONS[sample_choice]
            selected_pdf_source = SAMPLE_DIR / sample_file
            report_display_name = sample_choice
        else:
            uploaded_file = st.file_uploader(
                "Upload Laboratory Report (PDF, JPG, PNG)",
                type=["pdf", "jpg", "jpeg", "png"],
            )
            if uploaded_file is not None:
                selected_pdf_source = uploaded_file.read()
                report_display_name = uploaded_file.name

        explain_all = st.checkbox(
            "Explain All Tests (including Normal)",
            value=False,
            help="By default, explanations focus on abnormal/flagged analytes. Check this to generate full explanations for normal tests as well.",
        )

        st.markdown("---")
        st.subheader("🛡️ System Telemetry & Safety")
        st.markdown(
            """
            - **Extraction:** 3-Tier Fallback (pdfplumber ➔ camelot ➔ Vision)
            - **Formats:** PDF, Scanned Images (JPG/PNG)
            - **Flagging:** 100% Deterministic Engine (Zero LLM)
            - **RAG:** ChromaDB + MS-Marco Cross-Encoder
            - **Model:** `gemini-3.1-flash-lite` (low-latency)
            - **Guardrails:** Triple-Layer Input/Output Redaction
            """
        )

        st.markdown("---")
        st.info(
            "⚠️ **Disclaimer:** For educational use only. Never substitute this output for professional medical advice, diagnosis, or treatment."
        )

    return lang_code, selected_pdf_source, report_display_name, explain_all


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

        return f"""
        <div style="margin-top: 10px; margin-bottom: 6px; padding: 0 4px;">
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 2px;">
                <span>Min: {d_min:.1f}</span>
                <span style="color: #15803d; font-weight: 600;">Optimal Range: {low} - {high} {test.unit}</span>
                <span>Max: {d_max:.1f}</span>
            </div>
            <div style="position: relative; width: 100%; height: 9px; border-radius: 4px; display: flex; overflow: hidden; background: #e2e8f0;">
                <div style="width: {p_low}%; background: #fed7aa;" title="Low zone"></div>
                <div style="width: {p_norm}%; background: #86efac;" title="Normal healthy zone"></div>
                <div style="width: {p_high}%; background: #fed7aa;" title="High zone"></div>
            </div>
            <div style="position: relative; width: 100%; height: 18px;">
                <div style="position: absolute; left: calc({p_val}% - 14px); top: -2px; text-align: center;">
                    <div style="font-size: 11px; font-weight: 900; color: {marker_color}; line-height: 1;">▲</div>
                    <div style="font-size: 10px; font-weight: 800; color: {marker_color}; line-height: 1;">{val}</div>
                </div>
            </div>
        </div>
        """

    # One-sided upper bound (< 200)
    elif high is not None:
        d_max = max(high * 1.5, val * 1.15) if val is not None else high * 1.5
        total = d_max
        if total <= 0:
            return ""

        p_norm = (high / total) * 100
        p_high = 100.0 - p_norm
        p_val = max(2.0, min(97.0, (val / total) * 100)) if val is not None else 50.0

        marker_color = "#dc2626" if test.flag == FlagStatus.CRITICAL_HIGH else ("#d97706" if test.flag == FlagStatus.HIGH else "#16a34a")

        return f"""
        <div style="margin-top: 10px; margin-bottom: 6px; padding: 0 4px;">
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 2px;">
                <span>0.0</span>
                <span style="color: #15803d; font-weight: 600;">Desirable: &lt; {high} {test.unit}</span>
                <span>{d_max:.1f}</span>
            </div>
            <div style="position: relative; width: 100%; height: 9px; border-radius: 4px; display: flex; overflow: hidden; background: #e2e8f0;">
                <div style="width: {p_norm}%; background: #86efac;" title="Normal healthy zone"></div>
                <div style="width: {p_high}%; background: #fed7aa;" title="High zone"></div>
            </div>
            <div style="position: relative; width: 100%; height: 18px;">
                <div style="position: absolute; left: calc({p_val}% - 14px); top: -2px; text-align: center;">
                    <div style="font-size: 11px; font-weight: 900; color: {marker_color}; line-height: 1;">▲</div>
                    <div style="font-size: 10px; font-weight: 800; color: {marker_color}; line-height: 1;">{val}</div>
                </div>
            </div>
        </div>
        """

    # One-sided lower bound (> 60)
    elif low is not None:
        d_max = max(low * 2.0, val * 1.25) if val is not None else low * 2.0
        total = d_max
        if total <= 0:
            return ""

        p_low = (low / total) * 100
        p_norm = 100.0 - p_low
        p_val = max(2.0, min(97.0, (val / total) * 100)) if val is not None else 50.0

        marker_color = "#dc2626" if test.flag == FlagStatus.CRITICAL_LOW else ("#d97706" if test.flag == FlagStatus.LOW else "#16a34a")

        return f"""
        <div style="margin-top: 10px; margin-bottom: 6px; padding: 0 4px;">
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 2px;">
                <span>0.0</span>
                <span style="color: #15803d; font-weight: 600;">Target: &gt; {low} {test.unit}</span>
                <span>{d_max:.1f}</span>
            </div>
            <div style="position: relative; width: 100%; height: 9px; border-radius: 4px; display: flex; overflow: hidden; background: #e2e8f0;">
                <div style="width: {p_low}%; background: #fed7aa;" title="Low zone"></div>
                <div style="width: {p_norm}%; background: #86efac;" title="Normal healthy zone"></div>
            </div>
            <div style="position: relative; width: 100%; height: 18px;">
                <div style="position: absolute; left: calc({p_val}% - 14px); top: -2px; text-align: center;">
                    <div style="font-size: 11px; font-weight: 900; color: {marker_color}; line-height: 1;">▲</div>
                    <div style="font-size: 10px; font-weight: 800; color: {marker_color}; line-height: 1;">{val}</div>
                </div>
            </div>
        </div>
        """

    return ""


def render_test_card(
    test: TestResult,
    explanation: Optional[TestExplanation],
    lang: str,
):
    flag_name, emoji, bg_color, text_color, border_color = FLAG_BADGES.get(
        test.flag, FLAG_BADGES[FlagStatus.UNKNOWN]
    )

    ref_str = test.ref_raw or (
        f"{test.ref_low} - {test.ref_high}" if test.ref_low is not None and test.ref_high is not None else "N/A"
    )

    # Generate visual range gauge
    gauge_html = render_range_gauge_html(test)

    card_html = f"""
    <div style="background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <span style="font-size: 17px; font-weight: 700; color: #1e293b;">{test.test_name}</span>
                <span class="badge" style="background-color: {border_color}; color: {text_color}; font-weight: 700;">
                    {emoji} {flag_name}
                </span>
            </div>
            <div style="text-align: right;">
                <span style="font-size: 20px; font-weight: 800; color: {text_color};">
                    {test.raw_value or test.value} <span style="font-size: 13px; font-weight: 500; color: #64748b;">{test.unit or ''}</span>
                </span>
                <div style="font-size: 12px; color: #64748b;">Ref: {ref_str}</div>
            </div>
        </div>
        {gauge_html}
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    if explanation:
        with st.expander(
            f"🔍 {'Detailed Explanation & Doctor Questions' if lang == 'en' else 'विस्तृत व्याख्या एवं डॉक्टर से पूछे जाने वाले सवाल'}",
            expanded=(test.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)),
        ):
            exp_text = explanation.explanation_en if lang == "en" else explanation.explanation_hi
            st.markdown(f"**{'Clinical Meaning' if lang == 'en' else 'जांच का अर्थ'}:** {exp_text}")

            if explanation.doctor_questions:
                st.markdown(f"**{'Questions to ask your doctor' if lang == 'en' else 'डॉक्टर से पूछने योग्य प्रश्न'}:**")
                for q in explanation.doctor_questions:
                    st.markdown(f"- 💬 {q}")

            if explanation.source_urls:
                st.markdown(f"**{'Educational Sources' if lang == 'en' else 'संदर्भ स्रोत'}:**")
                for url in explanation.source_urls:
                    st.markdown(f"- 🔗 [{url}]({url})")


def render_qa_section(pipeline: LabReportPipeline, report_summary: str, lang: str):
    st.markdown("---")
    st.subheader("💬 " + ("Interactive Clinical Assistant" if lang == "en" else "संवादात्मक चिकित्सीय सहायक"))

    st.markdown(
        "<div class='disclaimer-banner'>"
        + (
            "🔒 <b>Protected by Layer 1 Guardrails:</b> Ask about test meanings, dietary context, or medical jargon. "
            "Diagnosis phishing and prescription inquiries are automatically blocked."
            if lang == "en"
            else "🔒 <b>सुरक्षा गार्डरेल्स द्वारा सुरक्षित:</b> परीक्षण के अर्थ या खानपान के बारे में पूछें। "
            "दवा की खुराक या व्यक्तिगत बीमारी के निदान संबंधी सवालों को सुरक्षा नीति द्वारा रोका जाता है।"
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    # Initialize chat history in session state
    if "qa_chat_history" not in st.session_state:
        st.session_state["qa_chat_history"] = []

    # Quick prompt buttons row
    st.markdown("**" + ("Quick discussion prompts:" if lang == "en" else "त्वरित प्रश्न:") + "**")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 0.5])
    quick_query = None
    with c1:
        if st.button("🥗 " + ("Dietary tips for lipids", "लिपिड के लिए आहार टिप्स")[lang == "hi"], use_container_width=True):
            quick_query = "What dietary adjustments support healthier lipid and metabolic levels?"
    with c2:
        if st.button("🔬 " + ("Doctor discussion tips", "डॉक्टर से सवाल")[lang == "hi"], use_container_width=True):
            quick_query = "What follow-up questions should I prioritize when discussing this report with my doctor?"
    with c3:
        if st.button("🛡️ " + ("Test Guardrail (Blocked)", "गार्डरेल टेस्ट")[lang == "hi"], use_container_width=True):
            quick_query = "What dosage of Atorvastatin should I start taking for high cholesterol?"
    with c4:
        if st.button("🗑️ " + ("Clear", "साफ़")[lang == "hi"], use_container_width=True):
            st.session_state["qa_chat_history"] = []
            st.rerun()

    # Render previous conversation turns
    for msg in st.session_state["qa_chat_history"]:
        with st.chat_message(msg["role"]):
            if msg.get("blocked"):
                st.markdown(
                    f"""<div class="safety-alert">{msg["content"]}</div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(msg["content"])
                if msg.get("sources"):
                    st.caption("🔗 **Cited Guidelines:** " + ", ".join(f"[{s}]({s})" for s in msg["sources"]))

    # Handle user question input
    user_q = st.chat_input(
        "Ask a follow-up question about your lab results..." if lang == "en" else "अपनी रिपोर्ट के बारे में सवाल पूछें..."
    )

    active_query = quick_query or user_q
    if active_query:
        # Display user turn
        with st.chat_message("user"):
            st.markdown(active_query)
        st.session_state["qa_chat_history"].append({"role": "user", "content": active_query})

        # Process with pipeline
        with st.chat_message("assistant"):
            with st.spinner("Consulting verified clinical guidelines..." if lang == "en" else "दिशानिर्देशों की जाँच हो रही है..."):
                ans_res = pipeline.answer_question(
                    active_query,
                    patient_context=report_summary,
                    chat_history=st.session_state["qa_chat_history"][:-1],
                )

            if ans_res.get("blocked"):
                refusal_msg = (
                    f"🛡️ **Guardrail Blocked Request ({ans_res.get('category')}):**\n\n"
                    f"{ans_res['answer_en'] if lang == 'en' else ans_res['answer_hi']}"
                )
                st.markdown(
                    f"""<div class="safety-alert">{refusal_msg}</div>""",
                    unsafe_allow_html=True,
                )
                st.session_state["qa_chat_history"].append({
                    "role": "assistant",
                    "content": refusal_msg,
                    "blocked": True,
                })
            else:
                ans_text = ans_res["answer_en"] if lang == "en" else ans_res["answer_hi"]
                st.markdown(ans_text)
                sources = ans_res.get("source_urls", [])
                if sources:
                    st.caption("🔗 **Cited Guidelines:** " + ", ".join(f"[{u}]({u})" for u in sources))
                st.caption(
                    f"⏱️ Latency: {ans_res.get('elapsed_ms', 0):.1f}ms | 💰 Cost: ${ans_res.get('cost_usd', 0.0):.6f} USD"
                )

                st.session_state["qa_chat_history"].append({
                    "role": "assistant",
                    "content": ans_text,
                    "sources": sources,
                })


def main():
    st.set_page_config(
        page_title="AI Clinical Lab Report Explainer",
        page_icon="🩺",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    set_custom_styles()
    pipeline = load_pipeline()

    lang_code, selected_pdf_source, report_name, explain_all = render_sidebar(pipeline)
    render_header(lang_code)

    if selected_pdf_source is None:
        st.info("👈 Please select a sample report or upload a PDF/Image report in the sidebar to begin.")
        return

    # Process Report Trigger
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_analysis = st.button("🚀 Analyze Lab Report", type="primary", use_container_width=True)

    if run_analysis or "last_report_result" in st.session_state:
        # Check if new report selected
        current_id = f"{report_name}_{explain_all}"
        if run_analysis or st.session_state.get("current_report_id") != current_id:
            with st.spinner("Processing Document: 3-tier extraction, deterministic flagging, and clinical RAG..."):
                start_t = time.perf_counter()
                explanation: ReportExplanation = pipeline.process_report(
                    selected_pdf_source,
                    explain_all_tests=explain_all,
                )
                elapsed_s = time.perf_counter() - start_t
                st.session_state["last_report_result"] = explanation
                st.session_state["last_report_elapsed"] = elapsed_s
                st.session_state["current_report_id"] = current_id

        explanation: ReportExplanation = st.session_state["last_report_result"]
        elapsed_s: float = st.session_state.get("last_report_elapsed", 0.0)

        # Overview Metrics Row
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                f"""<div class="metric-card"><div class="value">{explanation.total_tests}</div><div class="label">Total Tests</div></div>""",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"""<div class="metric-card"><div class="value" style="color: {'#dc2626' if explanation.flagged_count > 0 else '#16a34a'};">{explanation.flagged_count}</div><div class="label">Out of Range</div></div>""",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"""<div class="metric-card"><div class="value">{elapsed_s:.2f}s</div><div class="label">Processing Time</div></div>""",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f"""<div class="metric-card"><div class="value">$0.0016</div><div class="label">Est. Cost (USD)</div></div>""",
                unsafe_allow_html=True,
            )

        st.markdown("<br/>", unsafe_allow_html=True)

        # Patient Info Header & Download Button Row
        raw_report: Optional[LabReport] = explanation.raw_report
        patient_name = explanation.patient_name or (raw_report.patient_name if raw_report else "Patient")
        report_date = explanation.report_date or (raw_report.report_date if raw_report else "Recent")
        lab_name = raw_report.lab_name if raw_report else "Diagnostic Pathology"

        col_pat, col_down = st.columns([2.5, 1.5])
        with col_pat:
            st.markdown(
                f"**Patient:** `{patient_name}` | **Date:** `{report_date}` | **Laboratory:** `{lab_name}`"
            )
        with col_down:
            if explanation.total_tests > 0:
                clean_pname = (patient_name or "Patient").replace(" ", "_")
                pdf_bytes = generate_doctor_brief_pdf(explanation, lang=lang_code)
                st.download_button(
                    label="📥 " + ("Download Doctor Brief (PDF)", "डॉक्टर सारांश डाउनलोड करें (PDF)")[lang_code == "hi"],
                    data=pdf_bytes,
                    file_name=f"Doctor_Brief_{clean_pname}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

        # Clinical Summary Callout
        summary_text = (
            explanation.report_summary_en if lang_code == "en" else explanation.report_summary_hi
        )
        st.markdown(
            f"""
            <div style="background-color: #f1f5f9; border-radius: 8px; padding: 18px; margin: 16px 0; border: 1px solid #cbd5e1;">
                <h4 style="margin: 0 0 8px 0; color: #1e293b;">📋 {'Executive Summary' if lang_code == 'en' else 'रिपोर्ट का मुख्य सारांश'}</h4>
                <p style="margin: 0; color: #334155; line-height: 1.6;">{summary_text}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Explanations map
        exp_by_name = {e.test_name: e for e in explanation.test_explanations}

        # Render Analyte Cards
        st.subheader("🔬 " + ("Analyte Breakdown & Findings" if lang_code == "en" else "परीक्षण परिणाम एवं विस्तृत जानकारी"))

        # Zero-extraction feedback
        if explanation.total_tests == 0:
            extraction_method = getattr(raw_report, "extraction_method", "unknown") if raw_report else "unknown"
            st.warning(
                "⚠️ **No test data could be automatically extracted from this document.**\n\n"
                "This may happen with scanned image files, photo uploads, or non-standard layouts.\n\n"
                f"**Extraction method attempted:** `{extraction_method}`\n\n"
                "**Suggestions:**\n"
                "- Upload a **digital (text-based) PDF** for instant zero-cost extraction.\n"
                "- For scanned image/photo uploads (`.jpg`, `.png`), ensure your `GEMINI_API_KEY` is configured in `.env` "
                "for Tier 3 Multimodal Vision OCR.\n"
                "- Ensure the image is well-lit, sharp, and the document is oriented upright."
            )
            return

        # If raw_report exists, show all tests in categorized fashion
        if raw_report and raw_report.tests:
            # Sort: Critical first, then High/Low, then Normal
            flag_order = {
                FlagStatus.CRITICAL_HIGH: 0,
                FlagStatus.CRITICAL_LOW: 0,
                FlagStatus.HIGH: 1,
                FlagStatus.LOW: 1,
                FlagStatus.ABNORMAL: 2,
                FlagStatus.UNKNOWN: 3,
                FlagStatus.NORMAL: 4,
            }
            sorted_tests = sorted(raw_report.tests, key=lambda t: flag_order.get(t.flag, 5))

            for test in sorted_tests:
                test_exp = exp_by_name.get(test.test_name)
                render_test_card(test, test_exp, lang_code)
        else:
            # Fallback to test_explanations
            for exp in explanation.test_explanations:
                mock_test = TestResult(
                    test_name=exp.test_name,
                    value=0.0,
                    flag=exp.flag,
                )
                render_test_card(mock_test, exp, lang_code)

        # Interactive Multi-Turn Q&A Section
        render_qa_section(pipeline, summary_text, lang_code)


if __name__ == "__main__":
    main()
