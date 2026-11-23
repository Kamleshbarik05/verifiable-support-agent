"""
app/config.py
Centralized model configuration and environment variable overrides.

Verified Date: 2026-11-23
Official Documentation Sources:
- Vertex AI Gemini Models & Lifecycle:
  https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models
- Vertex AI Text Embeddings:
  https://cloud.google.com/vertex-ai/pricing#text-embeddings
- Google AI Studio Models:
  https://ai.google.dev/gemini-api/docs/models
"""

import os

# ==============================================================================
# Model Configurations
# ==============================================================================

# Default model for live Google AI Studio execution
# Verified available via Google AI Studio API key
DEFAULT_LIVE_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Target deployment model on Google Cloud Vertex AI
# Note: Target architecture specification; never executed against live Vertex AI.
VERTEX_TARGET_MODEL: str = os.getenv("VERTEX_MODEL", "gemini-1.5-flash-002")

# Target text embedding model on Google Cloud Vertex AI (768 dimensions)
# Note: Target architecture specification; never executed against live Vertex AI.
VERTEX_EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-004")

# Offline mock model identifier used for zero-cost, deterministic local evaluation
OFFLINE_MOCK_MODEL: str = "offline-mock"


def get_active_llm_model(is_offline: bool = False) -> str:
    """Returns active model name based on execution mode."""
    if is_offline:
        return OFFLINE_MOCK_MODEL
    # If Google AI Studio key is present, default to live model; otherwise target model name
    if os.getenv("GEMINI_API_KEY"):
        return DEFAULT_LIVE_MODEL
    return VERTEX_TARGET_MODEL


def get_active_embedding_model(is_offline: bool = False) -> str:
    """Returns active embedding model name based on execution mode."""
    if is_offline:
        return OFFLINE_MOCK_MODEL
    return VERTEX_EMBEDDING_MODEL
