"""
app/agents/retrieval_agent.py
Retrieval sub-agent: Queries pgvector store for top-k historical grounded resolutions.
"""

import time

from app.agents.base import BaseAgent
from app.agents.state import AgentState, GroundedCase
from app.config import VERTEX_EMBEDDING_MODEL
from app.observability.telemetry import estimate_tokens, record_agent_step_telemetry
from app.tools.retrieval_tools import search_resolutions_tool


class RetrievalAgent(BaseAgent):
    """
    Sub-agent responsible for grounding resolution retrieval using pgvector.
    """

    def __init__(self, top_k: int = 3):
        super().__init__(
            name="RetrievalAgent",
            description="Searches historical resolution vector database for grounding precedents.",
        )
        self.top_k = top_k
        self.register_tool(search_resolutions_tool)

    def process(self, state: AgentState) -> AgentState:
        if state.should_escalate:
            return state

        t0 = time.perf_counter()

        raw_cases = search_resolutions_tool(
            query=state.customer_query,
            intent=state.intent,
            top_k=self.top_k,
        )

        cases = [
            GroundedCase(
                id=c["id"],
                brand_text=c.get("brand_text", "@AppleSupport"),
                issue_text=c["issue_text"],
                resolution_text=c["resolution_text"],
                intent=c["intent"],
                similarity_score=c.get("similarity_score", 0.0),
            )
            for c in raw_cases
        ]

        state.retrieved_cases = cases
        state.max_retrieval_similarity = cases[0].similarity_score if cases else 0.0

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        in_tok = estimate_tokens(state.customer_query)
        record_agent_step_telemetry(
            state=state,
            step_name="retrieval",
            latency_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=0,
            model_name=VERTEX_EMBEDDING_MODEL,
            extra_span_attributes={
                "retrieved_count": len(cases),
                "max_similarity": state.max_retrieval_similarity,
            },
        )
        return state
