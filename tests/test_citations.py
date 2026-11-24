"""Comprehensive unit and integration test suite for Phase 4: Citations & Attribution.

Verifies:
1. Schema conformity: {claim, source_ids[]} with typed ReportFieldSource and KBChunkSource.
2. KB Manifest: authoritative catalog of 30 clinical reference guidelines with versioning.
3. Programmatic Verification: catches missing, empty, or hallucinated source IDs.
4. Semantic Verification: catches numerical distortions, concept mismatches, and contradictions.
5. UI Formatting: inline numeric anchors, enumerated bibliography, and UI JSON payloads.
6. Pipeline Integration: explain stage produces structured citations and output_guard verifies them.
"""

from __future__ import annotations


from src.citations.formatter import CitationFormatter
from src.citations.manifest import KBManifestManager
from src.citations.models import (
    AttributedClaim,
    CitationRegistry,
    KBChunkSource,
    ReportFieldSource,
    SourceKind,
    VerificationStatus,
)
from src.citations.verifier import CitationVerifier
from src.extraction.schema import FlagStatus
from src.stages.schemas import (
    ExplainInput,
    ExplainOutput,
    ExtractValuesOutput,
    ExtractionOutputItem,
    OutputGuardInput,
    OutputGuardOutput,
    RetrievedChunk,
    RetrieveOutput,
)
from src.stages.explain import ExplainStage
from src.stages.output_guard import OutputGuardStage


# ==============================================================================
# 1. Models & Registry Tests
# ==============================================================================

def test_citation_models_and_schema():
    """Verify pydantic schemas for ReportFieldSource, KBChunkSource, and AttributedClaim."""
    rep_src = ReportFieldSource(
        source_id="report:glucose:p1:l4",
        test_name="Fasting Blood Glucose",
        value=110.0,
        unit="mg/dL",
        ref_range="70 - 99",
        flag="HIGH",
        source_page=1,
        source_location="line_4",
    )
    assert rep_src.kind == SourceKind.REPORT_FIELD
    assert "Page 1, line_4" in rep_src.to_citation_label()
    assert "110.0 mg/dL" in rep_src.to_citation_label()

    kb_src = KBChunkSource(
        source_id="kb:medlineplus_fasting_blood_glucose:sec_what_it_measures",
        doc_id="medlineplus_fasting_blood_glucose",
        title="Fasting Blood Glucose",
        section="What the Test Measures",
        url="https://medlineplus.gov/lab-tests/blood-glucose-test/",
        version="2024.1",
        review_date="2024-05-15",
        text_excerpt="Measures circulating blood sugar concentration after an overnight fast.",
    )
    assert kb_src.kind == SourceKind.KB_CHUNK
    assert "v2024.1" in kb_src.to_citation_label()

    claim = AttributedClaim(
        claim_id="c1",
        claim="Your fasting blood glucose of 110.0 mg/dL is elevated above normal.",
        source_ids=[rep_src.source_id, kb_src.source_id],
    )
    assert len(claim.source_ids) == 2
    assert claim.verification_status == VerificationStatus.PENDING


def test_citation_registry_registration():
    """Verify registry methods for storing and retrieving sources."""
    registry = CitationRegistry()
    r_src = registry.register_report_field(
        test_name="Total Cholesterol",
        value=240.0,
        unit="mg/dL",
        ref_range="< 200",
        flag="HIGH",
        source_page=1,
        source_location="line_10",
    )
    kb_src = registry.register_kb_chunk(
        doc_id="medlineplus_total_cholesterol",
        title="Total Cholesterol",
        section="What Elevated / High Values Mean",
        url="https://medlineplus.gov/cholesterol.html",
        text_excerpt="Higher levels can build up in artery walls.",
    )

    assert registry.has_source(r_src.source_id) is True
    assert registry.has_source(kb_src.source_id) is True
    assert registry.has_source("report:non_existent:p1:l1") is False

    retrieved = registry.get_source(r_src.source_id)
    assert retrieved is not None
    assert retrieved.test_name == "Total Cholesterol"


# ==============================================================================
# 2. Knowledge Base Manifest Tests
# ==============================================================================

def test_kb_manifest_manager_document_catalog():
    """Verify KB manifest contains all 30 authoritative clinical reference documents."""
    manager = KBManifestManager()
    manifest = manager.get_manifest()

    assert manifest.manifest_version == "1.0.0"
    assert manifest.total_documents == 30
    assert len(manifest.documents) == 30

    # Test lookup by doc_id
    doc = manager.get_document("medlineplus_fasting_blood_glucose")
    assert doc is not None
    assert doc.test_name == "Fasting Blood Glucose"
    assert doc.category == "Diabetes & Metabolism"
    assert doc.version == "2024.1"
    assert len(doc.sections) >= 3

    # Test lookup by test name
    doc_by_name = manager.get_document("serum creatinine")
    assert doc_by_name is not None
    assert "creatinine" in doc_by_name.doc_id


# ==============================================================================
# 3. Citation Verifier Tests (Programmatic & Semantic)
# ==============================================================================

def test_citation_verifier_programmatic_check():
    """Verify programmatic source existence checks."""
    registry = CitationRegistry()
    valid_src = registry.register_report_field(
        test_name="Hemoglobin",
        value=11.2,
        unit="g/dL",
        ref_range="13.5 - 17.5",
        flag="LOW",
        source_page=1,
        source_location="line_2",
    )

    verifier = CitationVerifier()

    # Valid source ID
    valid_claim = AttributedClaim(
        claim="Hemoglobin level is 11.2 g/dL.",
        source_ids=[valid_src.source_id],
    )
    ok, errs = verifier.verify_claim_programmatic(valid_claim, registry)
    assert ok is True
    assert len(errs) == 0

    # Hallucinated source ID
    bad_claim = AttributedClaim(
        claim="Hemoglobin is 11.2 g/dL.",
        source_ids=["report:hallucinated_analyte:p99:l1"],
    )
    ok, errs = verifier.verify_claim_programmatic(bad_claim, registry)
    assert ok is False
    assert "hallucinated source ID" in errs[0]

    # Empty source IDs
    empty_claim = AttributedClaim(
        claim="No sources provided.",
        source_ids=[],
    )
    ok, errs = verifier.verify_claim_programmatic(empty_claim, registry)
    assert ok is False
    assert "uncited claim" in errs[0]


def test_citation_verifier_semantic_check_supported_report_field():
    """Verify semantic support when claim accurately reflects extracted report fields."""
    registry = CitationRegistry()
    r_src = registry.register_report_field(
        test_name="Fasting Blood Glucose",
        value=126.0,
        unit="mg/dL",
        ref_range="70 - 99",
        flag="HIGH",
        source_page=1,
        source_location="line_5",
    )

    verifier = CitationVerifier()
    claim = AttributedClaim(
        claim="Your Fasting Blood Glucose of 126.0 mg/dL is elevated.",
        source_ids=[r_src.source_id],
    )

    verified = verifier.verify_claim(claim, registry)
    assert verified.verification_status == VerificationStatus.VERIFIED
    assert "semantically supported" in verified.verification_reason.lower()


def test_citation_verifier_semantic_check_detects_numerical_distortion():
    """Verify semantic check catches hallucinated or distorted numbers in claims."""
    registry = CitationRegistry()
    r_src = registry.register_report_field(
        test_name="Fasting Blood Glucose",
        value=126.0,
        unit="mg/dL",
        ref_range="70 - 99",
        flag="HIGH",
        source_page=1,
        source_location="line_5",
    )

    verifier = CitationVerifier(strict_numerical_match=True)
    # Claim asserts 195.0 mg/dL which does not exist in the source report field
    distorted_claim = AttributedClaim(
        claim="Your Fasting Blood Glucose is 195.0 mg/dL, which is critically high.",
        source_ids=[r_src.source_id],
    )

    verified = verifier.verify_claim(distorted_claim, registry)
    assert verified.verification_status == VerificationStatus.UNSUPPORTED
    assert "does not contain cited number" in verified.verification_reason


def test_citation_verifier_semantic_check_supported_kb_chunk():
    """Verify semantic check succeeds when claim aligns with KB guideline content."""
    registry = CitationRegistry()
    kb_src = registry.register_kb_chunk(
        doc_id="medlineplus_fasting_blood_glucose",
        title="Fasting Blood Glucose Test",
        section="What the Test Measures",
        url="https://medlineplus.gov/lab-tests/blood-glucose-test/",
        text_excerpt="Measures circulating blood sugar concentration after an overnight fast of at least 8 hours.",
    )

    verifier = CitationVerifier()
    valid_claim = AttributedClaim(
        claim="Fasting blood glucose measures circulating blood sugar concentration in your body.",
        source_ids=[kb_src.source_id],
    )

    verified = verifier.verify_claim(valid_claim, registry)
    assert verified.verification_status == VerificationStatus.VERIFIED


def test_citation_verifier_batch_accuracy_scoring():
    """Verify batch accuracy calculation across a set of claims."""
    registry = CitationRegistry()
    src = registry.register_report_field(
        test_name="ALT",
        value=65.0,
        unit="U/L",
        ref_range="7 - 56",
        flag="HIGH",
    )

    claims = [
        AttributedClaim(claim="ALT result is 65.0 U/L.", source_ids=[src.source_id]),
        AttributedClaim(claim="ALT result is 999.0 U/L.", source_ids=[src.source_id]),  # Unsupported
        AttributedClaim(claim="Uncited statement.", source_ids=[]),                      # Missing
    ]

    verifier = CitationVerifier()
    res = verifier.verify_all_claims(claims, registry)

    assert res["total_claims"] == 3
    assert res["verified_claims"] == 1
    assert res["unsupported_claims"] == 1
    assert res["missing_source_claims"] == 1
    assert res["citation_accuracy"] == round(1 / 3, 4)
    assert res["is_fully_grounded"] is False


# ==============================================================================
# 4. Formatter & UI Presentation Tests
# ==============================================================================

def test_citation_formatter_inline_and_bibliography():
    """Verify inline anchor insertion and enumerated bibliography generation."""
    registry = CitationRegistry()
    r_src = registry.register_report_field(
        test_name="HbA1c",
        value=7.2,
        unit="%",
        ref_range="4.0 - 5.6",
        flag="HIGH",
        source_page=1,
        source_location="line_8",
    )
    kb_src = registry.register_kb_chunk(
        doc_id="medlineplus_hba1c",
        title="HbA1c Glycated Hemoglobin Test",
        section="What Elevated Values Mean",
        url="https://medlineplus.gov/lab-tests/hemoglobin-a1c-hba1c-test/",
        text_excerpt="HbA1c levels 6.5% or higher indicate diabetes.",
    )

    claims = [
        AttributedClaim(
            claim="HbA1c measures average blood sugar over the past 2 to 3 months.",
            source_ids=[kb_src.source_id],
            verification_status=VerificationStatus.VERIFIED,
        ),
        AttributedClaim(
            claim="Your HbA1c is 7.2%, which is above the 5.6% reference bound.",
            source_ids=[r_src.source_id],
            verification_status=VerificationStatus.VERIFIED,
        ),
    ]

    annotated_text, bib = CitationFormatter.format_inline_with_bibliography(claims, registry)

    assert "[1]" in annotated_text
    assert "[2]" in annotated_text
    assert "### References & Clinical Grounding Sources" in bib
    assert "HbA1c Glycated Hemoglobin Test" in bib
    assert "Page 1, Location: line_8" in bib


def test_citation_formatter_ui_payload():
    """Verify structured UI JSON payload suitable for React/Vue components."""
    registry = CitationRegistry()
    r_src = registry.register_report_field(
        test_name="Serum Creatinine",
        value=1.8,
        unit="mg/dL",
        ref_range="0.7 - 1.3",
        flag="HIGH",
        source_page=2,
        source_location="line_14",
    )

    claims = [
        AttributedClaim(
            claim_id="creat_c1",
            claim="Your Serum Creatinine is 1.8 mg/dL.",
            source_ids=[r_src.source_id],
            verification_status=VerificationStatus.VERIFIED,
            verification_reason="Semantically supported by report field.",
        )
    ]

    payload = CitationFormatter.format_ui_payload(claims, registry)
    assert payload["total_claims"] == 1
    assert len(payload["claims"]) == 1

    claim_data = payload["claims"][0]
    assert claim_data["claim_id"] == "creat_c1"
    assert claim_data["verification_status"] == "VERIFIED"
    assert len(claim_data["citations"]) == 1
    assert claim_data["citations"][0]["type"] == "report_field"
    assert claim_data["citations"][0]["value"] == 1.8


# ==============================================================================
# 5. Pipeline Stages Integration Tests
# ==============================================================================

def test_pipeline_stages_citation_grounding():
    """Verify end-to-end citation emission in ExplainStage and verification in OutputGuardStage."""
    # 1. Setup mock extraction output
    item = ExtractionOutputItem(
        test_name="Fasting Blood Glucose",
        value=115.0,
        unit="mg/dL",
        ref_low=70.0,
        ref_high=99.0,
        flag=FlagStatus.HIGH,
        ref_raw="70 - 99",
        source_page=1,
        source_bbox_or_line="line_4",
        confidence=0.98,
    )
    ext_out = ExtractValuesOutput(
        request_id="req_cit_test",
        items=[item],
        analyte_count=1,
        flagged_count=1,
        critical_count=0,
    )

    # 2. Setup mock retrieved knowledge chunk
    chunk = RetrievedChunk(
        chunk_id="chk_glucose_1",
        doc_id="medlineplus_fasting_blood_glucose",
        title="Fasting Blood Glucose Test",
        text="Measures blood glucose concentration after an overnight fast. Values between 100-125 mg/dL indicate impaired fasting glucose.",
        score=0.92,
        source_url="https://medlineplus.gov/lab-tests/blood-glucose-test/",
    )
    ret_out = RetrieveOutput(
        request_id="req_cit_test",
        chunks_by_query={"Fasting Blood Glucose high lab test meaning": [chunk]},
        total_chunks=1,
    )

    # 3. Run ExplainStage
    explain_stage = ExplainStage()
    exp_in = ExplainInput(
        request_id="req_cit_test",
        extraction=ext_out,
        retrieved_knowledge=ret_out,
        explain_all=True,
    )
    exp_out: ExplainOutput = explain_stage(exp_in)

    assert len(exp_out.test_explanations) == 1
    explained_item = exp_out.test_explanations[0]

    # Verify structured claims were created
    assert len(explained_item.claims) >= 2
    assert len(explained_item.sources) >= 1
    assert explained_item.bibliography is not None
    assert explained_item.ui_citation_payload is not None

    # 4. Run OutputGuardStage
    guard_stage = OutputGuardStage()
    guard_in = OutputGuardInput(
        request_id="req_cit_test",
        explanation=exp_out,
        extracted_items=[item],
    )
    guard_out: OutputGuardOutput = guard_stage(guard_in)

    assert guard_out.is_safe is True
    assert guard_out.citation_accuracy == 1.0
    assert guard_out.total_verified_citations >= 2
    assert len(guard_out.sanitized_explanations) == 1

    sanitized_item = guard_out.sanitized_explanations[0]
    for c in sanitized_item.claims:
        assert c.verification_status == VerificationStatus.VERIFIED
