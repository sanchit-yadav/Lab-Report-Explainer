"""Tests for observability and distributed tracing module."""

import time

import pytest

from src.tracing.langfuse_setup import LocalSpan, LocalTrace, calculate_cost, get_tracer


def test_calculate_cost():
    """Verify accurate pricing calculations per model."""
    # gemini-3.1-flash-lite: $0.25/M input, $1.50/M output
    cost_lite = calculate_cost("gemini-3.1-flash-lite", 1_000_000, 1_000_000)
    assert pytest.approx(cost_lite, 0.001) == 1.75

    # gemini-embedding-2: $0.05/M input, $0.00/M output
    cost_embed = calculate_cost("gemini-embedding-2", 1_000_000, 0)
    assert pytest.approx(cost_embed, 0.001) == 0.05

    # Default fallback
    cost_default = calculate_cost("unknown-model", 1_000_000, 1_000_000)
    assert pytest.approx(cost_default, 0.001) == 1.75


def test_local_span():
    """Test LocalSpan creation, metadata setting, and error recording."""
    span = LocalSpan("test_span")
    span.set_input(param="value")
    span.set_output(result=42)
    span.set_metadata(run_id="abc")

    assert span.inputs == {"param": "value"}
    assert span.outputs == {"result": 42}
    assert span.metadata == {"run_id": "abc"}
    assert span.error is None


def test_local_trace():
    """Test LocalTrace aggregation of spans, token counts, and cost."""
    trace = LocalTrace("test_trace", {"user_id": "u123"})
    assert trace.name == "test_trace"
    assert trace.metadata == {"user_id": "u123"}
    assert len(trace.spans) == 0

    span = LocalSpan("child_span", trace)
    trace.add_span(span)
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "child_span"

    # Add tokens
    trace.add_tokens("gemini-3.1-flash-lite", input_tokens=1000, output_tokens=500)
    assert trace.total_input_tokens == 1000
    assert trace.total_output_tokens == 500
    expected_cost = (1000 / 1e6 * 0.25) + (500 / 1e6 * 1.50)
    assert pytest.approx(trace.total_cost_usd, 1e-6) == expected_cost


def test_tracer_context_managers():
    """Test Tracer context managers for traces and child spans."""
    tracer = get_tracer()

    with tracer.start_trace("test_pipeline_run", patient="P001") as trace:
        assert trace.name == "test_pipeline_run"
        assert trace.metadata.get("patient") == "P001"

        with tracer.span("extraction_step", parent_trace=trace) as span:
            span.set_input(path="dummy.pdf")
            time.sleep(0.01)
            span.set_output(tests_found=5)

        with pytest.raises(ValueError):
            with tracer.span("failing_step", parent_trace=trace):
                raise ValueError("Deliberate failure")

    assert trace.elapsed_ms > 0
    assert len(trace.spans) == 2
    assert trace.spans[0].name == "extraction_step"
    assert trace.spans[0].outputs["tests_found"] == 5
    assert trace.spans[0].elapsed_ms > 0
    assert trace.spans[1].name == "failing_step"
    assert "Deliberate failure" in trace.spans[1].error


def test_pii_safe_sanitization_in_spans():
    """Verify that sensitive PHI/PII fields are strictly redacted in span inputs/outputs."""
    span = LocalSpan("pii_test_span")
    span.set_input(
        patient_name="John Doe",
        email="john.doe@example.com",
        phone="555-123-4567",
        dob="01/01/1980",
        safe_param="biomarker_query",
    )
    span.set_output(
        patient_address="123 Main St, New York, NY",
        ssn="123-45-6789",
        count=10,
    )

    # Blocked keys should be redacted
    assert span.inputs["patient_name"] == "[PII_REDACTED]"
    assert span.inputs["email"] == "[EMAIL_REDACTED]"
    assert span.inputs["phone"] == "[PHONE_REDACTED]"
    assert span.inputs["dob"] == "[PII_REDACTED]"
    assert span.inputs["safe_param"] == "biomarker_query"

    assert span.outputs["patient_address"] == "[PII_REDACTED]"
    assert span.outputs["ssn"] == "[PII_REDACTED]"
    assert span.outputs["count"] == 10


def test_opentelemetry_export():
    """Verify OpenTelemetry OTLP compatible dictionary serialization."""
    trace = LocalTrace("otel_pipeline_trace", request_id="req-999-otel")
    span = LocalSpan("retrieve_stage", trace)
    span.set_input(query="Glucose High")
    span.set_output(results=3)
    trace.add_span(span)

    otel_dict = trace.to_otel_dict()
    assert "resource_spans" in otel_dict
    res_span = otel_dict["resource_spans"][0]
    assert res_span["resource"]["attributes"]["service.name"] == "ai-blood-report-explainer"
    spans = res_span["scope_spans"][0]["spans"]
    assert len(spans) == 1
    s = spans[0]
    assert s["trace_id"] == "req-999-otel"
    assert s["name"] == "retrieve_stage"
    assert s["status"]["code"] == "STATUS_CODE_OK"
    assert s["attributes"]["input.query"] == "Glucose High"
    assert s["attributes"]["output.results"] == "3"


def test_trace_stage_decorator():
    """Test the @trace_stage decorator with simulated stage objects."""
    from src.tracing.langfuse_setup import trace_stage

    class DummyInput:
        def __init__(self, req_id: str):
            self.request_id = req_id

    class DummyOutput:
        def __init__(self):
            self.items = [1, 2, 3]
            self.is_valid = True

    @trace_stage("dummy_stage")
    def run_dummy_stage(inp: DummyInput) -> DummyOutput:
        return DummyOutput()

    res = run_dummy_stage(DummyInput("req-stage-123"))
    assert res.is_valid is True
    assert len(res.items) == 3


def test_recent_traces_ring_buffer():
    """Verify Tracer stores and retrieves recent traces in a bounded ring buffer."""
    tracer = get_tracer()
    with tracer.start_trace("ring_buffer_test_trace", request_id="ring-123") as t:
        with tracer.span("inner_op", parent_trace=t) as s:
            s.set_output(done=True)

    recent = tracer.get_recent_traces(limit=10)
    assert len(recent) >= 1
    found = any(tr.get("trace_id") == "ring-123" for tr in recent)
    assert found
