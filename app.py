"""AI Clinical Lab Report Explainer — Streamlit Web Application.

Industry-grade Extraction + RAG system with deterministic flagging,
clinical guardrails, bilingual output (English + Hindi), and telemetry.
"""

from __future__ import annotations

import io
from pathlib import Path
import time
from typing import Dict, List, Optional

import streamlit as st

from src.config import get_config
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
        input_mode = st.radio("Choose Input Mode", ["Sample Reports", "Upload Custom PDF"])

        selected_pdf_source = None
        report_display_name = ""

        if input_mode == "Sample Reports":
            sample_choice = st.selectbox("Select a benchmark sample:", list(SAMPLE_OPTIONS.keys()))
            sample_file = SAMPLE_OPTIONS[sample_choice]
            selected_pdf_source = SAMPLE_DIR / sample_file
            report_display_name = sample_choice
        else:
            uploaded_file = st.file_uploader("Upload Laboratory Report (PDF)", type=["pdf"])
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
    st.subheader("💬 " + ("Ask Questions About Your Report" if lang == "en" else "अपनी रिपोर्ट के बारे में सवाल पूछें"))

    st.markdown(
        "<div class='disclaimer-banner'>"
        + (
            "🔒 <b>Protected by Layer 1 Guardrails:</b> You can ask about general medical terms, dietary recommendations, or test meanings. "
            "Questions seeking personal medical diagnoses or prescription medications will be safely filtered."
            if lang == "en"
            else "🔒 <b>सुरक्षा गार्डरेल्स द्वारा सुरक्षित:</b> आप सामान्य चिकित्सीय शब्दों, खानपान या परीक्षणों के अर्थ पूछ सकते हैं। "
            "दवाओं के नाम या व्यक्तिगत बीमारी के निदान संबंधी सवालों को सुरक्षा नीति के तहत रोका जाता है।"
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    # Sample prompt buttons
    st.markdown("**" + ("Sample prompts to try:" if lang == "en" else "पूछने के उदाहरण:") + "**")
    col1, col2, col3 = st.columns(3)
    prompt_to_fill = ""
    with col1:
        if st.button("🥗 " + ("Dietary tips for lipids", "लिपिड के लिए आहार टिप्स")[lang == "hi"]):
            prompt_to_fill = "What dietary changes can help manage cholesterol levels?"
    with col2:
        if st.button("🔬 " + ("Explain creatinine role", "क्रिएटिनिन का महत्व")[lang == "hi"]):
            prompt_to_fill = "What is the physiological role of serum creatinine in the body?"
    with col3:
        if st.button("🛡️ " + ("Test Guardrail (Blocked)", "सुरक्षा गार्डरेल टेस्ट")[lang == "hi"]):
            prompt_to_fill = "What dosage of Atorvastatin should I take to cure my high cholesterol?"

    user_q = st.text_input(
        "Enter your question:" if lang == "en" else "अपना प्रश्न यहाँ लिखें:",
        value=prompt_to_fill,
        placeholder="e.g. What does a high triglyceride level mean?",
    )

    if st.button("Ask Assistant" if lang == "en" else "पूछें", type="primary", use_container_width=True):
        if not user_q.strip():
            st.warning("Please enter a question first." if lang == "en" else "कृपया पहले कोई प्रश्न लिखें।")
            return

        with st.spinner("Analyzing question through clinical RAG pipeline..." if lang == "en" else "विश्लेषण किया जा रहा है..."):
            ans_res = pipeline.answer_question(user_q, patient_context=report_summary)

        if ans_res.get("blocked"):
            st.markdown(
                f"""
                <div class="safety-alert">
                    <b>🛡️ Guardrail Blocked Request ({ans_res.get('category')}):</b><br/>
                    {ans_res['answer_en'] if lang == 'en' else ans_res['answer_hi']}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            ans_text = ans_res["answer_en"] if lang == "en" else ans_res["answer_hi"]
            st.markdown(f"### {'Response' if lang == 'en' else 'उत्तर'}")
            st.write(ans_text)

            if ans_res.get("source_urls"):
                st.markdown(f"**{'Cited Guidelines' if lang == 'en' else 'प्रमाणित स्रोत'}:**")
                for u in ans_res["source_urls"]:
                    st.markdown(f"- 🔗 [{u}]({u})")

            st.caption(
                f"⏱️ Latency: {ans_res.get('elapsed_ms', 0):.1f}ms | 💰 Cost: ${ans_res.get('cost_usd', 0.0):.6f} USD"
            )


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
        st.info("👈 Please select a sample report or upload a PDF report in the sidebar to begin.")
        return

    # Process Report Trigger
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_analysis = st.button("🚀 Analyze Lab Report", type="primary", use_container_width=True)

    if run_analysis or "last_report_result" in st.session_state:
        # Check if new report selected
        current_id = f"{report_name}_{explain_all}"
        if run_analysis or st.session_state.get("current_report_id") != current_id:
            with st.spinner("Processing PDF: 3-tier extraction, deterministic flagging, and clinical RAG..."):
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

        # Patient Info Header
        raw_report: Optional[LabReport] = explanation.raw_report
        patient_name = explanation.patient_name or (raw_report.patient_name if raw_report else "Patient")
        report_date = explanation.report_date or (raw_report.report_date if raw_report else "Recent")
        lab_name = raw_report.lab_name if raw_report else "Diagnostic Pathology"

        st.markdown(
            f"**Patient:** `{patient_name}` | **Date:** `{report_date}` | **Laboratory:** `{lab_name}`"
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
        st.subheader("\U0001f52c " + ("Analyte Breakdown & Findings" if lang_code == "en" else "\u092a\u0930\u0940\u0915\u094d\u0937\u0923 \u092a\u0930\u093f\u0923\u093e\u092e \u090f\u0935\u0902 \u0935\u093f\u0938\u094d\u0924\u0943\u0924 \u091c\u093e\u0928\u0915\u093e\u0930\u0940"))

        # Zero-extraction feedback \u2014 show helpful explanation instead of blank screen
        if explanation.total_tests == 0:
            extraction_method = getattr(raw_report, "extraction_method", "unknown") if raw_report else "unknown"
            st.warning(
                "\u26a0\ufe0f **No test data could be automatically extracted from this PDF.**\n\n"
                "This may happen with scanned, image-based, or unusually formatted reports.\n\n"
                f"**Extraction method attempted:** `{extraction_method}`\n\n"
                "**Suggestions:**\n"
                "- Upload a **digital (text-based) PDF** for best results.\n"
                "- If you have a scanned report, ensure your `GEMINI_API_KEY` is configured "
                "for Vision-based OCR extraction (Tier 3).\n"
                "- Some reports use non-standard column headers \u2014 check that the PDF is not password-protected or corrupted."
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

        # Interactive Q&A Section
        render_qa_section(pipeline, summary_text, lang_code)


if __name__ == "__main__":
    main()
