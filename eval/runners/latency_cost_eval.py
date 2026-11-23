"""
eval/runners/latency_cost_eval.py
Benchmarking runner for LLM-native observability metrics:
- Latency breakdown (p50/p95) per agent step (Triage, Retrieval, Draft, Guard, Critic)
- Tokens per second throughput
- Cost per request ($) via versioned pricing model
- Bounded self-reflection revision loop distribution (0, 1, 2 revisions)

Outputs results deterministically to eval/results/latency_cost.json.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Ensure project root and app/v1 are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.agents.orchestrator import OrchestratorAgent  # noqa: E402
from app.retrieval.ingest import ingest_resolutions  # noqa: E402
from app.retrieval.vector_store import get_vector_store  # noqa: E402
from eval.runners.e2e_eval import load_golden_evaluation_set  # noqa: E402

console = Console()

DATASETS_DIR = REPO_ROOT / "eval" / "datasets"
GOLDEN_EVAL_FILE = DATASETS_DIR / "golden_evaluation_set.json"
PAIRED_CONVERSATIONS_FILE = DATASETS_DIR / "apple_conversations_paired.csv"
OUTPUT_FILE = REPO_ROOT / "eval" / "results" / "latency_cost.json"


def get_git_commit_hash() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def run_latency_cost_eval(
    sample_size: int = 100,
    output_path: Path = OUTPUT_FILE,
) -> dict:
    console.print(
        Panel.fit(
            f"[bold cyan]LLM-Native Metrics & Observability Benchmark[/bold cyan]\n"
            f"[dim]Evaluating latency breakdown, token throughput, and cost across {sample_size} samples[/dim]",
            border_style="cyan",
        )
    )

    # 1. Ensure Vector Store is primed
    store = get_vector_store()
    if store.count() == 0 and PAIRED_CONVERSATIONS_FILE.exists():
        console.print("[dim]Seeding vector store...[/dim]")
        ingest_resolutions(PAIRED_CONVERSATIONS_FILE)

    # 2. Load Evaluation Data
    dataset = load_golden_evaluation_set(GOLDEN_EVAL_FILE)
    if sample_size and sample_size < len(dataset):
        dataset = dataset[:sample_size]

    orchestrator = OrchestratorAgent(max_revisions=2)

    total_latencies: list[float] = []
    step_latencies: dict[str, list[float]] = {
        "triage": [],
        "retrieval": [],
        "draft": [],
        "policy_guard": [],
        "critic": [],
    }
    tokens_per_sec_list: list[float] = []
    costs_per_req: list[float] = []
    revisions_list: list[int] = []

    console.print(f"[green][OK][/green] Benchmarking {len(dataset)} customer inquiries...\n")

    for item in dataset:
        query = item["customer_query"]
        t0 = time.perf_counter()
        state = orchestrator.process_ticket(query)
        total_lat = (time.perf_counter() - t0) * 1000.0
        total_latencies.append(total_lat)

        revisions_list.append(state.revision_count)
        costs_per_req.append(state.total_cost_usd)

        # Collect step latencies from step_metrics
        for m in state.step_metrics:
            for step_key in step_latencies:
                if step_key in m.step_name:
                    step_latencies[step_key].append(m.latency_ms)
            if m.tokens_per_second > 0:
                tokens_per_sec_list.append(m.tokens_per_second)

    # 3. Compute Aggregated Metrics
    p50_total = float(np.percentile(total_latencies, 50))
    p95_total = float(np.percentile(total_latencies, 95))

    p50_by_step = {}
    p95_by_step = {}
    for step, lats in step_latencies.items():
        if lats:
            p50_by_step[step] = round(float(np.percentile(lats, 50)), 2)
            p95_by_step[step] = round(float(np.percentile(lats, 95)), 2)
        else:
            p50_by_step[step] = 0.0
            p95_by_step[step] = 0.0

    mean_tokens_per_sec = (
        round(float(np.mean(tokens_per_sec_list)), 2) if tokens_per_sec_list else 0.0
    )
    mean_cost = round(float(np.mean(costs_per_req)), 6)
    total_cost = round(float(np.sum(costs_per_req)), 6)

    # Revision distribution
    rev_0 = sum(1 for r in revisions_list if r == 0)
    rev_1 = sum(1 for r in revisions_list if r == 1)
    rev_2 = sum(1 for r in revisions_list if r >= 2)
    n_total = len(revisions_list)

    results = {
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit_hash(),
        "sample_size": len(dataset),
        "latency_ms": {
            "p50_total": round(p50_total, 2),
            "p95_total": round(p95_total, 2),
            "p50_by_step": p50_by_step,
            "p95_by_step": p95_by_step,
        },
        "throughput": {
            "mean_tokens_per_sec": mean_tokens_per_sec,
        },
        "cost_usd": {
            "mean_per_request": mean_cost,
            "total_batch_cost": total_cost,
        },
        "revision_distribution": {
            "0_revisions": {
                "count": rev_0,
                "percentage": round((rev_0 / n_total) * 100.0, 2),
            },
            "1_revision": {
                "count": rev_1,
                "percentage": round((rev_1 / n_total) * 100.0, 2),
            },
            "2_or_more_revisions": {
                "count": rev_2,
                "percentage": round((rev_2 / n_total) * 100.0, 2),
            },
        },
    }

    # 4. Save JSON Output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # 5. Display Clean Terminal Table (ASCII safe)
    table = Table(
        title="LLM-Native Metrics & Observability Benchmark",
        header_style="bold magenta",
    )
    table.add_column("Telemetry Dimension", style="cyan", width=28)
    table.add_column("Benchmark Value", style="bold green", width=18)
    table.add_column("Operational Meaning / Engineering Context", style="dim", width=36)

    table.add_row(
        "Total Latency p50",
        f"{p50_total:.1f} ms",
        "Median end-to-end multi-agent resolution",
    )
    table.add_row(
        "Total Latency p95",
        f"{p95_total:.1f} ms",
        "Tail latency including reflection loops",
    )
    table.add_row(
        "Triage Step p50",
        f"{p50_by_step.get('triage', 0.0):.1f} ms",
        "Intent classification and risk gates",
    )
    table.add_row(
        "Retrieval Step p50",
        f"{p50_by_step.get('retrieval', 0.0):.1f} ms",
        "Dense vector similarity search (pgvector)",
    )
    table.add_row(
        "Draft Step p50",
        f"{p50_by_step.get('draft', 0.0):.1f} ms",
        "Grounded LLM synthesis with citations",
    )
    table.add_row(
        "PolicyGuard Step p50",
        f"{p50_by_step.get('policy_guard', 0.0):.1f} ms",
        "Deterministic URL allowlist & PII filter",
    )
    table.add_row(
        "Critic Step p50",
        f"{p50_by_step.get('critic', 0.0):.1f} ms",
        "Multi-dimensional QA rubric grading",
    )
    table.add_row(
        "Throughput (tokens/sec)",
        f"{mean_tokens_per_sec:.1f} tok/s",
        "Average generative drafting velocity",
    )
    table.add_row(
        "Cost per Request",
        f"${mean_cost:.6f}",
        "Deterministic token pricing model",
    )
    table.add_row(
        "0 Revisions (1-Pass)",
        f"{(rev_0 / n_total) * 100:.1f}%",
        "Direct approval on initial synthesis",
    )
    table.add_row(
        "1 Revision",
        f"{(rev_1 / n_total) * 100:.1f}%",
        "Corrected via CriticAgent feedback",
    )
    table.add_row(
        "2+ Revisions",
        f"{(rev_2 / n_total) * 100:.1f}%",
        "Boundary retries / escalated safety cases",
    )

    console.print(table)
    console.print(f"\n[green][OK][/green] Benchmark results saved to: [dim]{output_path}[/dim]\n")
    return results


def main():
    parser = argparse.ArgumentParser(description="LLM-Native Latency and Cost Evaluator")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of queries to benchmark (default: 100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUT_FILE),
        help="Destination JSON file",
    )
    args = parser.parse_args()

    run_latency_cost_eval(
        sample_size=args.sample_size,
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    main()
