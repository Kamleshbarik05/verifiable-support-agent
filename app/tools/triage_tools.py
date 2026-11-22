"""
app/tools/triage_tools.py
Production tool wrappers for intent classification and escalation risk triage.
Wraps existing, battle-tested v1 components without altering their logic.
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

from src.classifier import IntentClassifier  # noqa: E402
from src.escalation import EscalationEngine  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402

_default_llm = LLMClient(offline=True)
_default_classifier = IntentClassifier(llm_client=_default_llm)
_default_escalation = EscalationEngine()


def classify_intent_tool(query: str, classifier: IntentClassifier | None = None) -> dict[str, Any]:
    """
    Classifies customer query into 1 of the 7 MECE intent categories.
    Returns: intent, confidence, reasoning.
    """
    clf = classifier or _default_classifier
    return clf.classify(query)


def risk_gate_tool(
    query: str,
    predicted_intent: str,
    intent_confidence: float,
    rag_similarity_score: float = 0.85,
    escalation_engine: EscalationEngine | None = None,
) -> dict[str, Any]:
    """
    Evaluates Tier 1 (deterministic safety/PII/legal hazards)
    and Tier 2 (financial/ambiguity/low confidence) risk gates.
    """
    engine = escalation_engine or _default_escalation
    return engine.decide(
        customer_query=query,
        predicted_intent=predicted_intent,
        intent_confidence=intent_confidence,
        rag_similarity_score=rag_similarity_score,
    )
