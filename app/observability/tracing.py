"""
app/observability/tracing.py
OpenTelemetry distributed tracing, span management, and PII sanitization.
Supports local console export, zero-dependency in-memory recording, and Google Cloud Trace.
Enforces 100% uniform sampling (ALWAYS_ON) and strict data governance (PII scrubbing).
"""

import os
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

# ==========================================
# 1. PII SANITIZATION UTILITIES
# ==========================================
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")


def scrub_pii(text: str | None) -> str:
    """
    Sanitizes personal identifiers (emails and phone numbers) from strings
    before they are ever considered for logs or trace attributes.
    """
    if not text:
        return ""
    scrubbed = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    scrubbed = PHONE_PATTERN.sub("[REDACTED_PHONE]", scrubbed)
    return scrubbed


# ==========================================
# 2. IN-MEMORY / FALLBACK SPAN IMPLEMENTATION
# ==========================================
@dataclass
class RecordedSpan:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_time: float
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "UNSET"
    exceptions: list[Exception] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0.0
        return round((self.end_time - self.start_time) * 1000.0, 2)


class InMemorySpanContext:
    def __init__(self, span: RecordedSpan):
        self.span = span

    def set_attribute(self, key: str, value: Any) -> None:
        # Guarantee PII is never stored in attributes
        if isinstance(value, str):
            value = scrub_pii(value)
        self.span.attributes[key] = value

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        for k, v in attributes.items():
            self.set_attribute(k, v)

    def set_status(self, status: str) -> None:
        self.span.status = status

    def record_exception(self, exception: Exception) -> None:
        self.span.exceptions.append(exception)
        self.span.status = "ERROR"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.span.end_time = time.perf_counter()
        if exc_val is not None:
            self.record_exception(exc_val)
        return False


# In-memory global trace collector for audit assertions and test verifications
_RECORDED_SPANS: list[RecordedSpan] = []


def get_recorded_spans() -> list[RecordedSpan]:
    """Returns all in-memory recorded spans (useful in unit tests and local evals)."""
    return list(_RECORDED_SPANS)


def clear_recorded_spans() -> None:
    """Clears in-memory recorded spans."""
    _RECORDED_SPANS.clear()


# ==========================================
# 3. OPENTELEMETRY TRACER MANAGER
# ==========================================
class SupportTracer:
    """
    Manages OpenTelemetry distributed tracing with multi-mode export:
    - 'console': Formatted local stdout span printing
    - 'gcp': Google Cloud Trace exporter (CloudRun/GCP)
    - 'none' (default): In-memory recording with zero network/cloud dependencies
    """

    def __init__(self):
        self.exporter_mode = os.environ.get("OTEL_EXPORTER", "none").strip().lower()
        self.sampler_type = "ALWAYS_ON"  # 100% uniform audit sampling
        self.otel_tracer = None
        self._init_otel_tracer()

    def _init_otel_tracer(self) -> None:
        """Attempts to initialize real OpenTelemetry TracerProvider if dependencies exist."""
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
            from opentelemetry.sdk.trace.sampling import ALWAYS_ON

            provider = TracerProvider(sampler=ALWAYS_ON)

            if self.exporter_mode == "console":
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            elif self.exporter_mode == "gcp":
                try:
                    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

                    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
                except ImportError:
                    # Fallback cleanly if GCP exporter package is absent in dev
                    pass

            trace.set_tracer_provider(provider)
            self.otel_tracer = trace.get_tracer("verifiable-support-agent", "2.0.0")
        except ImportError:
            # OpenTelemetry SDK not installed; graceful in-memory fallback
            self.otel_tracer = None

    @contextmanager
    def start_span(
        self,
        name: str,
        trace_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ):
        """
        Context manager creating a structured trace span.
        Always records locally to _RECORDED_SPANS while forwarding to OTEL if active.
        """
        tid = trace_id or f"trace_{int(time.time() * 1000):x}"
        sid = f"span_{int(time.perf_counter() * 1000000):x}"

        rec = RecordedSpan(
            name=name,
            trace_id=tid,
            span_id=sid,
            parent_span_id=None,
            start_time=time.perf_counter(),
            attributes={},
        )
        _RECORDED_SPANS.append(rec)
        ctx = InMemorySpanContext(rec)

        if attributes:
            ctx.set_attributes(attributes)

        # If OTEL SDK is active, wrap within real otel span
        if self.otel_tracer is not None:
            with self.otel_tracer.start_as_current_span(name) as otel_span:
                if attributes:
                    for k, v in attributes.items():
                        if isinstance(v, str):
                            v = scrub_pii(v)
                        otel_span.set_attribute(k, v)
                with ctx:
                    yield ctx
        else:
            with ctx:
                yield ctx


# Global singleton instance
_tracer = SupportTracer()


def get_tracer() -> SupportTracer:
    return _tracer


def trace_agent_step(agent_name: str) -> Callable:
    """
    Decorator for wrapping an agent or tool execution in an auditable OpenTelemetry span.
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_span(
                f"Agent.{agent_name}",
                attributes={"agent.name": agent_name, "component": "ADKAgent"},
            ) as span:
                res = func(*args, **kwargs)
                span.set_attribute("agent.status", "completed")
                return res

        return wrapper

    return decorator
