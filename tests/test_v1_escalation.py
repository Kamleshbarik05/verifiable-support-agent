"""
Regression tests for v1 EscalationEngine.
"""

from src.escalation import EscalationEngine


def test_escalation_engine_initialization():
    engine = EscalationEngine()
    assert engine is not None


def test_deterministic_safety_hazard_triggers_escalation(sample_queries):
    engine = EscalationEngine()
    res = engine.decide(
        customer_query=sample_queries["battery_hazard"],
        predicted_intent="HARDWARE_BATTERY_PERFORMANCE",
        intent_confidence=0.95,
        rag_similarity_score=0.90,
    )
    assert res["should_escalate"] is True
    assert res["tier"] == "TIER_1_HARD_GUARDRAIL"
    assert res["reason_code"] == "HARD_GUARDRAIL_SAFETY_LEGAL"
    assert "smoke" in res["stated_reason"].lower()


def test_deterministic_pii_leakage_triggers_escalation(sample_queries):
    engine = EscalationEngine()
    res = engine.decide(
        customer_query=sample_queries["pii_query"],
        predicted_intent="USAGE_FEATURE_HOWTO",
        intent_confidence=0.95,
        rag_similarity_score=0.90,
    )
    assert res["should_escalate"] is True
    assert res["tier"] == "TIER_1_HARD_GUARDRAIL"
    assert res["reason_code"] == "HARD_GUARDRAIL_PII_EXPOSURE"


def test_billing_refund_intent_escalation(sample_queries):
    engine = EscalationEngine()
    res = engine.decide(
        customer_query=sample_queries["refund_issue"],
        predicted_intent="BILLING_SUBSCRIPTION_REFUND",
        intent_confidence=0.95,
        rag_similarity_score=0.85,
    )
    assert res["should_escalate"] is True
    assert res["tier"] == "TIER_2_POLICY_RISK"
    assert res["reason_code"] == "INTENT_HIGH_RISK_FINANCIAL"


def test_safe_query_passes_without_escalation(sample_queries):
    engine = EscalationEngine()
    res = engine.decide(
        customer_query=sample_queries["howto_issue"],
        predicted_intent="USAGE_FEATURE_HOWTO",
        intent_confidence=0.92,
        rag_similarity_score=0.85,
    )
    assert res["should_escalate"] is False
    assert res["reason_code"] == "AUTO_HANDLED_HIGH_CONFIDENCE"
    assert res["tier"] == "AUTO_HANDLED"
