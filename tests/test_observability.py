"""
tests/test_observability.py
Unit tests verifying OpenTelemetry tracing, PII sanitization,
granular step metrics, and cost modeling.
"""

from app.agents.orchestrator import OrchestratorAgent
from app.agents.state import AgentState
from app.observability.cost_model import calculate_cost, get_model_pricing
from app.observability.telemetry import record_agent_step_telemetry
from app.observability.tracing import (
    clear_recorded_spans,
    get_recorded_spans,
    get_tracer,
    scrub_pii,
)


def test_pii_sanitization_scrubs_emails_and_phones():
    raw_text = "Please reach out to support-user@company.co.uk or call 415-555-2671 for help."
    cleaned = scrub_pii(raw_text)

    assert "support-user@company.co.uk" not in cleaned
    assert "415-555-2671" not in cleaned
    assert "[REDACTED_EMAIL]" in cleaned
    assert "[REDACTED_PHONE]" in cleaned


def test_tracer_span_creation_and_automatic_pii_scrubbing():
    clear_recorded_spans()
    tracer = get_tracer()

    with tracer.start_span("test_span", trace_id="trace_test_123") as span:
        span.set_attribute("user.email", "confidential@secret.org")
        span.set_attribute("query.length", 42)
        span.set_status("OK")

    spans = get_recorded_spans()
    assert len(spans) == 1
    assert spans[0].name == "test_span"
    assert spans[0].trace_id == "trace_test_123"
    assert spans[0].attributes["user.email"] == "[REDACTED_EMAIL]"
    assert spans[0].attributes["query.length"] == 42
    assert spans[0].status == "OK"


def test_record_agent_step_telemetry():
    clear_recorded_spans()
    state = AgentState(customer_query="Test query without issues")

    metric = record_agent_step_telemetry(
        state=state,
        step_name="triage",
        latency_ms=15.5,
        input_tokens=100,
        output_tokens=20,
        model_name="offline-mock",
    )

    assert metric.step_name == "triage"
    assert metric.latency_ms == 15.5
    assert metric.input_tokens == 100
    assert metric.output_tokens == 20
    assert metric.tokens_per_second > 0
    assert len(state.step_metrics) == 1
    assert state.total_tokens == 120

    spans = get_recorded_spans()
    assert len(spans) == 1
    assert spans[0].name == "AgentStep.triage"
    assert spans[0].attributes["tokens.input"] == 100
    assert spans[0].attributes["tokens.output"] == 20


def test_cost_calculation_versioned_registry():
    # Gemini 1.5 Flash: $0.075 / 1M input, $0.30 / 1M output
    pricing = get_model_pricing("gemini-1.5-flash-002")
    assert pricing is not None
    assert pricing.input_cost_per_million == 0.075
    assert pricing.output_cost_per_million == 0.30

    cost = calculate_cost("gemini-1.5-flash-002", input_tokens=1_000_000, output_tokens=1_000_000)
    assert round(cost, 4) == 0.3750

    # Offline mock is strictly $0.00
    mock_cost = calculate_cost("offline-mock", input_tokens=10_000, output_tokens=5_000)
    assert mock_cost == 0.0


def test_full_orchestrator_execution_generates_traces_and_step_metrics():
    clear_recorded_spans()
    orchestrator = OrchestratorAgent()
    query = "How do I set up Personal Hotspot on my iPhone to share data with Mac?"

    state = orchestrator.process_ticket(customer_query=query)

    assert state.should_escalate is False
    assert len(state.step_metrics) >= 4  # triage, retrieval, draft, policy_guard, critic
    assert any(m.step_name == "triage" for m in state.step_metrics)
    assert any(m.step_name == "retrieval" for m in state.step_metrics)
    assert any("draft" in m.step_name for m in state.step_metrics)
    assert any("policy_guard" in m.step_name for m in state.step_metrics)
    assert any("critic" in m.step_name for m in state.step_metrics)

    spans = get_recorded_spans()
    span_names = [s.name for s in spans]
    assert "Orchestrator.process" in span_names
    assert "AgentStep.triage" in span_names
    assert "AgentStep.retrieval" in span_names

    # Assert no customer email or phone leaked to span attributes
    for s in spans:
        for val in s.attributes.values():
            if isinstance(val, str):
                assert "@" not in val or "[REDACTED_EMAIL]" in val
