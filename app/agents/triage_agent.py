"""
app/agents/triage_agent.py
Triage sub-agent: Classifies intent and enforces deterministic risk gates.
Halts pipeline immediately on safety hazards, legal threats, or PII exposure.
"""

import time

from app.agents.base import BaseAgent
from app.agents.state import AgentState
from app.tools.triage_tools import classify_intent_tool, risk_gate_tool


class TriageAgent(BaseAgent):
    """
    Sub-agent responsible for initial customer ticket triage and escalation routing.
    """

    def __init__(self):
        super().__init__(
            name="TriageAgent",
            description="Evaluates customer query intent and determines risk-based human escalation.",
        )
        self.register_tool(classify_intent_tool)
        self.register_tool(risk_gate_tool)

    def process(self, state: AgentState) -> AgentState:
        t0 = time.perf_counter()

        # 1. Intent Classification
        intent_res = classify_intent_tool(state.customer_query)
        state.intent = intent_res["intent"]
        state.intent_confidence = intent_res["confidence"]
        state.intent_reasoning = intent_res.get("reasoning", "")

        # 2. Risk Gate Evaluation
        risk_res = risk_gate_tool(
            query=state.customer_query,
            predicted_intent=state.intent,
            intent_confidence=state.intent_confidence,
        )

        state.should_escalate = risk_res["should_escalate"]
        state.escalation_reason = risk_res.get("stated_reason", "")
        state.escalation_tier = risk_res.get("tier", "AUTO_HANDLED")
        state.reason_code = risk_res.get("reason_code", "AUTO_HANDLED_HIGH_CONFIDENCE")

        state.step_timings_ms["triage"] = round((time.perf_counter() - t0) * 1000.0, 2)
        return state
