"""
app/agents/orchestrator.py
Root Orchestrator Agent compliant with Google Agent Development Kit (ADK) architecture.
Manages hierarchical delegation across Triage, Retrieval, Draft, PolicyGuard, and Critic.
Enforces a bounded self-reflection loop (max 2 retries) with strict deterministic guardrails.
"""

import time
import uuid

from app.agents.base import BaseAgent
from app.agents.critic_agent import CriticAgent
from app.agents.draft_agent import DraftAgent
from app.agents.policy_guard import PolicyGuard
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.state import AgentState
from app.agents.triage_agent import TriageAgent


class OrchestratorAgent(BaseAgent):
    """
    Root agent governing multi-agent support ticket resolution and state lifecycle.
    """

    def __init__(
        self,
        triage_agent: TriageAgent | None = None,
        retrieval_agent: RetrievalAgent | None = None,
        draft_agent: DraftAgent | None = None,
        policy_guard: PolicyGuard | None = None,
        critic_agent: CriticAgent | None = None,
        max_revisions: int = 2,
        similarity_threshold: float = 0.50,
    ):
        super().__init__(
            name="OrchestratorAgent",
            description="Root orchestrator delegating triage, grounding, synthesis, safety, and critique.",
        )
        self.triage_agent = triage_agent or TriageAgent()
        self.retrieval_agent = retrieval_agent or RetrievalAgent()
        self.draft_agent = draft_agent or DraftAgent()
        self.policy_guard = policy_guard or PolicyGuard()
        self.critic_agent = critic_agent or CriticAgent()
        self.max_revisions = max_revisions
        self.similarity_threshold = similarity_threshold

    def process(self, state: AgentState) -> AgentState:
        """
        Executes hierarchical multi-agent control flow:
        1. Triage -> (Escalate? Return early)
        2. Retrieval -> (Populate grounding cases) -> (Low similarity? Escalate to avoid hallucination)
        3. Draft -> PolicyGuard -> Critic (Bounded self-reflection loop, max 2 revisions)
        """
        t_total_start = time.perf_counter()

        # Step 1: Initial Triage & Risk Evaluation
        state = self.triage_agent.process(state)
        if state.should_escalate:
            state.step_timings_ms["total_orchestrator"] = round(
                (time.perf_counter() - t_total_start) * 1000.0, 2
            )
            return state

        # Step 2: Dense Vector Grounding Retrieval
        state = self.retrieval_agent.process(state)

        # Grounding Quality Gate (Hallucination Prevention)
        if not state.retrieved_cases or state.max_retrieval_similarity < self.similarity_threshold:
            state.should_escalate = True
            state.escalation_reason = (
                f"Historical resolution retrieval similarity ({state.max_retrieval_similarity:.2f}) "
                f"is below threshold ({self.similarity_threshold:.2f}). No verified historical precedent "
                f"exists; escalating to avoid hallucination."
            )
            state.reason_code = "GROUNDING_NO_HISTORICAL_PRECEDENT"
            state.escalation_tier = "TIER_2_QUALITY_GATE"
            state.step_timings_ms["total_orchestrator"] = round(
                (time.perf_counter() - t_total_start) * 1000.0, 2
            )
            return state

        # Step 3: Bounded Self-Reflection Loop
        state.max_revisions = self.max_revisions
        state.revision_count = 0

        while state.revision_count <= self.max_revisions:
            # 3a. Grounded Drafting
            state = self.draft_agent.process(state)

            # 3b. Deterministic Policy Guardrail Verification
            state = self.policy_guard.process(state)

            # If deterministic guardrail failed (e.g. ungrounded link or forbidden claim)
            if not state.policy_verdict.passed:
                state.revision_count += 1
                state.critic_feedback = (
                    f"PolicyGuard violation: {state.policy_verdict.details}. "
                    f"Remove unauthorized links and cite verified resolutions."
                )

                if state.revision_count > self.max_revisions:
                    # Bounded loop exhausted: hard escalation
                    state.should_escalate = True
                    state.escalation_reason = (
                        "Deterministic policy violation persisted after maximum revision retries."
                    )
                    state.escalation_tier = "TIER_1_HARD_GUARDRAIL"
                    state.reason_code = "POLICY_GUARD_REVISION_EXHAUSTED"
                    break
                continue

            # 3c. Critic Agent Evaluation Rubric
            state = self.critic_agent.process(state)

            if state.critic_verdict.passed:
                # Draft approved by Critic
                break

            # Critic requested revisions
            state.revision_count += 1
            if state.revision_count > self.max_revisions:
                # Quality threshold not met after max revisions
                state.should_escalate = True
                state.escalation_reason = (
                    "Draft failed QA rubric standards after maximum revision retries."
                )
                state.escalation_tier = "TIER_2_QUALITY_GATE"
                state.reason_code = "CRITIC_QUALITY_REVISION_EXHAUSTED"
                break

        state.step_timings_ms["total_orchestrator"] = round(
            (time.perf_counter() - t_total_start) * 1000.0, 2
        )
        return state

    def process_ticket(
        self,
        customer_query: str,
        ticket_id: str | None = None,
        trace_id: str | None = None,
    ) -> AgentState:
        """High-level entrypoint for external callers (FastAPI / CLI)."""
        tid = ticket_id or f"ticket_{uuid.uuid4().hex[:8]}"
        trid = trace_id or f"trace_{uuid.uuid4().hex[:12]}"

        state = AgentState(
            ticket_id=tid,
            customer_query=customer_query,
            trace_id=trid,
        )
        return self.process(state)
