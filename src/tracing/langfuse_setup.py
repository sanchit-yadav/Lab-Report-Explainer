"""Observability and distributed tracing with Langfuse and local telemetry fallback."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from src.config import get_config

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
    """Local in-memory span tracking execution metadata and latency."""

    def __init__(self, name: str, parent_trace: Optional[LocalTrace] = None):
        self.name = name
        self.parent_trace = parent_trace
        self.start_time = 0.0
        self.elapsed_ms = 0.0
        self.inputs: Dict[str, Any] = {}
        self.outputs: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def set_input(self, **kwargs):
        self.inputs.update(kwargs)

    def set_output(self, **kwargs):
        self.outputs.update(kwargs)

    def set_metadata(self, **kwargs):
        self.metadata.update(kwargs)


class LocalTrace:
    """Local in-memory trace collecting spans, total latency, and cost."""

    def __init__(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        self.name = name
        self.metadata = metadata or {}
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


class Tracer:
    """Unified telemetry tracer supporting Langfuse Cloud and local execution."""

    def __init__(self):
        self.config = get_config()
        self.enabled = self.config.tracing.enabled
        self.public_key = os.environ.get("LANGFUSE_PUBLIC_KEY") or self.config.langfuse_public_key
        self.secret_key = os.environ.get("LANGFUSE_SECRET_KEY") or self.config.langfuse_secret_key
        self.host = os.environ.get("LANGFUSE_HOST") or self.config.langfuse_host
        self.langfuse_client = None

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
    def start_trace(self, name: str, **metadata) -> Generator[LocalTrace, None, None]:
        """Start a root pipeline trace."""
        trace = LocalTrace(name, metadata)
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
                        metadata=metadata,
                        as_type="chain",
                    )
                    lf_obs = lf_cm.__enter__()
                elif hasattr(self.langfuse_client, "trace"):
                    lf_obs = self.langfuse_client.trace(name=name, metadata=metadata)
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

        # Map to Langfuse observation type
        as_type = "span"
        name_lower = name.lower()
        if "guard" in name_lower:
            as_type = "guardrail"
        elif "rag" in name_lower or "retriev" in name_lower:
            as_type = "retriever"
        elif "generation" in name_lower or "llm" in name_lower:
            as_type = "generation"

        lf_cm = None
        lf_obs = None
        if self.langfuse_client and hasattr(self.langfuse_client, "start_as_current_observation"):
            try:
                lf_cm = self.langfuse_client.start_as_current_observation(
                    name=name,
                    as_type=as_type,
                    metadata=metadata,
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


_GLOBAL_TRACER: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """Singleton getter for the Tracer."""
    global _GLOBAL_TRACER
    if _GLOBAL_TRACER is None:
        _GLOBAL_TRACER = Tracer()
    return _GLOBAL_TRACER
