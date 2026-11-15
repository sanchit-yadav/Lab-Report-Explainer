"""Prometheus metrics exporter and ASGI telemetry middleware for the API microservice.

Provides thread-safe Prometheus counter, histogram, and gauge instruments adhering
to the Prometheus exposition format v0.0.4 without external runtime dependencies.
"""

from __future__ import annotations

from collections import defaultdict
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Default Prometheus latency histogram buckets (in seconds)
DEFAULT_LATENCY_BUCKETS: Tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")
)

# Test count histogram buckets (number of tests per report)
DEFAULT_COUNT_BUCKETS: Tuple[float, ...] = (
    1.0, 5.0, 10.0, 20.0, 35.0, 50.0, 100.0, float("inf")
)


def _format_labels(labels: Dict[str, str]) -> str:
    """Format dictionary labels into Prometheus label string format."""
    if not labels:
        return ""
    items = [f'{k}="{v}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(items) + "}"


class PrometheusCounter:
    """Thread-safe Prometheus Counter metric."""

    def __init__(self, name: str, help_text: str, label_names: Optional[List[str]] = None):
        self.name = name
        self.help_text = help_text
        self.label_names = set(label_names or [])
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Increment counter by amount (must be non-negative)."""
        if amount < 0:
            raise ValueError("Counter increments must be non-negative")
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] += amount

    def get(self, **labels: str) -> float:
        """Get current counter value for labels."""
        key = tuple(sorted(labels.items()))
        with self._lock:
            return self._values[key]

    def render(self) -> List[str]:
        """Render Prometheus exposition lines."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} counter",
        ]
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0.0")
            else:
                for key, val in sorted(self._values.items()):
                    lbl_str = _format_labels(dict(key))
                    lines.append(f"{self.name}{lbl_str} {val}")
        return lines


class PrometheusGauge:
    """Thread-safe Prometheus Gauge metric."""

    def __init__(self, name: str, help_text: str, label_names: Optional[List[str]] = None):
        self.name = name
        self.help_text = help_text
        self.label_names = set(label_names or [])
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **labels: str) -> None:
        """Set gauge value."""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Increment gauge value."""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] += amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        """Decrement gauge value."""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] -= amount

    def get(self, **labels: str) -> float:
        """Get current gauge value."""
        key = tuple(sorted(labels.items()))
        with self._lock:
            return self._values[key]

    def render(self) -> List[str]:
        """Render Prometheus exposition lines."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} gauge",
        ]
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0.0")
            else:
                for key, val in sorted(self._values.items()):
                    lbl_str = _format_labels(dict(key))
                    lines.append(f"{self.name}{lbl_str} {val}")
        return lines


class PrometheusHistogram:
    """Thread-safe Prometheus Histogram metric with cumulative bucket counters."""

    def __init__(
        self,
        name: str,
        help_text: str,
        buckets: Tuple[float, ...] = DEFAULT_LATENCY_BUCKETS,
        label_names: Optional[List[str]] = None,
    ):
        self.name = name
        self.help_text = help_text
        self.buckets = sorted(buckets)
        if self.buckets[-1] != float("inf"):
            self.buckets.append(float("inf"))
        self.label_names = set(label_names or [])
        self._counts: Dict[Tuple[Tuple[str, str], ...], Dict[float, int]] = defaultdict(
            lambda: {b: 0 for b in self.buckets}
        )
        self._sums: Dict[Tuple[Tuple[str, str], ...], float] = defaultdict(float)
        self._totals: Dict[Tuple[Tuple[str, str], ...], int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        """Record an observed sample value in buckets, sum, and total count."""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._sums[key] += float(value)
            self._totals[key] += 1
            b_dict = self._counts[key]
            for b in self.buckets:
                if value <= b:
                    b_dict[b] += 1

    def render(self) -> List[str]:
        """Render Prometheus exposition lines with _bucket, _sum, and _count."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            if not self._totals:
                # Render zeroed default
                for b in self.buckets:
                    le = "+Inf" if math.isinf(b) else str(b)
                    lines.append(f'{self.name}_bucket{{le="{le}"}} 0')
                lines.append(f"{self.name}_sum 0.0")
                lines.append(f"{self.name}_count 0")
            else:
                for key in sorted(self._totals.keys()):
                    lbl_dict = dict(key)
                    b_dict = self._counts[key]
                    for b in self.buckets:
                        le = "+Inf" if math.isinf(b) else str(b)
                        lbl_with_le = dict(lbl_dict)
                        lbl_with_le["le"] = le
                        lines.append(
                            f"{self.name}_bucket{_format_labels(lbl_with_le)} {b_dict[b]}"
                        )
                    lines.append(f"{self.name}_sum{_format_labels(lbl_dict)} {self._sums[key]:.6f}")
                    lines.append(f"{self.name}_count{_format_labels(lbl_dict)} {self._totals[key]}")
        return lines


class MetricsRegistry:
    """Central registry managing all Prometheus instruments for the microservice."""

    _instance: Optional["MetricsRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        # HTTP Traffic Metrics
        self.http_requests_total = PrometheusCounter(
            name="lab_report_http_requests_total",
            help_text="Total number of HTTP requests processed by endpoint and status.",
            label_names=["method", "endpoint", "status"],
        )
        self.http_request_duration_seconds = PrometheusHistogram(
            name="lab_report_http_request_duration_seconds",
            help_text="HTTP request latency histogram in seconds.",
            buckets=DEFAULT_LATENCY_BUCKETS,
            label_names=["method", "endpoint"],
        )
        self.http_requests_in_progress = PrometheusGauge(
            name="lab_report_http_requests_in_progress",
            help_text="Current number of in-flight HTTP requests.",
            label_names=["method", "endpoint"],
        )

        # Asynchronous Job & Worker Metrics
        self.jobs_total = PrometheusCounter(
            name="lab_report_jobs_total",
            help_text="Total number of report analysis jobs processed by status.",
            label_names=["status"],
        )
        self.active_jobs_gauge = PrometheusGauge(
            name="lab_report_active_jobs_gauge",
            help_text="Current number of jobs pending or executing.",
        )
        self.extracted_tests_count = PrometheusHistogram(
            name="lab_report_extracted_tests_count",
            help_text="Distribution of analyte tests extracted per lab report document.",
            buckets=DEFAULT_COUNT_BUCKETS,
        )

        # Clinical Safety & Guardrail Metrics
        self.guardrail_blocks_total = PrometheusCounter(
            name="lab_report_guardrail_blocks_total",
            help_text="Total queries or uploads intercepted by clinical safety guardrails.",
            label_names=["reason"],
        )
        self.panic_values_detected_total = PrometheusCounter(
            name="lab_report_panic_values_detected_total",
            help_text="Total critical medical panic values flagged.",
            label_names=["biomarker"],
        )

    @classmethod
    def get_instance(cls) -> "MetricsRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def render_all(self) -> str:
        """Render all registered metrics to standard Prometheus text exposition format."""
        all_lines: List[str] = []
        metrics = [
            self.http_requests_total,
            self.http_request_duration_seconds,
            self.http_requests_in_progress,
            self.jobs_total,
            self.active_jobs_gauge,
            self.extracted_tests_count,
            self.guardrail_blocks_total,
            self.panic_values_detected_total,
        ]
        for m in metrics:
            all_lines.extend(m.render())
        return "\n".join(all_lines) + "\n"


class PrometheusMiddleware(BaseHTTPMiddleware):
    """ASGI middleware measuring request latency and tracking traffic metrics."""

    def __init__(self, app: Any, registry: Optional[MetricsRegistry] = None):
        super().__init__(app)
        self.registry = registry or MetricsRegistry.get_instance()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Normalize endpoint path to avoid unbounded label cardinality (e.g. replace job_ids)
        raw_path = request.url.path
        endpoint = self._normalize_endpoint(raw_path)
        method = request.method

        # Skip recording for the /metrics probe itself to avoid self-amplification
        if endpoint == "/metrics":
            return await call_next(request)

        self.registry.http_requests_in_progress.inc(method=method, endpoint=endpoint)
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start_time
            self.registry.http_requests_in_progress.dec(method=method, endpoint=endpoint)
            self.registry.http_request_duration_seconds.observe(
                duration, method=method, endpoint=endpoint
            )
            self.registry.http_requests_total.inc(
                method=method, endpoint=endpoint, status=str(status_code)
            )

    @staticmethod
    def _normalize_endpoint(path: str) -> str:
        """Normalize URL path parameters (e.g. UUIDs/job_ids) into static endpoint templates."""
        parts = path.strip("/").split("/")
        normalized = []
        for i, part in enumerate(parts):
            # Check if this part is an ID following 'reports'
            if i > 0 and parts[i - 1] == "reports" and (len(part) >= 8 or "-" in part):
                normalized.append("{job_id}")
            else:
                normalized.append(part)
        return "/" + "/".join(normalized) if normalized else "/"
