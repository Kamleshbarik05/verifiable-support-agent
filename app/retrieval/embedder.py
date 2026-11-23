"""
app/retrieval/embedder.py
Standardized Embedder interface for Google Cloud Vertex AI and offline local testing.
Generates 768-dimensional normalized embedding vectors.

Supported Models:
- Vertex AI: text-embedding-004 (Google Cloud flagship text embedding)
- Local Fallback: Deterministic unit-normalized pseudo-embedding for zero-cost offline tests.
"""

import hashlib
import os
from abc import ABC, abstractmethod

import numpy as np

from app.config import VERTEX_EMBEDDING_MODEL


class Embedder(ABC):
    """Abstract interface for dense text embedding generation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Returns the output vector dimensionality."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Returns the model identifier."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embeds a single string into a normalized dense vector."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embeds a batch of strings into normalized dense vectors."""
        pass


class LocalFallbackEmbedder(Embedder):
    """
    Deterministic offline embedder.
    Generates consistent 768-dimensional L2-normalized vectors using
    SHA-256 seeded pseudo-random projections. Guarantees that identical
    texts produce identical vectors with zero external network or API calls.
    """

    def __init__(self, dimension: int = 768):
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return "local-fallback-deterministic-768"

    def embed_text(self, text: str) -> list[float]:
        # Hash text to generate deterministic pseudo-random seed
        cleaned = text.strip().lower()
        seed_bytes = hashlib.sha256(cleaned.encode("utf-8")).digest()
        seed_int = int.from_bytes(seed_bytes[:4], byteorder="big")

        rng = np.random.default_rng(seed_int)
        vec = rng.standard_normal(self._dim).astype(np.float32)

        # Token-level ngram projection for semantic overlap approximation
        words = cleaned.split()
        for w in words:
            w_seed = int.from_bytes(hashlib.md5(w.encode("utf-8")).digest()[:4], byteorder="big")
            w_rng = np.random.default_rng(w_seed)
            vec += w_rng.standard_normal(self._dim).astype(np.float32) * 0.35

        # L2 Normalization (Cosine Similarity == Dot Product)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


class VertexAIEmbedder(Embedder):
    """
    Google Cloud Vertex AI Embedder.
    Calls text-embedding-004 via Google Cloud GenAI SDK.
    Falls back to LocalFallbackEmbedder if credentials or internet are absent.
    """

    def __init__(
        self,
        project_id: str | None = None,
        location: str = "us-central1",
        model_name: str = VERTEX_EMBEDDING_MODEL,
        dimension: int = 768,
    ):
        self._project_id = project_id or os.getenv("PROJECT_ID")
        self._location = location or os.getenv("REGION", "us-central1")
        self._model_name = model_name
        self._dim = dimension
        self._fallback = LocalFallbackEmbedder(dimension=dimension)
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            # Check for Google GenAI SDK (Vertex AI mode)
            from google import genai
            self._client = genai.Client(
                vertexai=True,
                project=self._project_id,
                location=self._location,
            )
        except Exception:
            self._client = None

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_text(self, text: str) -> list[float]:
        if not self._client:
            return self._fallback.embed_text(text)

        try:
            response = self._client.models.embed_content(
                model=self._model_name,
                contents=text,
            )
            embedding = response.embedding.values
            # Ensure unit normalization
            vec = np.array(embedding, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec.tolist()
        except Exception:
            # Graceful fallback on API timeout or credentials issue
            return self._fallback.embed_text(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._client:
            return self._fallback.embed_batch(texts)

        try:
            response = self._client.models.embed_content(
                model=self._model_name,
                contents=texts,
            )
            results = []
            for emb in response.embeddings:
                vec = np.array(emb.values, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                results.append(vec.tolist())
            return results
        except Exception:
            return self._fallback.embed_batch(texts)


def get_embedder(provider: str | None = None) -> Embedder:
    """Factory creating configured Embedder instance."""
    prov = (provider or os.getenv("EMBEDDER_PROVIDER", "local")).strip().lower()
    if prov in ("vertex", "vertexai", "gcp"):
        return VertexAIEmbedder()
    return LocalFallbackEmbedder()
