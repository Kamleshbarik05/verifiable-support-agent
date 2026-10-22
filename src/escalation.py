"""
src/escalation.py
Two-tier risk-aware escalation engine.
Enforces deterministic safety guardrails and probabilistic quality gates,
producing an auditable stated reason for every triage decision.
"""

import re
from typing import Any, Dict, List
from src.config import (
    ESCALATION_HARD_KEYWORDS,
    INTENT_CONFIDENCE_THRESHOLD,
    RAG_SIMILARITY_THRESHOLD,
)


class EscalationEngine:
    """
    Decides whether a customer query should be auto-handled by AI
    or escalated to a human agent, providing an auditable stated reason.
    """

    def __init__(
        self,
        confidence_threshold: float = INTENT_CONFIDENCE_THRESHOLD,
        similarity_threshold: float = RAG_SIMILARITY_THRESHOLD,
        hard_keywords: List[str] = ESCALATION_HARD_KEYWORDS,
    ):
        self.confidence_threshold = confidence_threshold
        self.similarity_threshold = similarity_threshold
        self.hard_keywords = hard_keywords

    def _check_hard_guardrails(self, query: str) -> Dict[str, Any]:
        """
        Tier 1: Deterministic check for physical safety, legal threats,
        security compromises, and public PII leakage.
        """
        query_lower = query.lower()

        # 1. Hard safety and legal keywords
        for keyword in self.hard_keywords:
            if re.search(r"\b" + re.escape(keyword) + r"\b", query_lower):
                return {
                    "should_escalate": True,
                    "reason_code": "HARD_GUARDRAIL_SAFETY_LEGAL",
                    "stated_reason": f"Customer mentioned safety-critical or legal trigger: '{keyword}'. Requires immediate human protocol.",
                }

        # 2. PII Detection (Email addresses or Phone numbers in public tweet)
        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        phone_pattern = r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"

        if re.search(email_pattern, query):
            return {
                "should_escalate": True,
                "reason_code": "HARD_GUARDRAIL_PII_EXPOSURE",
                "stated_reason": "Customer shared personal email publicly in tweet; must escalate to secure DM immediately.",
            }

        if re.search(phone_pattern, query):
            return {
                "should_escalate": True,
                "reason_code": "HARD_GUARDRAIL_PII_EXPOSURE",
                "stated_reason": "Customer shared phone number publicly in tweet; must escalate to secure DM immediately.",
            }

        return {"should_escalate": False, "reason_code": "PASS", "stated_reason": ""}

    def decide(
        self,
        customer_query: str,
        predicted_intent: str,
        intent_confidence: float,
        rag_similarity_score: float,
    ) -> Dict[str, Any]:
        """
        Main decision triage pipeline.
        Evaluates Tier 1 (Hard Guardrails) then Tier 2 (Quality & Risk Gates).
        """
        # ==========================================
        # TIER 1: DETERMINISTIC HARD GUARDRAILS
        # ==========================================
        tier1_result = self._check_hard_guardrails(customer_query)
        if tier1_result["should_escalate"]:
            return {
                "should_escalate": True,
                "stated_reason": tier1_result["stated_reason"],
                "reason_code": tier1_result["reason_code"],
                "tier": "TIER_1_HARD_GUARDRAIL",
            }

        # ==========================================
        # TIER 2: PROBABILISTIC QUALITY & RISK GATES
        # ==========================================
        # Check 1: High-Risk Financial / Account Intents
        # Financial refunds and account lockouts require human authorization
        if predicted_intent == "BILLING_SUBSCRIPTION_REFUND":
            return {
                "should_escalate": True,
                "stated_reason": "Billing dispute / refund request requires human agent review and transaction authorization.",
                "reason_code": "INTENT_HIGH_RISK_FINANCIAL",
                "tier": "TIER_2_POLICY_RISK",
            }

        if predicted_intent == "APPLE_ID_SECURITY_ACCESS" and intent_confidence > 0.85:
            # If explicit lock or security lockout, escalate to authenticated channel
            if any(w in customer_query.lower() for w in ["locked", "compromised", "hacked", "stolen", "unrecognized"]):
                return {
                    "should_escalate": True,
                    "stated_reason": "Apple ID security breach or lockout detected; requires authenticated human identity verification.",
                    "reason_code": "INTENT_SECURITY_VERIFICATION",
                    "tier": "TIER_2_POLICY_RISK",
                }

        # Check 2: Intent Confidence Gate (Ambiguity Check)
        if intent_confidence < self.confidence_threshold:
            return {
                "should_escalate": True,
                "stated_reason": (
                    f"Intent classification confidence ({intent_confidence:.2f}) is below safe threshold "
                    f"({self.confidence_threshold:.2f}). Query is ambiguous; escalating to human."
                ),
                "reason_code": "AMBIGUITY_LOW_CONFIDENCE",
                "tier": "TIER_2_QUALITY_GATE",
            }

        # Check 3: Retrieval Grounding Gate (Hallucination Prevention)
        if rag_similarity_score < self.similarity_threshold:
            return {
                "should_escalate": True,
                "stated_reason": (
                    f"Historical resolution retrieval similarity ({rag_similarity_score:.2f}) is below threshold "
                    f"({self.similarity_threshold:.2f}). No verified historical precedent exists; escalating to avoid hallucination."
                ),
                "reason_code": "GROUNDING_NO_HISTORICAL_PRECEDENT",
                "tier": "TIER_2_QUALITY_GATE",
            }

        # ==========================================
        # TIER 3: SAFE FOR AUTOMATED HANDLING
        # ==========================================
        return {
            "should_escalate": False,
            "stated_reason": (
                f"Auto-handled: High intent confidence ({intent_confidence:.2f}) on standard '{predicted_intent}' diagnostic, "
                f"well-grounded in historical resolution (similarity {rag_similarity_score:.2f})."
            ),
            "reason_code": "AUTO_HANDLED_HIGH_CONFIDENCE",
            "tier": "AUTO_HANDLED",
        }
