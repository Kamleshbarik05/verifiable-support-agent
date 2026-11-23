"""
app/observability/cost_model.py
Deterministic token cost model with versioned pricing tables.
Tracks input/output token pricing per 1M tokens across supported models.

Sources & References:
- Google Cloud Vertex AI Gemini Pricing (Effective October 2024 / Verified 2026):
  https://cloud.google.com/vertex-ai/generative-ai/pricing
- Text Embedding Pricing:
  https://cloud.google.com/vertex-ai/pricing#text-embeddings
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    model_id: str
    provider: str
    input_cost_per_million: float
    output_cost_per_million: float
    effective_date: str
    source_url: str


# Official Google Cloud Vertex AI & Offline Pricing Registry
PRICING_REGISTRY: dict[str, ModelPricing] = {
    # Gemini 3.8 Flash (Live AI Studio Default, verified 2026-11-23)
    "gemini-3.8-flash": ModelPricing(
        model_id="gemini-3.8-flash",
        provider="google-ai-studio",
        input_cost_per_million=0.075,
        output_cost_per_million=0.30,
        effective_date="2026-11-23",
        source_url="https://ai.google.dev/pricing",
    ),
    # Gemini 3.5 Flash (Live AI Studio, verified 2026-11-23)
    "gemini-3.5-flash": ModelPricing(
        model_id="gemini-3.5-flash",
        provider="google-ai-studio",
        input_cost_per_million=0.075,
        output_cost_per_million=0.30,
        effective_date="2026-11-23",
        source_url="https://ai.google.dev/pricing",
    ),
    # Gemini 1.5 Flash (General GA tier: <=128k context, Vertex target, verified 2026-11-23)
    "gemini-1.5-flash-002": ModelPricing(
        model_id="gemini-1.5-flash-002",
        provider="google-vertex-ai",
        input_cost_per_million=0.075,
        output_cost_per_million=0.30,
        effective_date="2024-10-01",
        source_url="https://cloud.google.com/vertex-ai/generative-ai/pricing#gemini-1.5-flash",
    ),
    "gemini-1.5-flash": ModelPricing(
        model_id="gemini-1.5-flash",
        provider="google-vertex-ai",
        input_cost_per_million=0.075,
        output_cost_per_million=0.30,
        effective_date="2024-10-01",
        source_url="https://cloud.google.com/vertex-ai/generative-ai/pricing#gemini-1.5-flash",
    ),
    # Gemini 1.5 Pro (General GA tier: <=128k context)
    "gemini-1.5-pro-002": ModelPricing(
        model_id="gemini-1.5-pro-002",
        provider="google-vertex-ai",
        input_cost_per_million=1.25,
        output_cost_per_million=5.00,
        effective_date="2024-10-01",
        source_url="https://cloud.google.com/vertex-ai/generative-ai/pricing#gemini-1.5-pro",
    ),
    "gemini-1.5-pro": ModelPricing(
        model_id="gemini-1.5-pro",
        provider="google-vertex-ai",
        input_cost_per_million=1.25,
        output_cost_per_million=5.00,
        effective_date="2024-10-01",
        source_url="https://cloud.google.com/vertex-ai/generative-ai/pricing#gemini-1.5-pro",
    ),
    # Text Embedding Gecko / text-embedding-004
    "text-embedding-004": ModelPricing(
        model_id="text-embedding-004",
        provider="google-vertex-ai",
        input_cost_per_million=0.025,
        output_cost_per_million=0.0,
        effective_date="2024-05-14",
        source_url="https://cloud.google.com/vertex-ai/pricing#text-embeddings",
    ),
    # Deterministic Local / Offline Mock Mode (Zero Cost)
    "offline-mock": ModelPricing(
        model_id="offline-mock",
        provider="local",
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        effective_date="2024-01-01",
        source_url="internal://offline-eval",
    ),
}


def get_model_pricing(model_name: str) -> ModelPricing | None:
    """Retrieves pricing specification for a registered model."""
    normalized = model_name.strip().lower()
    if normalized in PRICING_REGISTRY:
        return PRICING_REGISTRY[normalized]
    # Check partial match (e.g., 'flash' -> 'gemini-1.5-flash')
    for key, pricing in PRICING_REGISTRY.items():
        if key in normalized:
            return pricing
    return None


def calculate_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int = 0,
) -> float:
    """
    Computes total USD cost for a given token usage breakdown.
    Returns 0.0 if the model is offline or unknown.
    """
    pricing = get_model_pricing(model_name)
    if not pricing:
        return 0.0

    input_cost = (input_tokens / 1_000_000.0) * pricing.input_cost_per_million
    output_cost = (output_tokens / 1_000_000.0) * pricing.output_cost_per_million
    return round(input_cost + output_cost, 8)
