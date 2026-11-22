"""
app/agents/critic_agent.py
Critic sub-agent: Grades drafted replies against the multi-dimensional QA rubric.
Emits targeted feedback to guide bounded self-reflection loops.
"""

import sys
import time
from pathlib import Path

# Ensure project root and app/v1 are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from evaluation.judge import SupportJudge  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402

from app.agents.base import BaseAgent  # noqa: E402
from app.agents.state import AgentState, CriticReview  # noqa: E402
from app.tools.critic_tools import judge_score_tool  # noqa: E402


class CriticAgent(BaseAgent):
    """
    Sub-agent responsible for quality assurance grading and revision recommendations.
    """

    def __init__(self, judge: SupportJudge | None = None):
        super().__init__(
            name="CriticAgent",
            description="Evaluates draft quality across groundedness, actionability, tone, and safety.",
        )
        self.judge = judge or SupportJudge(llm_client=LLMClient(offline=True))
        self.register_tool(judge_score_tool)

    def process(self, state: AgentState) -> AgentState:
        if state.should_escalate:
            return state

        t0 = time.perf_counter()

        grounding_dicts = [
            {"resolution_text": c.resolution_text, "id": c.id}
            for c in state.retrieved_cases
        ]

        critic_res = judge_score_tool(
            customer_query=state.customer_query,
            drafted_reply=state.drafted_reply,
            grounding_cases=grounding_dicts,
            judge=self.judge,
        )

        review = CriticReview(
            passed=critic_res["passed"],
            groundedness=critic_res["groundedness"],
            actionability=critic_res["actionability"],
            brand_tone=critic_res["brand_tone"],
            safety_pass=critic_res["safety_pass"],
            critique=critic_res["critique"],
            actionable_feedback=critic_res.get("actionable_feedback"),
        )

        state.critic_verdict = review
        state.critic_feedback = review.actionable_feedback if not review.passed else None

        state.step_timings_ms[f"critic_step_{state.revision_count}"] = round(
            (time.perf_counter() - t0) * 1000.0, 2
        )
        return state
