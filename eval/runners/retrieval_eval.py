"""
eval/runners/retrieval_eval.py
Retrieval A/B Benchmark: v1 Retrieval vs. v2 Vector Retrieval (pgvector).
Measures Recall@1, Recall@3, Recall@5, Mean Reciprocal Rank (MRR), and Latency (p50/p95).
Outputs eval/results/retrieval_ab.json for scientific comparison.
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
from rich.panel import Panel
from rich.table import Table

# Ensure project root and app/v1 are on sys.path
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


def get_git_commit_sha() -> str:
    """Retrieves current Git commit hash."""
    try:
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=str(REPO_ROOT),
            )
            .decode("ascii")
            .strip()
        )
        return commit
    except Exception:
        return "unversioned-dev"


def is_relevant(retrieved_item: dict, gold_intent: str, gold_resolution: str) -> bool:
    """
    Evaluates whether a retrieved resolution is relevant to the customer query:
    1. Intent alignment: Matches the customer's diagnostic intent category.
    2. Substantive overlap: Diagnostic troubleshooting keyword overlap.
    """
    retrieved_intent = retrieved_item.get("intent", "")
    if retrieved_intent and retrieved_intent == gold_intent:
        return True

    text = (retrieved_item.get("resolution_text") or retrieved_item.get("apple_resolution") or "").lower()
    gold_words = set(gold_resolution.lower().split())
    ret_words = set(text.split())
    overlap = len(gold_words & ret_words)
    return overlap >= 3


def calculate_retrieval_metrics(
    eval_records: list[dict],
) -> dict[str, float]:
    """Computes Recall@1, Recall@3, Recall@5, MRR, p50, and p95 latency."""
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

        # Reciprocal Rank (1 / first hit position)
        first_hit_rank = 0
        for rank, is_hit in enumerate(ranked_hits, 1):
            if is_hit:
                first_hit_rank = rank
                break
        rr = (1.0 / first_hit_rank) if first_hit_rank > 0 else 0.0
        rr_scores.append(rr)

    return {
        "recall_at_1": round(float(np.mean(recalls_1)), 4),
        "recall_at_3": round(float(np.mean(recalls_3)), 4),
        "recall_at_5": round(float(np.mean(recalls_5)), 4),
        "mrr": round(float(np.mean(rr_scores)), 4),
        "latency_p50_ms": round(float(np.percentile(latencies, 50)), 2),
        "latency_p95_ms": round(float(np.percentile(latencies, 95)), 2),
    }


def run_retrieval_ab_benchmark(
    sample_size: int = 100,
    output_file: Path = REPO_ROOT / "eval" / "results" / "retrieval_ab.json",
    provider: str = "local",
) -> dict:
    """Executes comparative evaluation between v1 and v2 retrieval."""
    console.print(
        Panel.fit(
            "[bold cyan]Retrieval A/B Evaluation[/bold cyan]\n"
            f"[dim]v1 Historical Keyword/Embedding vs. v2 pgvector Dense Embeddings | Samples: {sample_size}[/dim]",
            border_style="cyan",
        )
    )

    # 1. Load Datasets
    golden_dataset = load_golden_evaluation_set(GOLDEN_EVAL_FILE)
    if sample_size and sample_size < len(golden_dataset):
        golden_dataset = golden_dataset[:sample_size]

    kb_df = pd.DataFrame()
    if PAIRED_CONVERSATIONS_FILE.exists():
        kb_df = load_or_process_paired_data(PAIRED_CONVERSATIONS_FILE)

    # 2. Setup v1 Retriever
    llm = LLMClient(offline=True)
    v1_retriever = HistoricalRetriever(knowledge_base_df=kb_df, llm_client=llm)

    # 3. Setup v2 Vector Store & Ingest
    v2_store = VectorStore()
    embedder = get_embedder(provider=provider)
    if v2_store.count() == 0 and not kb_df.empty:
        ingest_resolutions_from_df(kb_df, v2_store, embedder, batch_size=50)

    v1_eval_records = []
    v2_eval_records = []

    console.print(f"[green][OK][/green] Benchmarking {len(golden_dataset)} queries on both retrieval engines...\n")

    for item in golden_dataset:
        query = item["customer_query"]
        gold_intent = item["gold_intent"]
        gold_resolution = item.get("gold_historical_resolution", "")

        # --- A. Evaluate v1 Retrieval ---
        t0 = time.perf_counter()
        v1_hits = v1_retriever.retrieve(query, top_k=5)
        v1_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        v1_ranked = [is_relevant(hit, gold_intent, gold_resolution) for hit in v1_hits]
        # Pad up to 5 if fewer returned
        while len(v1_ranked) < 5:
            v1_ranked.append(False)

        v1_eval_records.append({
            "latency_ms": v1_elapsed_ms,
            "ranked_hits": v1_ranked,
        })

        # --- B. Evaluate v2 Vector Retrieval ---
        t1 = time.perf_counter()
        q_vec = embedder.embed_text(f"[{gold_intent}] {query}")
        v2_records = v2_store.search(q_vec, top_k=5, intent_filter=None)
        v2_elapsed_ms = (time.perf_counter() - t1) * 1000.0

        v2_hits = [
            {"intent": rec.intent, "resolution_text": rec.resolution_text}
            for rec in v2_records
        ]
        v2_ranked = [is_relevant(hit, gold_intent, gold_resolution) for hit in v2_hits]
        while len(v2_ranked) < 5:
            v2_ranked.append(False)

        v2_eval_records.append({
            "latency_ms": v2_elapsed_ms,
            "ranked_hits": v2_ranked,
        })

    # 4. Compute Metrics
    v1_metrics = calculate_retrieval_metrics(v1_eval_records)
    v2_metrics = calculate_retrieval_metrics(v2_eval_records)

    results_payload = {
        "benchmark": "retrieval_ab_comparison",
        "git_commit": get_git_commit_sha(),
        "timestamp": datetime.now(UTC).isoformat(),
        "sample_size": len(golden_dataset),
        "embedder_model": embedder.model_name,
        "v1_retrieval": v1_metrics,
        "v2_vector_retrieval": v2_metrics,
        "delta": {
            "recall_at_1_diff": round(v2_metrics["recall_at_1"] - v1_metrics["recall_at_1"], 4),
            "recall_at_3_diff": round(v2_metrics["recall_at_3"] - v1_metrics["recall_at_3"], 4),
            "recall_at_5_diff": round(v2_metrics["recall_at_5"] - v1_metrics["recall_at_5"], 4),
            "mrr_diff": round(v2_metrics["mrr"] - v1_metrics["mrr"], 4),
            "p50_latency_diff_ms": round(v2_metrics["latency_p50_ms"] - v1_metrics["latency_p50_ms"], 2),
        },
    }

    # 5. Render Comparison Table
    table = Table(title="Retrieval A/B Benchmark Results", header_style="bold magenta")
    table.add_column("Metric", style="bold")
    table.add_column("v1 Retrieval", justify="right")
    table.add_column("v2 Vector (pgvector)", justify="right")
    table.add_column("Delta (v2 - v1)", justify="center")

    def format_delta(diff: float, is_latency: bool = False) -> str:
        if is_latency:
            # Lower latency is better
            return f"[green]{diff:+.2f} ms[/green]" if diff <= 0 else f"[yellow]{diff:+.2f} ms[/yellow]"
        return f"[green]{diff:+.2%}[/green]" if diff >= 0 else f"[red]{diff:+.2%}[/red]"

    table.add_row(
        "Recall@1",
        f"{v1_metrics['recall_at_1']:.2%}",
        f"{v2_metrics['recall_at_1']:.2%}",
        format_delta(results_payload["delta"]["recall_at_1_diff"]),
    )
    table.add_row(
        "Recall@3",
        f"{v1_metrics['recall_at_3']:.2%}",
        f"{v2_metrics['recall_at_3']:.2%}",
        format_delta(results_payload["delta"]["recall_at_3_diff"]),
    )
    table.add_row(
        "Recall@5",
        f"{v1_metrics['recall_at_5']:.2%}",
        f"{v2_metrics['recall_at_5']:.2%}",
        format_delta(results_payload["delta"]["recall_at_5_diff"]),
    )
    table.add_row(
        "MRR (Mean Reciprocal Rank)",
        f"{v1_metrics['mrr']:.3f}",
        f"{v2_metrics['mrr']:.3f}",
        f"{results_payload['delta']['mrr_diff']:+.3f}",
    )
    table.add_row(
        "p50 Latency",
        f"{v1_metrics['latency_p50_ms']:.2f} ms",
        f"{v2_metrics['latency_p50_ms']:.2f} ms",
        format_delta(results_payload["delta"]["p50_latency_diff_ms"], is_latency=True),
    )
    table.add_row(
        "p95 Latency",
        f"{v1_metrics['latency_p95_ms']:.2f} ms",
        f"{v2_metrics['latency_p95_ms']:.2f} ms",
        f"{v2_metrics['latency_p95_ms'] - v1_metrics['latency_p95_ms']:+.2f} ms",
    )

    console.print(table)

    # 6. Save JSON Output
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)

    console.print(f"\n[green][OK][/green] Retrieval A/B results saved to: [dim]{output_file}[/dim]\n")
    return results_payload


def main():
    parser = argparse.ArgumentParser(description="Retrieval A/B Benchmark Runner")
    parser.add_argument("--sample-size", type=int, default=100, help="Number of queries to benchmark")
    parser.add_argument("--provider", type=str, default="local", choices=["local", "vertex"], help="Embedder provider")
    parser.add_argument(
        "--output",
        type=str,
        default=str(REPO_ROOT / "eval" / "results" / "retrieval_ab.json"),
        help="Path for JSON output",
    )
    args = parser.parse_args()

    run_retrieval_ab_benchmark(
        sample_size=args.sample_size,
        output_file=Path(args.output),
        provider=args.provider,
    )


if __name__ == "__main__":
    main()
