"""
tests/test_retrieval.py
Unit tests for dense embedding generation, dual-mode vector storage,
HNSW indexing abstractions, and idempotent ingestion.
"""

import numpy as np
import pandas as pd
import pytest

from app.retrieval.embedder import LocalFallbackEmbedder, get_embedder
from app.retrieval.ingest import generate_source_hash, ingest_resolutions_from_df
from app.retrieval.vector_store import VectorStore


def test_embedder_output_dimension_and_l2_normalization():
    embedder = get_embedder(provider="local")
    assert embedder.dimension == 768

    text = "My iPhone 12 battery drains from 100% to 20% in 3 hours."
    vec = embedder.embed_text(text)
    assert len(vec) == 768

    # Verify L2 Unit Normalization (norm == 1.0)
    norm = np.linalg.norm(np.array(vec))
    assert pytest.approx(norm, 1e-4) == 1.0


def test_embedder_deterministic_repeatability():
    embedder = LocalFallbackEmbedder(dimension=768)
    text = "How do I set up Personal Hotspot on iOS 17?"
    vec1 = embedder.embed_text(text)
    vec2 = embedder.embed_text(text)
    assert vec1 == vec2


def test_source_hash_generation():
    query = "Screen is cracked and smoking"
    resolution = "Visit an Apple Authorized Service Provider immediately."
    h1 = generate_source_hash(query, resolution)
    h2 = generate_source_hash(query, resolution)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex string


def test_vector_store_in_memory_crud_and_search():
    store = VectorStore(db_host="invalid-host-for-fallback", db_port=9999)
    assert store.is_connected is False  # Confirms in-memory fallback mode

    embedder = LocalFallbackEmbedder()
    rec1_emb = embedder.embed_text("[HARDWARE_BATTERY_PERFORMANCE] Battery draining fast")
    rec2_emb = embedder.embed_text("[BILLING_SUBSCRIPTION_REFUND] Charged twice for iCloud storage")

    records = [
        {
            "id": "test_1",
            "brand_text": "@AppleSupport",
            "issue_text": "Battery draining fast",
            "resolution_text": "Check battery health in Settings > Battery.",
            "intent": "HARDWARE_BATTERY_PERFORMANCE",
            "embedding": rec1_emb,
            "source_hash": "hash_1",
        },
        {
            "id": "test_2",
            "brand_text": "@AppleSupport",
            "issue_text": "Charged twice for iCloud storage",
            "resolution_text": "Review purchase history at reportaproblem.apple.com.",
            "intent": "BILLING_SUBSCRIPTION_REFUND",
            "embedding": rec2_emb,
            "source_hash": "hash_2",
        },
    ]

    inserted = store.upsert_batch(records)
    assert inserted == 2
    assert store.count() == 2

    # Idempotent deduplication test: Re-inserting the same records must insert 0
    duplicate_inserted = store.upsert_batch(records)
    assert duplicate_inserted == 0
    assert store.count() == 2

    # Search for battery issue
    query_vec = embedder.embed_text("[HARDWARE_BATTERY_PERFORMANCE] My battery drains rapidly")
    hits = store.search(query_vec, top_k=2)
    assert len(hits) == 2
    assert hits[0].id == "test_1"  # Best match should be battery record
    assert hits[0].intent == "HARDWARE_BATTERY_PERFORMANCE"
    assert hits[0].similarity_score > hits[1].similarity_score

    # Hybrid Search with Intent Filter
    billing_hits = store.search(query_vec, top_k=2, intent_filter="BILLING_SUBSCRIPTION_REFUND")
    assert len(billing_hits) == 1
    assert billing_hits[0].id == "test_2"


def test_ingest_pipeline_idempotency():
    sample_df = pd.DataFrame([
        {
            "customer_tweet_id": "t_01",
            "customer_query": "My iPhone battery health is at 79% and needs service.",
            "apple_tweet_id": "r_01",
            "apple_resolution": "Visit support.apple.com/repair to schedule battery replacement.",
        },
        {
            "customer_tweet_id": "t_02",
            "customer_query": "How do I cancel my Apple Music trial before being billed?",
            "apple_tweet_id": "r_02",
            "apple_resolution": "Go to Settings > [Your Name] > Subscriptions and tap Cancel.",
        },
    ])

    store = VectorStore(db_host="invalid-host-for-fallback", db_port=9999)
    embedder = LocalFallbackEmbedder()

    # First pass
    stats1 = ingest_resolutions_from_df(sample_df, store, embedder, batch_size=10)
    assert stats1["inserted"] == 2
    assert stats1["skipped"] == 0
    assert store.count() == 2

    # Second pass (Idempotent: 0 inserted, 2 skipped)
    stats2 = ingest_resolutions_from_df(sample_df, store, embedder, batch_size=10)
    assert stats2["inserted"] == 0
    assert stats2["skipped"] == 2
    assert store.count() == 2
