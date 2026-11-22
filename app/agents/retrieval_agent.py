"""
app/agents/retrieval_agent.py
Retrieval sub-agent: Queries pgvector store for top-k historical grounded resolutions.
"""

import time

from app.agents.base import BaseAgent
from app.agents.state import AgentState, GroundedCase
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

        state.step_timings_ms["retrieval"] = round((time.perf_counter() - t0) * 1000.0, 2)
        return state
