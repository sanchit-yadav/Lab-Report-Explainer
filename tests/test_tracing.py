"""Tests for observability and distributed tracing module."""

import pytest
import time
from src.tracing.langfuse_setup import LocalSpan, LocalTrace, Tracer, calculate_cost, get_tracer


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
            with tracer.span("failing_step", parent_trace=trace) as fail_span:
                raise ValueError("Deliberate failure")

    assert trace.elapsed_ms > 0
    assert len(trace.spans) == 2
    assert trace.spans[0].name == "extraction_step"
    assert trace.spans[0].outputs["tests_found"] == 5
    assert trace.spans[0].elapsed_ms > 0
    assert trace.spans[1].name == "failing_step"
    assert "Deliberate failure" in trace.spans[1].error
