"""
tests/test_agents.py
Unit tests verifying the 4 critical production paths of the ADK multi-agent orchestrator:
1. Escalation Path (immediate short-circuit on safety hazard / PII)
2. Normal Path (1-pass clean approval by Critic)
3. One-Revision Path (Critic requests revision -> DraftAgent refines -> Critic approves)
4. Guardrail-Block Path (PolicyGuard catches ungrounded link -> bounded loop exhausted -> human escalation)
"""

from unittest.mock import MagicMock

from app.agents.critic_agent import CriticAgent
from app.agents.draft_agent import DraftAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.state import AgentState, CriticReview


def test_path_1_escalation_short_circuit():
    """
    Path 1: Physical safety hazard or public PII must halt immediately at TriageAgent.
    Downstream retrieval and drafting must never execute.
    """
    orchestrator = OrchestratorAgent()
    hazard_query = "Battery on my iPhone expanded, cracked the screen, and there is smoke!"

    state = orchestrator.process_ticket(customer_query=hazard_query)

    assert state.should_escalate is True
    assert state.escalation_tier == "TIER_1_HARD_GUARDRAIL"
    assert "smoke" in state.escalation_reason.lower()
    # Downstream components were bypassed
    assert state.drafted_reply == ""
    assert len(state.retrieved_cases) == 0
    assert "retrieval" not in state.step_timings_ms


def test_path_2_normal_approval_path():
    """
    Path 2: Standard safe inquiry completes in a single pass without revisions.
    """
    orchestrator = OrchestratorAgent()
    safe_query = "How do I set up Personal Hotspot on my iPhone to share data with Mac?"

    state = orchestrator.process_ticket(customer_query=safe_query)

    assert state.should_escalate is False
    assert state.intent == "USAGE_FEATURE_HOWTO"
    assert len(state.retrieved_cases) > 0
    assert len(state.cited_resolution_ids) > 0
    assert state.policy_verdict.passed is True
    assert state.critic_verdict.passed is True
    assert state.revision_count == 0
    assert len(state.draft_history) == 1


def test_path_3_one_revision_path():
    """
    Path 3: CriticAgent rejects initial draft; DraftAgent refines with feedback; Critic passes on retry.
    """
    mock_critic = CriticAgent()
    call_count = 0

    def mock_critic_process(state: AgentState) -> AgentState:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Rejection on pass 1
            state.critic_verdict = CriticReview(
                passed=False,
                groundedness=2,
                safety_pass=True,
                critique="Draft omitted verified support resolution ID citations.",
                actionable_feedback="Include official resolution ID brackets.",
            )
            state.critic_feedback = state.critic_verdict.actionable_feedback
        else:
            # Approval on pass 2
            state.critic_verdict = CriticReview(
                passed=True,
                groundedness=5,
                safety_pass=True,
                critique="Revisions verified; cited resolutions confirmed.",
            )
            state.critic_feedback = None
        return state

    mock_critic.process = mock_critic_process

    orchestrator = OrchestratorAgent(critic_agent=mock_critic, max_revisions=2)
    safe_query = "How do I set up Personal Hotspot on my iPhone to share data with Mac?"

    state = orchestrator.process_ticket(customer_query=safe_query)

    assert state.should_escalate is False
    assert state.revision_count == 1  # Exactly 1 revision cycle completed
    assert len(state.draft_history) == 2  # Two distinct draft attempts
    assert state.critic_verdict.passed is True
    assert call_count == 2


def test_path_4_guardrail_block_and_exhausted_retries():
    """
    Path 4: DraftAgent attempts to inject an ungrounded, unauthorized link.
    PolicyGuard detects the violation repeatedly until max_revisions is exhausted,
    triggering safe human escalation.
    """
    mock_draft = DraftAgent()
    # Mock draft to always inject an unauthorized phishing link
    mock_draft.process = MagicMock(side_effect=lambda state: setattr(
        state,
        "drafted_reply",
        "Please visit https://unauthorized-phishing-apple.com/get-free-replacement to claim your refund."
    ) or state)

    orchestrator = OrchestratorAgent(draft_agent=mock_draft, max_revisions=2)
    query = "How do I set up Personal Hotspot on my iPhone to share data with Mac?"

    state = orchestrator.process_ticket(customer_query=query)

    assert state.should_escalate is True
    assert state.revision_count > 2  # Exhausted max_revisions
    assert state.reason_code == "POLICY_GUARD_REVISION_EXHAUSTED"
    assert state.escalation_tier == "TIER_1_HARD_GUARDRAIL"
    assert "persisted after maximum revision retries" in state.escalation_reason.lower()
