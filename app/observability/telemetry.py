"""
app/observability/telemetry.py
Centralized telemetry instrumentation and step metric recording.
Integrates ADK agent execution lifecycle with OpenTelemetry tracing and versioned cost models.
"""

from typing import Any

from app.agents.state import AgentState, StepMetric
from app.observability.cost_model import calculate_cost
from app.observability.tracing import get_tracer, scrub_pii


def estimate_tokens(text: str | None) -> int:
    """
    Lightweight, deterministic token estimator (~1.33 tokens per word or 4 chars/token)
    used for local offline benchmarks when provider usage metadata is not returned.
    """
    if not text:
        return 0
    words = text.strip().split()
    return max(1, int(len(words) * 1.33))


def record_agent_step_telemetry(
    state: AgentState,
    step_name: str,
    latency_ms: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model_name: str = "offline-mock",
    extra_span_attributes: dict[str, Any] | None = None,
) -> StepMetric:
    """
    Records an auditable StepMetric on AgentState and emits a structured OpenTelemetry trace span.
    Enforces strict PII redaction on all span attributes.
    """
    # 1. Compute Cost & Throughput
    cost_usd = calculate_cost(model_name, input_tokens, output_tokens)
    tokens_per_sec = (
        round(output_tokens / (latency_ms / 1000.0), 2)
        if latency_ms > 0 and output_tokens > 0
        else 0.0
    )

    metric = StepMetric(
        step_name=step_name,
        model_name=model_name,
        latency_ms=round(latency_ms, 2),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tokens_per_second=tokens_per_sec,
        estimated_cost_usd=cost_usd,
    )
    state.step_metrics.append(metric)
    state.total_cost_usd = round(state.total_cost_usd + cost_usd, 8)
    state.total_tokens += input_tokens + output_tokens
    state.step_timings_ms[step_name] = round(latency_ms, 2)
    state.tokens_used[f"{step_name}_input"] = input_tokens
    state.tokens_used[f"{step_name}_output"] = output_tokens

    # 2. Emit OpenTelemetry Span with scrubbed attributes
    tracer = get_tracer()
    span_attributes = {
        "step.name": step_name,
        "model.name": model_name,
        "latency.ms": metric.latency_ms,
        "tokens.input": input_tokens,
        "tokens.output": output_tokens,
        "tokens.per_second": tokens_per_sec,
        "cost.usd": cost_usd,
        "ticket.id": state.ticket_id,
        "intent": state.intent,
        "should_escalate": state.should_escalate,
        "query.char_length": len(state.customer_query),
    }

    if extra_span_attributes:
        for k, v in extra_span_attributes.items():
            if isinstance(v, str):
                v = scrub_pii(v)
            span_attributes[k] = v

    with tracer.start_span(
        f"AgentStep.{step_name}",
        trace_id=state.trace_id,
        attributes=span_attributes,
    ) as span:
        span.set_attribute("status", "SUCCESS" if not state.should_escalate else "ESCALATED")

    return metric
