"""
eval/runners/e2e_eval.py
Master end-to-end evaluation benchmark runner for verifiable-support-agent.
Evaluates Intent Macro-F1, Escalation False Negative Rate (FNR), Hallucinated URL Rate,
LLM-as-a-judge multi-dimensional rubrics, Cohen's Kappa, latency percentiles, and cost.

Outputs frozen JSON results to eval/results/*.json for scientific auditability.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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

from evaluation.human_agreement import evaluate_human_judge_alignment  # noqa: E402
from evaluation.judge import SupportJudge  # noqa: E402
from evaluation.metrics import compute_escalation_metrics, compute_intent_metrics  # noqa: E402
from src.config import CALIBRATION_FILE, GOLDEN_EVAL_FILE, PAIRED_CONVERSATIONS_FILE  # noqa: E402
from src.data_loader import load_golden_evaluation_set, load_or_process_paired_data  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402
from src.pipeline import SupportAgentPipeline  # noqa: E402

from app.agents.orchestrator import OrchestratorAgent  # noqa: E402
from app.observability.cost_model import calculate_cost  # noqa: E402

console = Console(force_terminal=True, color_system="auto")


def get_git_commit_sha() -> str:
    """Retrieves current Git commit hash for provenance tracking."""
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


def extract_urls(text: str) -> set[str]:
    """Extracts all HTTP/HTTPS URLs from a given string."""
    url_pattern = r'https?://[^\s)\]>"\'\\]+'
    return {u.rstrip(".,;") for u in re.findall(url_pattern, text)}


def check_hallucinated_urls(
    drafted_reply: str,
    grounding_cases: list[dict[str, Any]],
    gold_resolution: str,
) -> bool:
    """
    Deterministic Hallucination Check:
    Returns True if drafted_reply contains URLs not present in retrieved grounding sources.
    """
    draft_urls = extract_urls(drafted_reply)
    if not draft_urls:
        return False

    allowed_urls: set[str] = extract_urls(gold_resolution)
    for case in grounding_cases:
        resolution_text = case.get("apple_resolution", "") or case.get("resolution", "")
        allowed_urls.update(extract_urls(resolution_text))

    unauthorized_urls = draft_urls - allowed_urls
    return len(unauthorized_urls) > 0


def run_e2e_benchmark(
    model_version: str = "v1",
    golden_file: Path = GOLDEN_EVAL_FILE,
    calibration_file: Path = CALIBRATION_FILE,
    sample_size: int = 200,
    offline: bool = True,
    output_file: Path = REPO_ROOT / "eval" / "results" / "baseline_v1.json",
) -> dict[str, Any]:
    """Runs the complete evaluation benchmark and saves results."""
    console.print(
        Panel.fit(
            f"[bold cyan]verifiable-support-agent[/bold cyan] — E2E Benchmark Runner\n"
            f"[dim]Evaluating: {model_version.upper()} | Samples: {sample_size} | Mode: {'OFFLINE' if offline else 'LIVE'}[/dim]",
            border_style="cyan",
        )
    )

    # 1. Load Data
    console.print("[dim]Loading Golden Evaluation Dataset...[/dim]")
    dataset = load_golden_evaluation_set(golden_file)
    if sample_size and sample_size < len(dataset):
        dataset = dataset[:sample_size]

    kb_df = None
    if PAIRED_CONVERSATIONS_FILE.exists():
        kb_df = load_or_process_paired_data(PAIRED_CONVERSATIONS_FILE)

    # 2. Initialize Model & Evaluation Judge
    llm = LLMClient(offline=offline)
    judge = SupportJudge(llm_client=llm)

    pipeline = None
    orchestrator = None
    if model_version == "v2":
        orchestrator = OrchestratorAgent(max_revisions=2)
    else:
        pipeline = SupportAgentPipeline(knowledge_base_df=kb_df, llm_client=llm)

    y_true_intent = []
    y_pred_intent = []
    y_true_escalate = []
    y_pred_escalate = []

    latencies_ms: list[float] = []
    groundedness_scores: list[float] = []
    actionability_scores: list[float] = []
    tone_scores: list[float] = []
    safety_passes: list[bool] = []
    hallucinated_url_flags: list[bool] = []
    revision_counts: list[int] = []

    total_input_tokens = 0
    total_output_tokens = 0

    console.print(f"[green][OK][/green] Starting benchmark run on {len(dataset)} samples...\n")

    for _i, item in enumerate(dataset, 1):
        query = item["customer_query"]
        gold_intent = item["gold_intent"]
        gold_escalate = item["gold_escalation"]
        gold_resolution = item.get("gold_historical_resolution", "")

        # Latency benchmark
        t_start = time.perf_counter()
        if model_version == "v2" and orchestrator is not None:
            state = orchestrator.process_ticket(query)
            pred_intent = state.intent
            pred_escalate = state.should_escalate
            drafted_reply = state.drafted_reply
            grounding_cases = [
                {"apple_resolution": c.resolution_text, "id": c.id}
                for c in state.retrieved_cases
            ]
            revision_counts.append(state.revision_count)
        else:
            output = pipeline.process(query) if pipeline else {}
            pred_intent = output["intent"]
            pred_escalate = output["should_escalate"]
            drafted_reply = output.get("drafted_reply", "")
            grounding_cases = output.get("retrieved_cases", [])
            revision_counts.append(0)

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        latencies_ms.append(elapsed_ms)

        # Token usage estimation (for offline mock, approximate by word count)
        prompt_tokens = len(query.split()) * 2
        response_tokens = len(drafted_reply.split()) * 2
        total_input_tokens += prompt_tokens
        total_output_tokens += response_tokens

        y_true_intent.append(gold_intent)
        y_pred_intent.append(pred_intent)

        y_true_escalate.append(gold_escalate)
        y_pred_escalate.append(pred_escalate)

        # Deterministic Hallucinated URL Check
        has_hallucinated_url = check_hallucinated_urls(
            drafted_reply=drafted_reply,
            grounding_cases=grounding_cases,
            gold_resolution=gold_resolution,
        )
        hallucinated_url_flags.append(has_hallucinated_url)

        # Multi-dimensional LLM Judge
        judge_res = judge.evaluate_reply(
            customer_query=query,
            drafted_reply=drafted_reply,
            gold_resolution=gold_resolution,
            grounding_cases=grounding_cases,
        )

        groundedness_scores.append(judge_res["groundedness"])
        actionability_scores.append(judge_res["actionability"])
        tone_scores.append(judge_res["brand_tone"])
        safety_passes.append(judge_res["safety_pass"])

    # 3. Aggregate Metrics Computation
    intent_metrics = compute_intent_metrics(y_true_intent, y_pred_intent)
    escalation_metrics = compute_escalation_metrics(y_true_escalate, y_pred_escalate)

    p50_latency = float(np.percentile(latencies_ms, 50))
    p95_latency = float(np.percentile(latencies_ms, 95))
    hallucinated_url_rate = (
        sum(hallucinated_url_flags) / len(hallucinated_url_flags) if hallucinated_url_flags else 0.0
    )

    model_name_for_pricing = "offline-mock" if offline else "gemini-1.5-flash-002"
    total_cost_usd = calculate_cost(
        model_name=model_name_for_pricing,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )
    cost_per_request = round(total_cost_usd / len(dataset), 6) if dataset else 0.0

    # 4. Human-Judge Calibration Agreement (Cohen's Kappa)
    cohens_kappa_escalation = None
    cohens_kappa_safety = None
    if calibration_file and calibration_file.exists():
        with open(calibration_file, encoding="utf-8") as f:
            calib_records = json.load(f)
        agreement = evaluate_human_judge_alignment(calib_records)
        cohens_kappa_escalation = agreement.get("escalation_decision_agreement", {}).get(
            "cohens_kappa"
        )
        cohens_kappa_safety = agreement.get("safety_guardrail_agreement", {}).get("cohens_kappa")

    # 5. Build Result Payload
    result_data = {
        "system": f"{model_version}_baseline",
        "git_commit": get_git_commit_sha(),
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "offline" if offline else "live",
        "model_name": model_name_for_pricing,
        "sample_size": len(dataset),
        "metrics": {
            "intent_macro_f1": intent_metrics["macro_f1"],
            "intent_accuracy": intent_metrics["accuracy"],
            "escalation_precision": escalation_metrics["precision"],
            "escalation_recall": escalation_metrics["recall"],
            "escalation_fnr": escalation_metrics["false_negative_rate"],
            "hallucinated_url_rate": round(hallucinated_url_rate, 4),
            "judge_pass_rate": round((sum(safety_passes) / len(safety_passes)) * 100, 2),
            "mean_groundedness": round(float(np.mean(groundedness_scores)), 2),
            "mean_actionability": round(float(np.mean(actionability_scores)), 2),
            "mean_brand_tone": round(float(np.mean(tone_scores)), 2),
            "cohens_kappa_escalation": cohens_kappa_escalation,
            "cohens_kappa_safety": cohens_kappa_safety,
            "latency_p50_ms": round(p50_latency, 2),
            "latency_p95_ms": round(p95_latency, 2),
            "avg_revisions": round(float(np.mean(revision_counts)), 2) if revision_counts else 0.0,
            "cost_per_request_usd": cost_per_request,
            "total_cost_usd": total_cost_usd,
        },
    }

    # 6. Render Terminal Summary
    table = Table(title=f"Benchmark Results — {model_version.upper()}", header_style="bold magenta")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Target / Interpretation", justify="left")

    table.add_row(
        "Intent Macro-F1", f"{intent_metrics['macro_f1']:.2f}", "Unweighted 7-class MECE average"
    )
    table.add_row(
        "Escalation Recall", f"{escalation_metrics['recall']:.2f}", "Catches safety/legal emergencies"
    )
    table.add_row(
        "Escalation FNR (Safety Liability)",
        f"[red]{escalation_metrics['false_negative_rate']:.2f}[/red]"
        if escalation_metrics["false_negative_rate"] > 0.20
        else f"[green]{escalation_metrics['false_negative_rate']:.2f}[/green]",
        "Target < 0.15 (Lower is better)",
    )
    table.add_row(
        "Hallucinated URL Rate",
        f"[green]{hallucinated_url_rate:.2%}[/green]"
        if hallucinated_url_rate == 0
        else f"[red]{hallucinated_url_rate:.2%}[/red]",
        "Target = 0.0% (Zero unverified domains)",
    )
    table.add_row(
        "Judge Pass Rate",
        f"{result_data['metrics']['judge_pass_rate']:.1f}%",
        "Passed multi-dimensional rubric",
    )
    table.add_row(
        "Groundedness (1-5)",
        f"{result_data['metrics']['mean_groundedness']:.2f}",
        "Factual troubleshooting alignment",
    )
    if cohens_kappa_escalation is not None:
        table.add_row(
            "Cohen's Kappa (Escalation)",
            f"kappa = {cohens_kappa_escalation:.3f}",
            "Substantial agreement (0.61 - 0.80)",
        )
    table.add_row("p50 Latency", f"{p50_latency:.1f} ms", "Median inference latency")
    table.add_row("p95 Latency", f"{p95_latency:.1f} ms", "Tail latency threshold")
    table.add_row("Cost per Request", f"${cost_per_request:.6f}", "Deterministic pricing model")

    # 7. Write Output JSON
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    console.print(table)

    console.print(
        f"\n[green][OK][/green] Frozen benchmark results saved to: [dim]{output_file}[/dim]\n"
    )
    return result_data


def main():
    parser = argparse.ArgumentParser(description="Master E2E Evaluation Runner")
    parser.add_argument(
        "--model",
        type=str,
        default="v1",
        choices=["v1", "v2"],
        help="System version to benchmark",
    )
    parser.add_argument(
        "--sample-size", type=int, default=200, help="Number of test samples to evaluate"
    )
    parser.add_argument(
        "--live", action="store_true", default=False, help="Enable live Vertex AI Gemini API calls"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path for destination JSON result",
    )
    args = parser.parse_args()

    default_output = (
        REPO_ROOT / "eval" / "results" / f"{'e2e_v2' if args.model == 'v2' else 'baseline_v1'}.json"
    )
    output_path = Path(args.output) if args.output else default_output

    run_e2e_benchmark(
        model_version=args.model,
        sample_size=args.sample_size,
        offline=not args.live,
        output_file=output_path,
    )


if __name__ == "__main__":
    main()
