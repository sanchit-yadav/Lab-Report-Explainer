"""Observability and distributed tracing with Langfuse, OpenTelemetry, and local telemetry fallback.

Provides:
- PII-safe distributed tracing across all pipeline stages (automatic PHI/PII redaction).
- OpenTelemetry OTLP-compliant span serialization.
- Modular stage tracing decorator `@trace_stage`.
- In-memory thread-safe trace ring buffer for production diagnostics.
"""

from __future__ import annotations

from collections import deque
import functools
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, List, Optional
import uuid

from src.config import get_config
from src.stages.logger import sanitize_value

logger = logging.getLogger("tracing")

# Token pricing per million tokens (USD)
MODEL_PRICING = {
    "gemini-3.1-flash-lite": {"input_per_m": 0.25, "output_per_m": 1.50},
    "gemini-3.5-flash": {"input_per_m": 1.50, "output_per_m": 9.00},
    "gemini-embedding-2": {"input_per_m": 0.05, "output_per_m": 0.00},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute estimated API cost in USD based on token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["gemini-3.1-flash-lite"])
    in_cost = (input_tokens / 1_000_000.0) * pricing["input_per_m"]
    out_cost = (output_tokens / 1_000_000.0) * pricing["output_per_m"]
    return in_cost + out_cost


class LocalSpan:
    """Local in-memory span tracking execution metadata, latency, and PII-scrubbed telemetry."""

    def __init__(self, name: str, parent_trace: Optional[LocalTrace] = None):
        self.span_id = uuid.uuid4().hex[:16]
        self.name = name
        self.parent_trace = parent_trace
        self.start_time = 0.0
        self.start_time_nano = 0
        self.end_time_nano = 0
        self.elapsed_ms = 0.0
        self.inputs: Dict[str, Any] = {}
        self.outputs: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def set_input(self, **kwargs):
        """Record sanitized input parameters, stripping any PII."""
        self.inputs.update(sanitize_value(kwargs))

    def set_output(self, **kwargs):
        """Record sanitized output attributes, stripping any PII."""
        self.outputs.update(sanitize_value(kwargs))

    def set_metadata(self, **kwargs):
        """Record sanitized execution metadata."""
        self.metadata.update(sanitize_value(kwargs))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize span to dictionary representation."""
        return {
            "span_id": self.span_id,
            "name": self.name,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "inputs": self.inputs,
            "outputs": self.outputs,
            "metadata": self.metadata,
            "error": self.error,
        }

    def to_otel_span(self, trace_id: str) -> Dict[str, Any]:
        """Convert to OpenTelemetry-compliant span dictionary."""
        attributes = {
            f"input.{k}": str(v) for k, v in self.inputs.items()
        }
        attributes.update({f"output.{k}": str(v) for k, v in self.outputs.items()})
        attributes.update({f"meta.{k}": str(v) for k, v in self.metadata.items()})

        return {
            "trace_id": trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "start_time_unix_nano": self.start_time_nano,
            "end_time_unix_nano": self.end_time_nano,
            "attributes": attributes,
            "status": {
                "code": "STATUS_CODE_ERROR" if self.error else "STATUS_CODE_OK",
                "description": self.error or "",
            },
        }


class LocalTrace:
    """Local in-memory trace collecting spans, total latency, and cost."""

    def __init__(self, name: str, metadata: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None):
        self.trace_id = (request_id or uuid.uuid4().hex)[:32]
        self.name = name
        self.metadata = sanitize_value(metadata or {})
        self.spans: List[LocalSpan] = []
        self.start_time = 0.0
        self.elapsed_ms = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0

    def add_span(self, span: LocalSpan):
        self.spans.append(span)

    def add_tokens(self, model: str, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += calculate_cost(model, input_tokens, output_tokens)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete trace with child spans."""
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "metadata": self.metadata,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "spans": [s.to_dict() for s in self.spans],
        }

    def to_otel_dict(self) -> Dict[str, Any]:
        """Export trace and spans as an OpenTelemetry OTLP compatible trace structure."""
        return {
            "resource_spans": [
                {
                    "resource": {
                        "attributes": {
                            "service.name": "ai-blood-report-explainer",
                            "service.version": "1.0.0",
                        }
                    },
                    "scope_spans": [
                        {
                            "scope": {"name": "pipeline.tracing"},
                            "spans": [s.to_otel_span(self.trace_id) for s in self.spans],
                        }
                    ],
                }
            ]
        }


class Tracer:
    """Unified telemetry tracer supporting Langfuse Cloud and local execution."""

    def __init__(self, max_buffer_size: int = 500):
        self.config = get_config()
        self.enabled = self.config.tracing.enabled
        self.public_key = os.environ.get("LANGFUSE_PUBLIC_KEY") or self.config.langfuse_public_key
        self.secret_key = os.environ.get("LANGFUSE_SECRET_KEY") or self.config.langfuse_secret_key
        self.host = os.environ.get("LANGFUSE_HOST") or self.config.langfuse_host
        self.langfuse_client = None

        # Thread-safe trace ring buffer for observability inspection
        self._trace_buffer: deque[Dict[str, Any]] = deque(maxlen=max_buffer_size)
        self._buffer_lock = threading.Lock()

        if self.enabled and self.public_key and self.secret_key:
            try:
                from langfuse import Langfuse
                self.langfuse_client = Langfuse(
                    public_key=self.public_key,
                    secret_key=self.secret_key,
                    host=self.host,
                )
                logger.info("Langfuse Cloud tracing successfully initialized.")
            except Exception as e:
                logger.warning(f"Could not connect to Langfuse Cloud ({e}). Using local tracer.")

    @contextmanager
    def start_trace(self, name: str, request_id: Optional[str] = None, **metadata) -> Generator[LocalTrace, None, None]:
        """Start a root pipeline trace."""
        trace = LocalTrace(name, metadata, request_id=request_id)
        start = time.perf_counter()
        trace.start_time = start

        # If Langfuse is connected, start cloud trace
        lf_cm = None
        lf_obs = None
        if self.langfuse_client:
            try:
                if hasattr(self.langfuse_client, "start_as_current_observation"):
                    lf_cm = self.langfuse_client.start_as_current_observation(
                        name=name,
                        metadata=trace.metadata,
                        as_type="chain",
                    )
                    lf_obs = lf_cm.__enter__()
                elif hasattr(self.langfuse_client, "trace"):
                    lf_obs = self.langfuse_client.trace(name=name, metadata=trace.metadata)
            except Exception as e:
                logger.debug(f"Langfuse start_trace error: {e}")

        exc_info = (None, None, None)
        try:
            yield trace
        except Exception as e:
            exc_info = (type(e), e, e.__traceback__)
            raise
        finally:
            elapsed = (time.perf_counter() - start) * 1000.0
            trace.elapsed_ms = elapsed

            # Record in thread-safe trace history buffer
            with self._buffer_lock:
                self._trace_buffer.append(trace.to_dict())

            if lf_obs:
                try:
                    summary_meta = {
                        **trace.metadata,
                        "elapsed_ms": elapsed,
                        "total_cost_usd": trace.total_cost_usd,
                        "input_tokens": trace.total_input_tokens,
                        "output_tokens": trace.total_output_tokens,
                    }
                    if hasattr(lf_obs, "update"):
                        lf_obs.update(metadata=summary_meta)
                except Exception as e:
                    logger.debug(f"Langfuse trace update error: {e}")
            if lf_cm:
                try:
                    lf_cm.__exit__(*exc_info)
                except Exception:
                    pass
            if self.langfuse_client and hasattr(self.langfuse_client, "flush"):
                try:
                    self.langfuse_client.flush()
                except Exception:
                    pass

    @contextmanager
    def span(self, name: str, parent_trace: Optional[LocalTrace] = None, **metadata) -> Generator[LocalSpan, None, None]:
        """Start a modular child span within an ongoing trace."""
        span_obj = LocalSpan(name, parent_trace)
        span_obj.set_metadata(**metadata)
        start = time.perf_counter()
        span_obj.start_time = start
        span_obj.start_time_nano = int(time.time() * 1e9)

        # Map to Langfuse observation type
        as_type = "span"
        name_lower = name.lower()
        if "guard" in name_lower:
            as_type = "guardrail"
        elif "rag" in name_lower or "retriev" in name_lower:
            as_type = "retriever"
        elif "generation" in name_lower or "llm" in name_lower or "explain" in name_lower:
            as_type = "generation"

        lf_cm = None
        lf_obs = None
        if self.langfuse_client and hasattr(self.langfuse_client, "start_as_current_observation"):
            try:
                lf_cm = self.langfuse_client.start_as_current_observation(
                    name=name,
                    as_type=as_type,
                    metadata=span_obj.metadata,
                )
                lf_obs = lf_cm.__enter__()
            except Exception as e:
                logger.debug(f"Langfuse child span enter error: {e}")

        exc_info = (None, None, None)
        try:
            yield span_obj
        except Exception as e:
            span_obj.error = str(e)
            exc_info = (type(e), e, e.__traceback__)
            raise
        finally:
            elapsed = (time.perf_counter() - start) * 1000.0
            span_obj.elapsed_ms = elapsed
            span_obj.end_time_nano = int(time.time() * 1e9)
            if parent_trace:
                parent_trace.add_span(span_obj)
            if lf_obs:
                try:
                    if hasattr(lf_obs, "update"):
                        lf_obs.update(
                            input=span_obj.inputs or None,
                            output=span_obj.outputs or None,
                            metadata={**span_obj.metadata, "elapsed_ms": elapsed},
                            level="ERROR" if span_obj.error else "DEFAULT",
                            status_message=span_obj.error,
                        )
                except Exception:
                    pass
            if lf_cm:
                try:
                    lf_cm.__exit__(*exc_info)
                except Exception:
                    pass

    def get_recent_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent traces recorded in memory (PII-safe)."""
        with self._buffer_lock:
            items = list(self._trace_buffer)
            return items[-limit:]

    def export_otlp_json(self, limit: int = 50) -> str:
        """Export recent traces formatted for OpenTelemetry collectors."""
        traces = self.get_recent_traces(limit=limit)
        return json.dumps({"traces": traces}, indent=2)


_GLOBAL_TRACER: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """Singleton getter for the Tracer."""
    global _GLOBAL_TRACER
    if _GLOBAL_TRACER is None:
        _GLOBAL_TRACER = Tracer()
    return _GLOBAL_TRACER


def trace_stage(stage_name: Optional[str] = None):
    """Decorator for tracing pipeline stages with PII safety and latency tracking."""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            name = stage_name or func.__name__

            # Extract request_id from args or kwargs if available
            req_id = "unknown"
            if args:
                first_arg = args[0]
                if hasattr(first_arg, "request_id"):
                    req_id = first_arg.request_id
                elif len(args) > 1 and hasattr(args[1], "request_id"):
                    req_id = args[1].request_id
            if "request_id" in kwargs:
                req_id = kwargs["request_id"]
            elif "inp" in kwargs and hasattr(kwargs["inp"], "request_id"):
                req_id = kwargs["inp"].request_id

            with tracer.span(f"stage.{name}", request_id=req_id) as span:
                span.set_input(request_id=req_id)
                res = func(*args, **kwargs)
                # Record safe summary of output
                if hasattr(res, "is_valid"):
                    span.set_output(is_valid=res.is_valid)
                if hasattr(res, "items"):
                    span.set_output(items_count=len(res.items))
                if hasattr(res, "total_chunks"):
                    span.set_output(total_chunks=res.total_chunks)
                if hasattr(res, "is_safe"):
                    span.set_output(is_safe=res.is_safe)
                elif hasattr(res, "passed"):
                    span.set_output(passed=res.passed)
                return res
        return wrapper
    return decorator
