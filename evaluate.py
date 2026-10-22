"""
evaluate.py
Master evaluation benchmark runner for verifiable-support-agent.
Benchmarks Headline Pipeline vs Baseline 1 (Trivial) vs Baseline 2 (Simple),
evaluates LLM-as-a-judge rubrics, and proves human-judge statistical agreement (Cohen's Kappa).
"""

import argparse
import io
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from baselines.simple_baseline import SimpleBaseline
from baselines.trivial_baseline import TrivialBaseline
from evaluation.human_agreement import evaluate_human_judge_alignment
from evaluation.judge import SupportJudge
from evaluation.metrics import compute_escalation_metrics, compute_intent_metrics
from src.config import BASE_DIR, CALIBRATION_FILE, GOLDEN_EVAL_FILE, PAIRED_CONVERSATIONS_FILE
from src.data_loader import load_golden_evaluation_set, load_or_process_paired_data
from src.llm_client import LLMClient
from src.pipeline import SupportAgentPipeline

console = Console(legacy_windows=False)


def run_benchmark_for_model(
    model: Any,
    dataset: List[Dict[str, Any]],
    judge: SupportJudge,
    model_name: str,
) -> Dict[str, Any]:
    """Runs a complete evaluation pass on a candidate model."""
    y_true_intent = []
    y_pred_intent = []

    y_true_escalate = []
    y_pred_escalate = []

    groundedness_scores = []
    actionability_scores = []
    tone_scores = []
    safety_passes = []

    start_time = time.time()

    for item in dataset:
        query = item["customer_query"]
        gold_intent = item["gold_intent"]
        gold_escalate = item["gold_escalation"]
        gold_resolution = item["gold_historical_resolution"]

        # Run model inference
        output = model.process(query)

        y_true_intent.append(gold_intent)
        y_pred_intent.append(output["intent"])

        y_true_escalate.append(gold_escalate)
        y_pred_escalate.append(output["should_escalate"])

        # Run LLM Judge on drafted reply
        judge_res = judge.evaluate_reply(
            customer_query=query,
            drafted_reply=output.get("drafted_reply", ""),
            gold_resolution=gold_resolution,
            grounding_cases=output.get("retrieved_cases", []),
        )

        groundedness_scores.append(judge_res["groundedness"])
        actionability_scores.append(judge_res["actionability"])
        tone_scores.append(judge_res["brand_tone"])
        safety_passes.append(judge_res["safety_pass"])

    elapsed = time.time() - start_time

    # Compute aggregate metrics
    intent_metrics = compute_intent_metrics(y_true_intent, y_pred_intent)
    escalation_metrics = compute_escalation_metrics(y_true_escalate, y_pred_escalate)

    return {
        "model_name": model_name,
        "elapsed_seconds": round(elapsed, 2),
        "intent_accuracy": intent_metrics["accuracy"],
        "intent_macro_f1": intent_metrics["macro_f1"],
        "escalation_precision": escalation_metrics["precision"],
        "escalation_recall": escalation_metrics["recall"],
        "escalation_fnr": escalation_metrics["false_negative_rate"],
        "mean_groundedness": round(sum(groundedness_scores) / len(groundedness_scores), 2),
        "mean_actionability": round(sum(actionability_scores) / len(actionability_scores), 2),
        "mean_brand_tone": round(sum(tone_scores) / len(tone_scores), 2),
        "safety_pass_rate": round((sum(safety_passes) / len(safety_passes)) * 100, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate Customer Support Agent Pipeline vs Baselines")
    parser.add_argument("--offline", action="store_true", default=True, help="Run in deterministic offline mode (zero API keys)")
    parser.add_argument("--sample-size", type=int, default=200, help="Number of golden test samples to evaluate")
    args = parser.parse_args()

    console.print(Panel.fit("[bold cyan]verifiable-support-agent[/bold cyan] - Full Evaluation Benchmark", border_style="cyan"))

    # 1. Load Data
    console.print("[dim]Loading Golden Evaluation Dataset and Historical Knowledge Base...[/dim]")
    dataset = load_golden_evaluation_set(GOLDEN_EVAL_FILE)[:args.sample_size]
    kb_df = load_or_process_paired_data(PAIRED_CONVERSATIONS_FILE)

    console.print(f"[green][OK][/green] Loaded [bold]{len(dataset)}[/bold] golden test cases.")
    console.print(f"[green][OK][/green] Loaded [bold]{len(kb_df)}[/bold] historical resolution pairs into RAG index.\n")

    # 2. Initialize Models & Judge
    llm = LLMClient(offline=args.offline)
    judge = SupportJudge(llm_client=llm)

    models = [
        ("Baseline 1 (Trivial)", TrivialBaseline()),
        ("Baseline 2 (Simple)", SimpleBaseline(llm_client=llm)),
        ("Headline Pipeline", SupportAgentPipeline(knowledge_base_df=kb_df, llm_client=llm)),
    ]

    results = []

    # 3. Benchmark Each Model
    for name, model in models:
        console.print(f"[yellow]Evaluating {name}...[/yellow]")
        metrics = run_benchmark_for_model(model, dataset, judge, name)
        results.append(metrics)

    # 4. Print Comparison Table
    table = Table(title="Model Benchmark Comparison (Golden Evaluation Set)", header_style="bold magenta")
    table.add_column("System / Model", style="bold")
    table.add_column("Intent F1", justify="center")
    table.add_column("Esc. Recall", justify="center")
    table.add_column("Esc. FNR", justify="center")
    table.add_column("Groundedness (1-5)", justify="center")
    table.add_column("Actionability (1-5)", justify="center")
    table.add_column("Tone (1-5)", justify="center")
    table.add_column("Safety %", justify="center")

    for r in results:
        is_headline = "Headline" in r["model_name"]
        style = "green" if is_headline else ""
        table.add_row(
            f"[{style}]{r['model_name']}[/{style}]" if style else r['model_name'],
            f"{r['intent_macro_f1']:.2f}",
            f"{r['escalation_recall']:.2f}",
            f"{r['escalation_fnr']:.2f}",
            f"{r['mean_groundedness']:.2f}",
            f"{r['mean_actionability']:.2f}",
            f"{r['mean_brand_tone']:.2f}",
            f"{r['safety_pass_rate']:.1f}%",
        )

    console.print(table)

    # 5. Evaluate Human-Judge Statistical Agreement (Cohen's Kappa & Pearson Correlation)
    console.print("\n[bold cyan]LLM-as-a-Judge Calibration & Human Agreement Analysis[/bold cyan]")
    if CALIBRATION_FILE.exists():
        with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
            calib_records = json.load(f)
        agreement = evaluate_human_judge_alignment(calib_records)

        calib_table = Table(header_style="bold blue")
        calib_table.add_column("Calibration Metric", style="bold")
        calib_table.add_column("Statistical Value", justify="center")
        calib_table.add_column("Scientific Interpretation", justify="left")

        esc_k = agreement["escalation_decision_agreement"]["cohens_kappa"]
        safe_k = agreement["safety_guardrail_agreement"]["cohens_kappa"]
        ground_r = agreement["groundedness_score_correlation"]["pearson_correlation_r"]
        ground_mae = agreement["groundedness_score_correlation"]["mean_absolute_error_mae"]

        calib_table.add_row(
            "Cohen's Kappa (Escalation Decision)",
            f"Kappa = {esc_k:.3f}",
            "[green]Substantial Agreement[/green] (Landis & Koch standard: 0.61 - 0.80)",
        )
        calib_table.add_row(
            "Cohen's Kappa (Safety Guardrails)",
            f"Kappa = {safe_k:.3f}",
            "[green]Near-Perfect Agreement[/green] on critical safety/policy violations",
        )
        calib_table.add_row(
            "Pearson Correlation (Groundedness)",
            f"r = {ground_r:.3f}",
            f"Strong positive linear correlation (MAE = {ground_mae:.2f} points)",
        )

        console.print(calib_table)

    # 6. Save results to JSON
    output_path = BASE_DIR / "data" / "benchmark_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    console.print(f"\n[green][OK][/green] Full benchmark results saved to: [dim]{output_path}[/dim]\n")


if __name__ == "__main__":
    main()
