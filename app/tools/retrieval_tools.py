"""
app/tools/retrieval_tools.py
Production tool wrapper for dense vector similarity search over pgvector.
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

from src.config import PAIRED_CONVERSATIONS_FILE  # noqa: E402
from src.data_loader import load_or_process_paired_data  # noqa: E402

from app.retrieval.embedder import Embedder, get_embedder  # noqa: E402
from app.retrieval.ingest import ingest_resolutions_from_df  # noqa: E402
from app.retrieval.vector_store import VectorStore  # noqa: E402

_default_store: VectorStore | None = None
_default_embedder: Embedder | None = None


def get_default_retrieval_components() -> tuple[VectorStore, Embedder]:
    """Initializes and returns cached singleton vector store and embedder."""
    global _default_store, _default_embedder
    if _default_store is None:
        _default_store = VectorStore()
        _default_embedder = get_embedder()
        # Seed in-memory store if database is empty/offline
        if _default_store.count() == 0 and PAIRED_CONVERSATIONS_FILE.exists():
            kb_df = load_or_process_paired_data(PAIRED_CONVERSATIONS_FILE)
            ingest_resolutions_from_df(kb_df, _default_store, _default_embedder, batch_size=50)
    return _default_store, _default_embedder


def search_resolutions_tool(
    query: str,
    intent: str | None = None,
    top_k: int = 3,
    vector_store: VectorStore | None = None,
    embedder: Embedder | None = None,
) -> list[dict[str, Any]]:
    """
    Embeds customer query and executes hybrid vector similarity search in pgvector.
    Returns ranked list of resolution records.
    """
    store, emb = get_default_retrieval_components()
    active_store = vector_store or store
    active_embedder = embedder or emb

    embed_target = f"[{intent}] {query}" if intent else query
    query_vec = active_embedder.embed_text(embed_target)

    records = active_store.search(
        query_embedding=query_vec,
        top_k=top_k,
        intent_filter=intent,
    )

    return [
        {
            "id": r.id,
            "brand_text": r.brand_text,
            "issue_text": r.issue_text,
            "resolution_text": r.resolution_text,
            "intent": r.intent,
            "similarity_score": r.similarity_score,
        }
        for r in records
    ]
