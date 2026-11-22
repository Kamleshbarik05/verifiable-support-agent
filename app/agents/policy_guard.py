"""
app/agents/policy_guard.py
Deterministic firewall sub-agent: Validates public PII exposure and enforces URL allowlisting.
Maintains absolute veto authority over LLM outputs.
"""

import time

from app.agents.base import BaseAgent
from app.agents.state import AgentState, PolicyVerdict
from app.tools.guardrail_tools import pii_check_tool, url_allowlist_check_tool


class PolicyGuard(BaseAgent):
    """
    Sub-agent executing deterministic compliance, privacy, and hallucinated URL verification.
    """

    def __init__(self):
        super().__init__(
            name="PolicyGuard",
            description="Enforces zero-PII exposure and validates URL allowlists and grounding citations.",
        )
        self.register_tool(pii_check_tool)
        self.register_tool(url_allowlist_check_tool)

    def process(self, state: AgentState) -> AgentState:
        if state.should_escalate:
            return state

        t0 = time.perf_counter()

        # 1. Deterministic PII Check on Customer Query
        pii_res = pii_check_tool(state.customer_query)
        if not pii_res["passed"]:
            state.should_escalate = True
            state.escalation_reason = f"Deterministic Guardrail Triggered: {pii_res['details']}"
            state.escalation_tier = "TIER_1_HARD_GUARDRAIL"
            state.reason_code = "HARD_GUARDRAIL_PII_EXPOSURE"
            state.policy_verdict = PolicyVerdict(
                passed=False,
                reason_code=pii_res["violation_type"],
                details=pii_res["details"],
                violation_tier="TIER_1_HARD_GUARDRAIL",
            )
            state.step_timings_ms[f"policy_guard_{state.revision_count}"] = round(
                (time.perf_counter() - t0) * 1000.0, 2
            )
            return state

        # 2. Deterministic URL Verification on Drafted Reply
        grounding_dicts = [
            {"resolution_text": c.resolution_text, "id": c.id}
            for c in state.retrieved_cases
        ]
        url_res = url_allowlist_check_tool(
            drafted_text=state.drafted_reply,
            grounding_resolutions=grounding_dicts,
        )

        if not url_res["passed"]:
            state.policy_verdict = PolicyVerdict(
                passed=False,
                reason_code=url_res["violation_type"],
                details=url_res["details"],
                violation_tier="TIER_2_POLICY_RISK",
            )
        else:
            state.policy_verdict = PolicyVerdict(
                passed=True,
                reason_code="PASS",
                details="Passed all deterministic safety and URL allowlist checks.",
            )

        state.step_timings_ms[f"policy_guard_{state.revision_count}"] = round(
            (time.perf_counter() - t0) * 1000.0, 2
        )
        return state
