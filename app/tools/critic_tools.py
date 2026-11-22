"""
app/tools/critic_tools.py
Production tool wrapper for LLM-as-a-judge rubric scoring and critique feedback.
"""

import sys
from pathlib import Path
from typing import Any

# Ensure project root and app/v1 are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from evaluation.judge import SupportJudge  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402

_default_judge = SupportJudge(llm_client=LLMClient(offline=True))


def judge_score_tool(
    customer_query: str,
    drafted_reply: str,
    grounding_cases: list[dict[str, Any]],
    gold_resolution: str = "",
    judge: SupportJudge | None = None,
) -> dict[str, Any]:
    """
    Evaluates drafted reply against Apple Support QA standards:
    Groundedness (1-5), Actionability (1-5), Brand Tone (1-5), Safety Pass (bool).
    """
    eval_judge = judge or _default_judge
    res = eval_judge.evaluate_reply(
        customer_query=customer_query,
        drafted_reply=drafted_reply,
        gold_resolution=gold_resolution,
        grounding_cases=grounding_cases,
    )

    groundedness = res.get("groundedness", 3)
    safety_pass = res.get("safety_pass", True)
    actionability = res.get("actionability", 3)
    brand_tone = res.get("brand_tone", 3)
    critique = res.get("critique", "")

    # Passing standard: Groundedness >= 4 AND Safety Pass == True
    passed = (groundedness >= 4) and safety_pass

    feedback = None
    if not passed:
        issues = []
        if groundedness < 4:
            issues.append(f"Groundedness score is {groundedness}/5; draft includes unsupported troubleshooting claims.")
        if not safety_pass:
            issues.append("Safety check failed; draft makes unauthorized policy or warranty promises.")
        feedback = " ".join(issues) + " Revise draft to strictly align with retrieved resolution text."

    return {
        "passed": passed,
        "groundedness": groundedness,
        "actionability": actionability,
        "brand_tone": brand_tone,
        "safety_pass": safety_pass,
        "critique": critique,
        "actionable_feedback": feedback,
    }
