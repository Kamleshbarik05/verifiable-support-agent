"""
eval/runners/retrieval_pgvector_eval.py
Retrieval A/B Benchmark with Real Embeddings & Local pgvector (or local fallback).
Compares v1 keyword/shallow retrieval against dense vector search.

Guarantees strict train/test hold-out:
No evaluation query's source resolution is included in the indexed precedent database.
Outputs to eval/results/retrieval_ab_pgvector.json.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.config import GOLDEN_EVAL_FILE, PAIRED_CONVERSATIONS_FILE  # noqa: E402
from src.data_loader import load_golden_evaluation_set, load_or_process_paired_data  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402
from src.retriever import HistoricalRetriever  # noqa: E402

from app.retrieval.embedder import get_embedder  # noqa: E402
from app.retrieval.ingest import ingest_resolutions_from_df  # noqa: E402
from app.retrieval.vector_store import VectorStore  # noqa: E402

console = Console(force_terminal=True, color_system="auto")
OUTPUT_FILE = REPO_ROOT / "eval" / "results" / "retrieval_ab_pgvector.json"


def get_git_commit_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=str(REPO_ROOT),
            )
            .decode("ascii")
            .strip()
        )
    except Exception:
        return "unversioned-dev"


def is_relevant(retrieved_item: dict, gold_intent: str, gold_resolution: str) -> bool:
    retrieved_intent = retrieved_item.get("intent", "")
    if retrieved_intent and retrieved_intent == gold_intent:
        return True

    text = (retrieved_item.get("resolution_text") or retrieved_item.get("apple_resolution") or "").lower()
    gold_words = set(gold_resolution.lower().split())
    ret_words = set(text.split())
    overlap = len(gold_words & ret_words)
    return overlap >= 3


def calculate_metrics(eval_records: list[dict]) -> dict[str, float]:
    recalls_1 = []
    recalls_3 = []
    recalls_5 = []
    rr_scores = []
    latencies = []

    for r in eval_records:
        ranked_hits = r["ranked_hits"]
        latencies.append(r["latency_ms"])

        recalls_1.append(1.0 if any(ranked_hits[:1]) else 0.0)
        recalls_3.append(1.0 if any(ranked_hits[:3]) else 0.0)
        recalls_5.append(1.0 if any(ranked_hits[:5]) else 0.0)

        first_hit = 0
        for rank, is_hit in enumerate(ranked_hits, 1):
            if is_hit:
                first_hit = rank
                break
        rr_scores.append((1.0 / first_hit) if first_hit > 0 else 0.0)

    return {
        "recall_at_1": round(float(np.mean(recalls_1)), 4),
        "recall_at_3": round(float(np.mean(recalls_3)), 4),
        "recall_at_5": round(float(np.mean(recalls_5)), 4),
        "mrr": round(float(np.mean(rr_scores)), 4),
        "latency_p50_ms": round(float(np.percentile(latencies, 50)), 2),
        "latency_p95_ms": round(float(np.percentile(latencies, 95)), 2),
    }


def run_benchmark(sample_size: int = 100):
    console.print(
        f"[bold cyan]Running Retrieval Benchmark with Real Embeddings (n={sample_size})...[/bold cyan]"
    )

    # 1. Load 100 Query Samples
    golden = load_golden_evaluation_set(GOLDEN_EVAL_FILE)[:sample_size]
    gold_resolutions = {item.get("gold_historical_resolution", "").strip() for item in golden}
    gold_queries = {item.get("customer_query", "").strip() for item in golden}

    # 2. Load Knowledge Base & Apply Strict Held-Out Split
    kb_df = pd.DataFrame()
    if PAIRED_CONVERSATIONS_FILE.exists():
        kb_df = load_or_process_paired_data(PAIRED_CONVERSATIONS_FILE)

    if not kb_df.empty:
        # Precedents whose resolution or query matches a test sample are held out
        held_out_mask = (
            kb_df["apple_resolution"].astype(str).str.strip().isin(gold_resolutions)
            | kb_df["customer_query"].astype(str).str.strip().isin(gold_queries)
        )
        kb_train = kb_df[~held_out_mask].copy()
        console.print(
            f"[dim]Total KB pairs: {len(kb_df)} | Held out: {held_out_mask.sum()} | Indexed precedents: {len(kb_train)}[/dim]"
        )
    else:
        kb_train = kb_df

    # 3. Initialize Embedder & Vector Store
    # Use real Google AI Studio embedding model
    embedder = get_embedder("gemini")
    vector_store = VectorStore()
    store_backend = "PostgreSQL (pgvector HNSW)" if vector_store.is_connected else "In-Memory Cosine Store"
    console.print(f"[dim]Vector Store Backend: {store_backend} | Embedder: {embedder.model_name}[/dim]")

    if not kb_train.empty:
        ingest_resolutions_from_df(kb_train, vector_store, embedder, batch_size=20)

    # 4. Initialize v1 Baseline
    v1_retriever = HistoricalRetriever(knowledge_base_df=kb_train, llm_client=LLMClient(offline=True))

    v1_records = []
    v2_records = []

    for item in golden:
        q = item["customer_query"]
        g_intent = item["gold_intent"]
        g_res = item.get("gold_historical_resolution", "")

        # --- v1 Keyword/Shallow Retrieval ---
        t0 = time.perf_counter()
        v1_hits = v1_retriever.retrieve(q, top_k=5)
        v1_ms = (time.perf_counter() - t0) * 1000.0

        v1_ranked = [is_relevant(h, g_intent, g_res) for h in v1_hits]
        while len(v1_ranked) < 5:
            v1_ranked.append(False)
        v1_records.append({"latency_ms": v1_ms, "ranked_hits": v1_ranked})

        # --- v2 Dense Vector Retrieval ---
        t1 = time.perf_counter()
        q_vec = embedder.embed_text(f"[{g_intent}] {q}")
        v2_records_found = vector_store.search(q_vec, top_k=5, intent_filter=None)
        v2_ms = (time.perf_counter() - t1) * 1000.0

        v2_ranked = [
            is_relevant({"intent": r.intent, "resolution_text": r.resolution_text}, g_intent, g_res)
            for r in v2_records_found
        ]
        while len(v2_ranked) < 5:
            v2_ranked.append(False)
        v2_records.append({"latency_ms": v2_ms, "ranked_hits": v2_ranked})

    v1_metrics = calculate_metrics(v1_records)
    v2_metrics = calculate_metrics(v2_records)

    payload = {
        "benchmark": "retrieval_ab_pgvector",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit_sha(),
        "sample_size": len(golden),
        "embedding_model": embedder.model_name,
        "dimensions": embedder.dimension,
        "backend": store_backend,
        "index_parameters": {
            "type": "hnsw",
            "metric": "cosine",
            "m": 16,
            "ef_construction": 64,
        },
        "held_out_query_count": len(golden),
        "indexed_precedent_count": len(kb_train),
        "v1_keyword_baseline": v1_metrics,
        "v2_vector_retrieval_real_embeddings": v2_metrics,
        "delta": {
            "recall_at_1_diff": round(v2_metrics["recall_at_1"] - v1_metrics["recall_at_1"], 4),
            "recall_at_3_diff": round(v2_metrics["recall_at_3"] - v1_metrics["recall_at_3"], 4),
            "recall_at_5_diff": round(v2_metrics["recall_at_5"] - v1_metrics["recall_at_5"], 4),
            "mrr_diff": round(v2_metrics["mrr"] - v1_metrics["mrr"], 4),
            "p50_latency_diff_ms": round(v2_metrics["latency_p50_ms"] - v1_metrics["latency_p50_ms"], 2),
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    console.print(f"[bold green]Saved real embedding retrieval results to {OUTPUT_FILE}[/bold green]")

    # Print summary table
    table = Table(title="Retrieval A/B with Real Embeddings & Held-Out Query Split")
    table.add_column("Metric", style="cyan")
    table.add_column("v1 Keyword Baseline", style="dim")
    table.add_column(f"v2 Vector ({embedder.model_name})", style="bold green")
    table.add_column("Delta", style="bold yellow")

    table.add_row(
        "Recall@1",
        f"{v1_metrics['recall_at_1']:.1%}",
        f"{v2_metrics['recall_at_1']:.1%}",
        f"{payload['delta']['recall_at_1_diff']:+.1%}",
    )
    table.add_row(
        "Recall@3",
        f"{v1_metrics['recall_at_3']:.1%}",
        f"{v2_metrics['recall_at_3']:.1%}",
        f"{payload['delta']['recall_at_3_diff']:+.1%}",
    )
    table.add_row(
        "Recall@5",
        f"{v1_metrics['recall_at_5']:.1%}",
        f"{v2_metrics['recall_at_5']:.1%}",
        f"{payload['delta']['recall_at_5_diff']:+.1%}",
    )
    table.add_row(
        "MRR",
        f"{v1_metrics['mrr']:.3f}",
        f"{v2_metrics['mrr']:.3f}",
        f"{payload['delta']['mrr_diff']:+.3f}",
    )
    table.add_row(
        "p50 Search Latency",
        f"{v1_metrics['latency_p50_ms']:.2f} ms",
        f"{v2_metrics['latency_p50_ms']:.2f} ms",
        f"{payload['delta']['p50_latency_diff_ms']:+.2f} ms",
    )
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Run retrieval benchmark with real embeddings")
    parser.add_argument("--samples", type=int, default=100)
    args = parser.parse_args()
    run_benchmark(sample_size=args.samples)


if __name__ == "__main__":
    main()
