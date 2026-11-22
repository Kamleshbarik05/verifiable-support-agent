"""
eval/runners/compare_eval.py
Master comparative benchmark runner: v1 Baseline vs. v2 ADK Multi-Agent System.
Parses eval/results/baseline_v1.json and eval/results/e2e_v2.json to generate
an audited, scientifically honest side-by-side comparison table.
"""

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_RESULTS_FILE = REPO_ROOT / "eval" / "results" / "baseline_v1.json"
V2_RESULTS_FILE = REPO_ROOT / "eval" / "results" / "e2e_v2.json"

console = Console(force_terminal=True, color_system="auto")


def format_delta(diff: float, is_lower_better: bool = False, is_percentage: bool = False) -> str:
    """Formats numeric differences with visual sentiment coloring."""
    if is_lower_better:
        color = "green" if diff < 0 else ("red" if diff > 0 else "dim")
    else:
        color = "green" if diff > 0 else ("red" if diff < 0 else "dim")

    if is_percentage:
        return f"[{color}]{diff:+.2%}[/{color}]"
    return f"[{color}]{diff:+.3f}[/{color}]"


def run_comparison(
    v1_path: Path = V1_RESULTS_FILE,
    v2_path: Path = V2_RESULTS_FILE,
):
    console.print(
        Panel.fit(
            "[bold cyan]Verifiable Support Agent - Benchmark Audit[/bold cyan]\n"
            "[dim]v1 Monolithic Baseline vs. v2 ADK Multi-Agent Architecture (200 Golden Samples)[/dim]",
            border_style="cyan",
        )
    )

    if not v1_path.exists():
        console.print(f"[red]Error:[/red] v1 baseline results not found at {v1_path}. Run `make eval-baseline` first.")
        return

    if not v2_path.exists():
        console.print(f"[red]Error:[/red] v2 results not found at {v2_path}. Run `python eval/runners/e2e_eval.py --model v2` first.")
        return

    with open(v1_path, encoding="utf-8") as f:
        v1_data = json.load(f)

    with open(v2_path, encoding="utf-8") as f:
        v2_data = json.load(f)

    v1_m = v1_data["metrics"]
    v2_m = v2_data["metrics"]

    table = Table(title="System Comparison: v1 Baseline vs. v2 Multi-Agent", header_style="bold magenta")
    table.add_column("Evaluation Dimension", style="bold")
    table.add_column("v1 Baseline", justify="right")
    table.add_column("v2 Multi-Agent", justify="right")
    table.add_column("Delta (v2 - v1)", justify="center")
    table.add_column("Engineering Analysis", justify="left")

    # 1. Intent Macro-F1
    d_f1 = v2_m["intent_macro_f1"] - v1_m["intent_macro_f1"]
    table.add_row(
        "Intent Macro-F1",
        f"{v1_m['intent_macro_f1']:.3f}",
        f"{v2_m['intent_macro_f1']:.3f}",
        format_delta(d_f1),
        "Unweighted 7-class MECE intent categorization",
    )

    # 2. Escalation Recall
    d_rec = v2_m["escalation_recall"] - v1_m["escalation_recall"]
    table.add_row(
        "Escalation Recall",
        f"{v1_m['escalation_recall']:.2%}",
        f"{v2_m['escalation_recall']:.2%}",
        format_delta(d_rec, is_percentage=True),
        "Captures safety, legal, and privacy emergencies",
    )

    # 3. Escalation FNR (Safety Liability)
    d_fnr = v2_m["escalation_fnr"] - v1_m["escalation_fnr"]
    table.add_row(
        "Escalation FNR (Safety Risk)",
        f"{v1_m['escalation_fnr']:.2%}",
        f"{v2_m['escalation_fnr']:.2%}",
        format_delta(d_fnr, is_lower_better=True, is_percentage=True),
        "Lower is better (Risk of missing emergency)",
    )

    # 4. Hallucinated URL Rate
    d_url = v2_m["hallucinated_url_rate"] - v1_m["hallucinated_url_rate"]
    table.add_row(
        "Hallucinated URL Rate",
        f"{v1_m['hallucinated_url_rate']:.2%}",
        f"{v2_m['hallucinated_url_rate']:.2%}",
        format_delta(d_url, is_lower_better=True, is_percentage=True),
        "Deterministic PolicyGuard enforcement",
    )

    # 5. Judge Pass Rate
    d_pass = (v2_m["judge_pass_rate"] - v1_m["judge_pass_rate"]) / 100.0
    table.add_row(
        "Judge Pass Rate",
        f"{v1_m['judge_pass_rate']:.1f}%",
        f"{v2_m['judge_pass_rate']:.1f}%",
        format_delta(d_pass, is_percentage=True),
        "Passed multi-dimensional QA rubric",
    )

    # 6. Mean Groundedness
    d_ground = v2_m["mean_groundedness"] - v1_m["mean_groundedness"]
    table.add_row(
        "Groundedness Score (1-5)",
        f"{v1_m['mean_groundedness']:.2f}",
        f"{v2_m['mean_groundedness']:.2f}",
        format_delta(d_ground),
        "Troubleshooting accuracy vs Apple precedents",
    )

    # 7. p50 Latency (ms)
    d_p50 = v2_m["latency_p50_ms"] - v1_m["latency_p50_ms"]
    table.add_row(
        "p50 Latency (ms)",
        f"{v1_m['latency_p50_ms']:.1f} ms",
        f"{v2_m['latency_p50_ms']:.1f} ms",
        f"[yellow]{d_p50:+.1f} ms[/yellow]" if d_p50 > 0 else f"[green]{d_p50:+.1f} ms[/green]",
        "Trade-off: multi-agent delegation overhead",
    )

    # 8. p95 Latency (ms)
    d_p95 = v2_m["latency_p95_ms"] - v1_m["latency_p95_ms"]
    table.add_row(
        "p95 Latency (ms)",
        f"{v1_m['latency_p95_ms']:.1f} ms",
        f"{v2_m['latency_p95_ms']:.1f} ms",
        f"[yellow]{d_p95:+.1f} ms[/yellow]" if d_p95 > 0 else f"[green]{d_p95:+.1f} ms[/green]",
        "Tail latency including reflection loops",
    )

    # 9. Cost per Request ($)
    table.add_row(
        "Cost per Request ($)",
        f"${v1_m.get('cost_per_request_usd', 0.0):.6f}",
        f"${v2_m.get('cost_per_request_usd', 0.0):.6f}",
        "~+$0.000",
        "Estimated via Vertex AI pricing model",
    )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Compare v1 Baseline vs. v2 Multi-Agent Benchmark")
    parser.add_argument("--v1", type=str, default=str(V1_RESULTS_FILE), help="Path to v1 baseline JSON")
    parser.add_argument("--v2", type=str, default=str(V2_RESULTS_FILE), help="Path to v2 results JSON")
    args = parser.parse_args()

    run_comparison(v1_path=Path(args.v1), v2_path=Path(args.v2))


if __name__ == "__main__":
    main()
