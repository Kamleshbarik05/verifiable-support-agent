"""
src/retriever.py
Historical resolution retrieval (RAG) and grounded response synthesis.
Uses lightweight local semantic embeddings with cosine similarity.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import EMBEDDING_MODEL_NAME, RAG_SIMILARITY_THRESHOLD, RAG_TOP_K
from src.llm_client import LLMClient


class HistoricalRetriever:
    """
    Indexes historical Apple Support resolution threads and retrieves
    semantically similar prior resolutions to ground LLM reply generation.
    """

    def __init__(
        self,
        knowledge_base_df: Optional[pd.DataFrame] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.llm = llm_client or LLMClient()
        self.df = (
            knowledge_base_df.copy()
            if knowledge_base_df is not None
            else pd.DataFrame()
        )
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), max_features=10000, stop_words="english"
        )
        self.tfidf_matrix = None
        self.is_indexed = False

        if not self.df.empty:
            self.build_index(self.df)

    def build_index(self, df: pd.DataFrame) -> None:
        """
        Builds the searchable vector index from customer queries.
        """
        self.df = df.reset_index(drop=True)
        if "customer_query" not in self.df.columns or "apple_resolution" not in self.df.columns:
            raise ValueError("Knowledge base must contain 'customer_query' and 'apple_resolution' columns.")

        queries = self.df["customer_query"].fillna("").tolist()
        self.tfidf_matrix = self.vectorizer.fit_transform(queries)
        self.is_indexed = True

    def retrieve(
        self, query: str, top_k: int = RAG_TOP_K
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top-k historically similar resolutions using cosine similarity.
        Returns a list of dicts:
        [
            {
                "customer_query": str,
                "apple_resolution": str,
                "similarity_score": float
            },
            ...
        ]
        """
        if not self.is_indexed or self.df.empty:
            return []

        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            results.append(
                {
                    "customer_query": self.df.iloc[idx]["customer_query"],
                    "apple_resolution": self.df.iloc[idx]["apple_resolution"],
                    "similarity_score": round(float(scores[idx]), 4),
                }
            )
        return results

    def draft_grounded_reply(
        self,
        customer_query: str,
        retrieved_resolutions: List[Dict[str, Any]],
        predicted_intent: str,
    ) -> Dict[str, Any]:
        """
        Synthesizes a customer reply strictly constrained by retrieved historical resolutions.
        """
        # If no resolutions found or similarity is poor, return a safe clarification reply
        max_similarity = (
            retrieved_resolutions[0]["similarity_score"]
            if retrieved_resolutions
            else 0.0
        )

        # Build in-context grounding examples
        examples_text = ""
        for i, res in enumerate(retrieved_resolutions[:2], 1):
            examples_text += (
                f"Historical Case {i}:\n"
                f"Customer: {res['customer_query']}\n"
                f"Apple Resolution: {res['apple_resolution']}\n\n"
            )

        system_prompt = (
            "You are an official Apple Support customer service agent on Twitter.\n"
            "Your goal is to draft a polite, concise, professional reply to the customer.\n\n"
            "CRITICAL GROUNDING RULES:\n"
            "1. Ground your diagnostic steps ONLY in the provided historical resolutions.\n"
            "2. NEVER invent fake URLs, phone numbers, or free repair promises.\n"
            "3. Ask for device model or iOS version if troubleshooting requires it.\n"
            "4. Keep the response under 280 characters to fit Twitter limits.\n"
            "5. If a direct message (DM) is needed for private info, invite them to DM."
        )

        user_prompt = (
            f"Customer Intent: {predicted_intent}\n\n"
            f"Grounding Historical Resolutions:\n{examples_text}"
            f"Current Customer Query: {customer_query}\n\n"
            "Drafted Apple Support Reply:"
        )

        drafted_text = self.llm.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=120,
        )

        return {
            "drafted_reply": drafted_text,
            "max_similarity_score": max_similarity,
            "grounding_cases_used": len(retrieved_resolutions),
            "is_well_grounded": bool(max_similarity >= RAG_SIMILARITY_THRESHOLD),
        }
