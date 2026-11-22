"""
src/pipeline.py
End-to-end unified customer support agent orchestrator.
Coordinates cleaning, intent classification, RAG historical retrieval,
grounded reply generation, and risk-aware escalation triage.
"""

from typing import Any, Dict, Optional
import pandas as pd

from src.classifier import IntentClassifier
from src.data_loader import clean_tweet_text
from src.escalation import EscalationEngine
from src.llm_client import LLMClient
from src.retriever import HistoricalRetriever


class SupportAgentPipeline:
    """
    Unified end-to-end AI customer support agent.
    """

    def __init__(
        self,
        knowledge_base_df: Optional[pd.DataFrame] = None,
        llm_client: Optional[LLMClient] = None,
        confidence_threshold: Optional[float] = None,
        similarity_threshold: Optional[float] = None,
    ):
        self.llm = llm_client or LLMClient()
        self.classifier = IntentClassifier(llm_client=self.llm)
        self.retriever = HistoricalRetriever(
            knowledge_base_df=knowledge_base_df, llm_client=self.llm
        )

        escalation_kwargs = {}
        if confidence_threshold is not None:
            escalation_kwargs["confidence_threshold"] = confidence_threshold
        if similarity_threshold is not None:
            escalation_kwargs["similarity_threshold"] = similarity_threshold

        self.escalation_engine = EscalationEngine(**escalation_kwargs)

    def process(self, raw_tweet: str) -> Dict[str, Any]:
        """
        Executes the full triage and response pipeline for an incoming tweet.

        Returns a structured dictionary:
        {
            "customer_query": str,
            "intent": str,
            "intent_confidence": float,
            "intent_reasoning": str,
            "drafted_reply": str,
            "max_similarity_score": float,
            "is_well_grounded": bool,
            "retrieved_cases": list,
            "should_escalate": bool,
            "escalation_reason": str,
            "reason_code": str,
            "escalation_tier": str
        }
        """
        # 1. Normalize text
        cleaned_query = clean_tweet_text(raw_tweet)

        # 2. Intent Classification & Confidence Scoring
        classification = self.classifier.classify(cleaned_query)
        predicted_intent = classification["intent"]
        confidence = classification["confidence"]
        reasoning = classification["reasoning"]

        # 3. Retrieve Historical Resolutions (RAG)
        retrieved_cases = self.retriever.retrieve(cleaned_query)
        max_similarity = (
            retrieved_cases[0]["similarity_score"] if retrieved_cases else 0.0
        )

        # 4. Draft Grounded Response
        draft_result = self.retriever.draft_grounded_reply(
            customer_query=cleaned_query,
            retrieved_resolutions=retrieved_cases,
            predicted_intent=predicted_intent,
        )

        # 5. Two-Tier Risk-Based Escalation Triage
        triage_decision = self.escalation_engine.decide(
            customer_query=cleaned_query,
            predicted_intent=predicted_intent,
            intent_confidence=confidence,
            rag_similarity_score=max_similarity,
        )

        # 6. Assemble complete audit trail
        return {
            "customer_query": cleaned_query,
            "intent": predicted_intent,
            "intent_confidence": confidence,
            "intent_reasoning": reasoning,
            "drafted_reply": draft_result["drafted_reply"],
            "max_similarity_score": max_similarity,
            "is_well_grounded": draft_result["is_well_grounded"],
            "retrieved_cases": retrieved_cases,
            "should_escalate": triage_decision["should_escalate"],
            "escalation_reason": triage_decision["stated_reason"],
            "reason_code": triage_decision["reason_code"],
            "escalation_tier": triage_decision["tier"],
        }
