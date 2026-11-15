"""Unit tests for Prometheus telemetry instruments and metrics exporter."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from src.api.main import app
from src.api.metrics import (
    MetricsRegistry,
    PrometheusCounter,
    PrometheusGauge,
    PrometheusHistogram,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_prometheus_counter_operations():
    """Test Counter increments and label rendering."""
    counter = PrometheusCounter(
        name="test_counter_total",
        help_text="Test counter metric.",
        label_names=["method", "status"],
    )
    assert counter.get(method="GET", status="200") == 0.0

    counter.inc(1.0, method="GET", status="200")
    counter.inc(2.5, method="GET", status="200")
    assert counter.get(method="GET", status="200") == 3.5

    with pytest.raises(ValueError, match="non-negative"):
        counter.inc(-1.0, method="GET", status="200")

    rendered = "\n".join(counter.render())
    assert "# HELP test_counter_total Test counter metric." in rendered
    assert "# TYPE test_counter_total counter" in rendered
    assert 'test_counter_total{method="GET",status="200"} 3.5' in rendered


def test_prometheus_gauge_operations():
    """Test Gauge set, inc, and dec operations."""
    gauge = PrometheusGauge(
        name="test_gauge_active",
        help_text="Active workers gauge.",
    )
    assert gauge.get() == 0.0

    gauge.set(5.0)
    assert gauge.get() == 5.0

    gauge.inc(2.0)
    assert gauge.get() == 7.0

    gauge.dec(3.0)
    assert gauge.get() == 4.0

    rendered = "\n".join(gauge.render())
    assert "# TYPE test_gauge_active gauge" in rendered
    assert "test_gauge_active 4.0" in rendered


def test_prometheus_histogram_buckets_and_summary():
    """Test Histogram observation, cumulative buckets, sum, and count."""
    hist = PrometheusHistogram(
        name="test_request_duration_seconds",
        help_text="Duration histogram.",
        buckets=(0.1, 0.5, 1.0, float("inf")),
        label_names=["endpoint"],
    )

    hist.observe(0.05, endpoint="/upload")
    hist.observe(0.3, endpoint="/upload")
    hist.observe(0.8, endpoint="/upload")
    hist.observe(2.5, endpoint="/upload")

    rendered = "\n".join(hist.render())
    assert "# TYPE test_request_duration_seconds histogram" in rendered
    assert 'test_request_duration_seconds_bucket{endpoint="/upload",le="0.1"} 1' in rendered
    assert 'test_request_duration_seconds_bucket{endpoint="/upload",le="0.5"} 2' in rendered
    assert 'test_request_duration_seconds_bucket{endpoint="/upload",le="1.0"} 3' in rendered
    assert 'test_request_duration_seconds_bucket{endpoint="/upload",le="+Inf"} 4' in rendered
    assert 'test_request_duration_seconds_count{endpoint="/upload"} 4' in rendered
    assert 'test_request_duration_seconds_sum{endpoint="/upload"} 3.650000' in rendered


def test_metrics_registry_render_all():
    """Test that MetricsRegistry exports all instruments in Prometheus text format."""
    registry = MetricsRegistry.get_instance()
    output = registry.render_all()
    assert "lab_report_http_requests_total" in output
    assert "lab_report_http_request_duration_seconds" in output
    assert "lab_report_jobs_total" in output
    assert "lab_report_active_jobs_gauge" in output
    assert "lab_report_guardrail_blocks_total" in output
    assert "lab_report_panic_values_detected_total" in output


def test_metrics_endpoint_http(client):
    """Test GET /metrics returns HTTP 200 with text/plain exposition format."""
    # First make a request to ensure traffic is tracked
    client.get("/healthz")

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "version=0.0.4" in resp.headers["content-type"]
    assert "lab_report_http_requests_total" in resp.text
