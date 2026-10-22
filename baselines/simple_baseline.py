"""
baselines/simple_baseline.py
Baseline 2 (Simple):
Keyword-based intent heuristic + unconstrained zero-shot reply + naive keyword escalation.
"""

from typing import Any, Dict, Optional
from src.data_loader import clean_tweet_text
from src.llm_client import LLMClient


class SimpleBaseline:
    """
    Simple baseline representing an ungrounded zero-shot chatbot with naive regex escalation.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def process(self, query: str) -> Dict[str, Any]:
        cleaned = clean_tweet_text(query)
        cleaned_lower = cleaned.lower()

        # 1. Simple keyword-based intent classification
        if "battery" in cleaned_lower or "drain" in cleaned_lower:
            intent = "HARDWARE_BATTERY_PERFORMANCE"
        elif "update" in cleaned_lower or "ios" in cleaned_lower:
            intent = "SOFTWARE_OS_UPDATE"
        elif "password" in cleaned_lower or "id" in cleaned_lower:
            intent = "APPLE_ID_SECURITY_ACCESS"
        elif "bill" in cleaned_lower or "charge" in cleaned_lower:
            intent = "BILLING_SUBSCRIPTION_REFUND"
        else:
            intent = "USAGE_FEATURE_HOWTO"

        # 2. Naive keyword-only escalation check
        naive_escalation_words = ["human", "agent", "person", "representative", "call me"]
        should_escalate = any(w in cleaned_lower for w in naive_escalation_words)
        reason = (
            "Customer explicitly requested a human agent."
            if should_escalate
            else "No human escalation keywords detected."
        )

        # 3. Unconstrained Zero-Shot Prompting (No RAG grounding, prone to hallucination)
        reply = self.llm.generate(
            user_prompt=f"Customer issue: {cleaned}\nWrite an Apple Support reply:",
            system_prompt="You are a helpful customer service chatbot for Apple.",
            temperature=0.7,
            max_tokens=100,
        )

        return {
            "customer_query": cleaned,
            "intent": intent,
            "intent_confidence": 0.65,
            "drafted_reply": reply,
            "max_similarity_score": 0.0,
            "is_well_grounded": False,
            "should_escalate": should_escalate,
            "escalation_reason": reason,
            "reason_code": "SIMPLE_KEYWORD_MATCH",
            "escalation_tier": "SIMPLE_BASELINE",
        }
