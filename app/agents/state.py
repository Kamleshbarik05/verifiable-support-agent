"""
app/agents/state.py
Strongly typed Pydantic state contracts for Google ADK multi-agent pipeline.
Ensures strict validation across all agent boundaries.
"""

from pydantic import BaseModel, Field


class GroundedCase(BaseModel):
    id: str
    brand_text: str = "@AppleSupport"
    issue_text: str
    resolution_text: str
    intent: str
    similarity_score: float = 0.0


class PolicyVerdict(BaseModel):
    passed: bool = True
    reason_code: str = "PASS"
    details: str = "Passed all deterministic safety and URL allowlist checks."
    violation_tier: str | None = None


class CriticReview(BaseModel):
    passed: bool = True
    groundedness: int = Field(default=4, ge=1, le=5)
    actionability: int = Field(default=4, ge=1, le=5)
    brand_tone: int = Field(default=4, ge=1, le=5)
    safety_pass: bool = True
    critique: str = "Draft verified against Apple Support QA standards."
    actionable_feedback: str | None = None


class AgentState(BaseModel):
    """
    Unified state payload passed through the hierarchical multi-agent orchestrator.
    """
    ticket_id: str = "ticket_default"
    customer_query: str
    trace_id: str = "trace_default"

    # Triage Agent outputs
    intent: str = "OUT_OF_SCOPE_COMPLAINT"
    intent_confidence: float = 0.0
    intent_reasoning: str = ""
    should_escalate: bool = False
    escalation_reason: str = ""
    escalation_tier: str = "AUTO_HANDLED"
    reason_code: str = "AUTO_HANDLED_HIGH_CONFIDENCE"

    # Retrieval Agent outputs
    retrieved_cases: list[GroundedCase] = Field(default_factory=list)
    max_retrieval_similarity: float = 0.0

    # Draft Agent outputs
    drafted_reply: str = ""
    cited_resolution_ids: list[str] = Field(default_factory=list)
    draft_history: list[str] = Field(default_factory=list)

    # Policy Guard outputs
    policy_verdict: PolicyVerdict = Field(default_factory=PolicyVerdict)

    # Critic Agent outputs
    critic_verdict: CriticReview = Field(default_factory=CriticReview)
    critic_feedback: str | None = None
    revision_count: int = 0
    max_revisions: int = 2

    # Step Metrics for Observability
    step_timings_ms: dict[str, float] = Field(default_factory=dict)
    tokens_used: dict[str, int] = Field(default_factory=dict)
