"""
app/agents/draft_agent.py
Drafting sub-agent: Generates customer responses strictly constrained to retrieved precedents.
Cites resolution IDs and incorporates targeted feedback during revision loops.
"""

import re
import sys
import time
from pathlib import Path

# Ensure project root and app/v1 are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.llm_client import LLMClient  # noqa: E402

from app.agents.base import BaseAgent  # noqa: E402
from app.agents.state import AgentState  # noqa: E402
from app.observability.telemetry import estimate_tokens, record_agent_step_telemetry  # noqa: E402


class DraftAgent(BaseAgent):
    """
    Sub-agent that synthesizes grounded customer replies with explicit citations.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        super().__init__(
            name="DraftAgent",
            description="Drafts concise, grounded support replies using retrieved resolution precedents.",
        )
        self.llm = llm_client or LLMClient()

    def process(self, state: AgentState) -> AgentState:
        if state.should_escalate:
            return state

        t0 = time.perf_counter()

        # Build context from retrieved cases
        citations_available = []
        context_lines = []
        for c in state.retrieved_cases:
            citations_available.append(c.id)
            context_lines.append(f"- [Resolution #{c.id}]: {c.resolution_text}")
        context_str = "\n".join(context_lines)

        revision_guidance = ""
        if state.critic_feedback:
            revision_guidance = (
                f"\nCRITICAL REVISION INSTRUCTION:\n"
                f"Your previous attempt was rejected with feedback: '{state.critic_feedback}'.\n"
                f"Ensure you address this issue directly and do not repeat unauthorized claims or links.\n"
            )

        system_prompt = (
            "You are an expert customer support agent for Apple Support on Twitter.\n"
            "Draft a helpful, concise, empathetic reply.\n"
            "MANDATORY CONSTRAINTS:\n"
            "1. Ground your answer ONLY in the historical resolutions provided.\n"
            "2. Cite the resolution ID you referenced in brackets, e.g. [Resolution #<id>].\n"
            "3. DO NOT invent fake URLs or promise free hardware replacements.\n"
            "4. Keep response under 280 characters if possible."
        )

        user_prompt = (
            f"Customer Tweet: {state.customer_query}\n\n"
            f"Verified Historical Precedents:\n{context_str}\n"
            f"{revision_guidance}\n"
            f"Drafted Response:"
        )

        reply = self.llm.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=150,
        ).strip()

        # Offline fallback synthesis if mock LLM
        if not reply or self.llm.offline:
            if state.retrieved_cases:
                best_case = state.retrieved_cases[0]
                reply = f"{best_case.resolution_text} [Resolution #{best_case.id}]"
            else:
                reply = "We want to help. Please DM us with more details so we can investigate."

        # Extract cited IDs
        cited_ids = re.findall(r"\[Resolution #([a-zA-Z0-9_\-]+)\]", reply)
        if not cited_ids and citations_available:
            cited_ids = [citations_available[0]]
            reply += f" [Resolution #{cited_ids[0]}]"

        state.drafted_reply = reply
        state.cited_resolution_ids = cited_ids
        state.draft_history.append(reply)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        in_tok = estimate_tokens(user_prompt)
        out_tok = estimate_tokens(reply)
        model_name = "offline-mock" if self.llm.offline else "gemini-1.5-flash-002"
        record_agent_step_telemetry(
            state=state,
            step_name=f"draft_revision_{state.revision_count}",
            latency_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model_name=model_name,
            extra_span_attributes={
                "revision_count": state.revision_count,
                "cited_ids_count": len(cited_ids),
            },
        )
        return state
