"""
adk_agent/agent.py
Google Agent Development Kit (ADK) root agent for Verifiable Support Agent.
Visualized and inspected via the local `adk web` developer UI.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.agents.orchestrator import OrchestratorAgent  # noqa: E402
from app.tools.guardrail_tools import pii_check_tool, url_allowlist_check_tool  # noqa: E402
from app.tools.retrieval_tools import search_resolutions_tool  # noqa: E402
from app.tools.triage_tools import classify_intent_tool, risk_gate_tool  # noqa: E402

_orchestrator = OrchestratorAgent()


# ==============================================================================
# Clean Primitive-Typed Tool Wrappers for Google ADK Function Schema Generation
# ==============================================================================
def resolve_support_ticket(customer_query: str) -> dict:
    """Evaluates customer support query through the full multi-agent hierarchy with grounding and guardrails."""
    state = _orchestrator.process_ticket(customer_query)
    
    if state.should_escalate:
        reply = (
            f"Your request has been routed to our senior specialized support team ({state.escalation_tier}). "
            f"Reason: {state.escalation_reason}"
        )
    else:
        reply = state.drafted_reply or "Thank you for contacting Apple Support. We have verified your request."

    return {
        "reply": reply,
        "intent": state.intent,
        "should_escalate": state.should_escalate,
        "escalation_reason": state.escalation_reason,
        "escalation_tier": state.escalation_tier,
        "drafted_reply": reply,
        "cited_resolutions": state.cited_resolution_ids,
        "revisions_needed": state.revision_count,
        "latency_ms": state.step_timings_ms,
        "cost_usd": state.total_cost_usd,
    }


def classify_customer_intent(customer_query: str) -> dict:
    """Classifies the customer support tweet into 1 of 7 MECE intent categories."""
    res = classify_intent_tool(customer_query)
    return {"intent": res["intent"], "confidence": res["confidence"]}


def evaluate_safety_and_legal_risk(customer_query: str, intent: str = "USAGE_FEATURE_HOWTO") -> dict:
    """Evaluates physical safety hazards, legal lawsuits, and financial risks for immediate human escalation."""
    res = risk_gate_tool(query=customer_query, predicted_intent=intent, intent_confidence=0.90)
    return {
        "should_escalate": res["should_escalate"],
        "reason": res.get("stated_reason", "PASS"),
        "tier": res.get("tier", "AUTO_HANDLED"),
    }


def search_historical_resolutions(query: str, top_k: int = 3) -> list:
    """Retrieves top-k historical brand support resolution precedents using dense vector embeddings."""
    return search_resolutions_tool(query=query, top_k=top_k)


def verify_url_allowlist(drafted_reply: str) -> dict:
    """Verifies that all URLs in a draft comply with authorized support domains (e.g. apple.com)."""
    return url_allowlist_check_tool(drafted_text=drafted_reply)


def scan_for_pii(text: str) -> dict:
    """Detects public leakage of customer email addresses and phone numbers."""
    return pii_check_tool(text=text)


# ==============================================================================
# Google ADK Root Agent Initialization
# ==============================================================================
try:
    from google.adk.agents import Agent

    adk_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    # Google AI Studio mandates gemini-3.8-flash for new users/keys
    if any(k in adk_model for k in ["002", "1.5", "2.0", "2.5"]):
        adk_model = "gemini-3.8-flash"

    root_agent = Agent(
        name="verifiable_support_agent",
        model=adk_model,
        description="Enterprise multi-agent customer support triage and resolution platform with pgvector grounding.",
        instruction=(
            "You are the Verifiable Support Agent governor for Apple Support. "
            "For every user message, always call the `resolve_support_ticket` tool with their inquiry. "
            "Then immediately present the tool's `reply` to the user."
        ),
        tools=[
            resolve_support_ticket,
            classify_customer_intent,
            evaluate_safety_and_legal_risk,
            search_historical_resolutions,
            verify_url_allowlist,
            scan_for_pii,
        ],
    )
except ImportError:
    root_agent = None  # type: ignore
