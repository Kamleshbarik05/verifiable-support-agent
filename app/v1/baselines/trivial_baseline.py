"""
baselines/trivial_baseline.py
Baseline 1 (Trivial):
Majority-class intent prediction + static canned reply + zero escalation.
"""

from typing import Any, Dict


class TrivialBaseline:
    """
    Trivial heuristic baseline for lower-bound benchmarking.
    """

    MAJORITY_INTENT = "HARDWARE_BATTERY_PERFORMANCE"
    CANNED_REPLY = (
        "Thank you for contacting Apple Support on Twitter. We would be glad to help! "
        "Please send us a direct message (DM) with your device model and iOS version."
    )

    def process(self, query: str) -> Dict[str, Any]:
        return {
            "customer_query": query,
            "intent": self.MAJORITY_INTENT,
            "intent_confidence": 0.50,
            "drafted_reply": self.CANNED_REPLY,
            "max_similarity_score": 0.0,
            "is_well_grounded": False,
            "should_escalate": False,
            "escalation_reason": "Trivial Baseline: Static auto-handle policy.",
            "reason_code": "TRIVIAL_STATIC",
            "escalation_tier": "TRIVIAL_BASELINE",
        }
