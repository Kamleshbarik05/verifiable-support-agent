"""
app/api/schemas.py
Pydantic schemas and request/response models for the FastAPI support triage API.
Includes input validation boundaries (size limits) to protect against DoS attacks.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.agents.state import StepMetric


class TriageRequest(BaseModel):
    """
    Inbound customer ticket inquiry.
    Bounded between 1 and 1000 characters to prevent prompt injection context-stuffing.
    """
    customer_query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Customer inquiry or tweet text to evaluate.",
        json_schema_extra={"example": "My iPhone 12 battery drains from 100% to 20% in 3 hours. Battery health is 84%."},
    )
    ticket_id: str | None = Field(
        default=None,
        description="Optional external ticket identifier.",
        json_schema_extra={"example": "ticket_apple_1001"},
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata (e.g. customer tier, channel, platform).",
    )


class TriageResponse(BaseModel):
    """
    Comprehensive operational triage response payload.
    """
    ticket_id: str
    intent: str
    intent_confidence: float
    decision: str = Field(
        ...,
        description="'draft' if safe for automated response; 'escalate' if routed to human.",
    )
    should_escalate: bool
    escalation_reason: str | None = None
    escalation_tier: str
    reason_code: str
    drafted_reply: str
    cited_resolution_ids: list[str] = Field(default_factory=list)
    critic_passed: bool
    revisions_needed: int
    trace_id: str
    step_latencies_ms: dict[str, float] = Field(default_factory=dict)
    step_metrics: list[StepMetric] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_tokens: int = 0


class HealthResponse(BaseModel):
    """Liveness probe response for Cloud Run container health monitoring."""
    status: str = "healthy"
    version: str = "2.0.0"
    uptime_seconds: float
    timestamp: str
