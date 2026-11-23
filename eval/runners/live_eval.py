"""
eval/runners/live_eval.py
Live model evaluation benchmark using Google AI Studio API key.
Runs a 30-sample stratified slice of the golden evaluation set with per-call rate limiting,
exponential backoff, Wilson 95% confidence intervals, and full latency/token/cost telemetry.

Writes to eval/results/live_sample.json.
"""

import argparse
import collections
import json
import math
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Load local environment if available
load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from evaluation.judge import SupportJudge  # noqa: E402
from src.config import GOLDEN_EVAL_FILE  # noqa: E402
from src.data_loader import load_golden_evaluation_set  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402

from app.agents.critic_agent import CriticAgent  # noqa: E402
from app.agents.draft_agent import DraftAgent  # noqa: E402
from app.agents.orchestrator import OrchestratorAgent  # noqa: E402
from app.config import DEFAULT_LIVE_MODEL  # noqa: E402
from app.observability.cost_model import PRICING_REGISTRY  # noqa: E402

console = Console()
OUTPUT_FILE = REPO_ROOT / "eval" / "results" / "live_sample.json"


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


def wilson_interval(k: int, n: int) -> dict[str, float]:
    """Computes Wilson score 95% confidence interval for binomial proportions."""
    if n == 0:
        return {"value": 0.0, "ci_lower": 0.0, "ci_upper": 0.0}
    p = k / n
    z = 1.95996  # 95% confidence
    denominator = 1.0 + (z**2) / n
    centre = p + (z**2) / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) + (z**2) / (4.0 * n)) / n)
    lower = max(0.0, (centre - spread) / denominator)
    upper = min(1.0, (centre + spread) / denominator)
    return {
        "value": round(p * 100.0, 1),
        "ci_lower": round(lower * 100.0, 1),
        "ci_upper": round(upper * 100.0, 1),
    }


def select_stratified_sample(dataset: list[dict], target_n: int = 30) -> list[dict]:
    """Selects target_n samples stratified proportionally across 7 MECE intent categories."""
    by_intent = collections.defaultdict(list)
    for item in dataset:
        by_intent[item.get("gold_intent", "OTHER")].append(item)

    selected = []
    # Round-robin picking from each intent class until target_n is reached
    intent_keys = sorted(by_intent.keys())
    idx = 0
    while len(selected) < target_n:
        for k in intent_keys:
            if idx < len(by_intent[k]) and len(selected) < target_n:
                selected.append(by_intent[k][idx])
        idx += 1
    return selected


def run_live_eval(sample_size: int = 30, rate_limit_delay: float = 2.0):
    api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        console.print("[yellow]Warning: GEMINI_API_KEY is not set. Skipping live evaluation.[/yellow]")
        return

    # Allow environment override for model or fallback to 3.5 if 3.8 has capacity spikes
    chosen_model = os.getenv("GEMINI_MODEL", DEFAULT_LIVE_MODEL)
    console.print(
        f"[bold cyan]Starting Live Model Evaluation ({sample_size} stratified samples) using {chosen_model}...[/bold cyan]"
    )

    data = load_golden_evaluation_set(GOLDEN_EVAL_FILE)
    samples = select_stratified_sample(data, target_n=sample_size)

    # Initialize live LLM client
    live_llm = LLMClient(provider="gemini", offline=False)
    draft_agent = DraftAgent(llm_client=live_llm)
    critic_agent = CriticAgent(judge=SupportJudge(llm_client=live_llm))
    orchestrator = OrchestratorAgent(
        draft_agent=draft_agent,
        critic_agent=critic_agent,
    )

    latencies: list[float] = []
    step_latencies: dict[str, list[float]] = collections.defaultdict(list)
    costs: list[float] = []
    in_tokens: list[int] = []
    out_tokens: list[int] = []
    revisions: list[int] = []

    passed_judge_count = 0
    hallucinated_urls_count = 0
    escalation_true_pos = 0
    escalation_false_neg = 0
    escalation_false_pos = 0
    intent_correct_count = 0

    for i, s in enumerate(samples):
        query = s.get("customer_query", "")
        gold_intent = s.get("gold_intent", "")
        gold_esc = s.get("gold_escalation", False)

        console.print(f"[{i + 1}/{len(samples)}] Processing query: {query[:45]}...")
        t0 = time.perf_counter()
        state = None
        max_attempts = 4

        for attempt in range(max_attempts):
            try:
                state = orchestrator.process_ticket(query)
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "503" in err_str or "ResourceExhausted" in err_str or "UNAVAILABLE" in err_str:
                    backoff = rate_limit_delay * (2 ** (attempt + 1))
                    console.print(f"[yellow]Spike or rate limit on sample {i + 1} ({err_str[:40]}...). Backing off {backoff:.1f}s...[/yellow]")
                    time.sleep(backoff)
                else:
                    console.print(f"[red]Error on sample {i + 1}: {e}[/red]")
                    break

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if state is not None:
            console.print(f"[{i + 1}/{len(samples)}] Done ({elapsed_ms:.0f} ms) | Esc: {state.should_escalate} | Revs: {state.revision_count} | Judge: {state.critic_verdict.passed if state.critic_verdict else 'N/A'}")
            latencies.append(elapsed_ms)
            costs.append(state.total_cost_usd)
            revisions.append(state.revision_count)

            # Record step timings
            for step_k, step_v in state.step_timings_ms.items():
                step_latencies[step_k].append(step_v)

            # Record tokens
            step_in = sum(v for k, v in state.tokens_used.items() if "_input" in k)
            step_out = sum(v for k, v in state.tokens_used.items() if "_output" in k)
            in_tokens.append(step_in)
            out_tokens.append(step_out)

            # Accuracy & Safety Tracking
            if state.intent == gold_intent:
                intent_correct_count += 1

            if gold_esc and state.should_escalate:
                escalation_true_pos += 1
            elif gold_esc and not state.should_escalate:
                escalation_false_neg += 1
            elif not gold_esc and state.should_escalate:
                escalation_false_pos += 1

            if state.critic_verdict and state.critic_verdict.passed:
                passed_judge_count += 1
            if not state.policy_verdict.passed and "URL" in state.policy_verdict.reason_code:
                hallucinated_urls_count += 1

        time.sleep(rate_limit_delay)

    if not latencies:
        console.print("[red]No samples processed successfully.[/red]")
        return

    n = len(latencies)
    gold_esc_total = escalation_true_pos + escalation_false_neg
    model_esc_pred = escalation_true_pos + escalation_false_pos

    esc_recall_wilson = wilson_interval(escalation_true_pos, gold_esc_total) if gold_esc_total > 0 else {"value": 100.0, "ci_lower": 0.0, "ci_upper": 100.0}
    esc_prec_wilson = wilson_interval(escalation_true_pos, model_esc_pred) if model_esc_pred > 0 else {"value": 100.0, "ci_lower": 0.0, "ci_upper": 100.0}
    judge_pass_wilson = wilson_interval(passed_judge_count, n)
    url_halluc_wilson = wilson_interval(hallucinated_urls_count, n)
    intent_acc_wilson = wilson_interval(intent_correct_count, n)

    # Revision distribution
    rev_counts = collections.Counter(revisions)
    share_0_rev = round((rev_counts[0] / n) * 100.0, 1)
    share_1_rev = round((rev_counts[1] / n) * 100.0, 1)
    share_2_rev = round((rev_counts[2] / n) * 100.0, 1)

    # Tokens per second
    total_out_tokens = sum(out_tokens)
    total_time_sec = sum(latencies) / 1000.0
    mean_tokens_per_sec = round(total_out_tokens / total_time_sec, 2) if total_time_sec > 0 else 0.0

    p50_total = float(np.percentile(latencies, 50))
    p95_total = float(np.percentile(latencies, 95))

    # Pricing reference
    pricing_info = PRICING_REGISTRY.get(chosen_model) or PRICING_REGISTRY.get("gemini-1.5-flash")
    price_source = pricing_info.source_url if pricing_info else "https://ai.google.dev/pricing"
    price_effective = pricing_info.effective_date if pricing_info else "2026-11-23"

    payload = {
        "benchmark": "live_model_evaluation",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit_sha(),
        "sample_size": n,
        "sample_size_note": "Sample size n=30 is small; reported confidence intervals reflect sampling uncertainty.",
        "model_name": chosen_model,
        "model_architecture_note": "Drafter and Judge agents both use the Gemini model family.",
        "pricing_metadata": {
            "source_url": price_source,
            "effective_date": price_effective,
        },
        "rates": {
            "judge_pass_rate": judge_pass_wilson,
            "escalation_recall": esc_recall_wilson,
            "escalation_precision": esc_prec_wilson,
            "hallucinated_url_rate": url_halluc_wilson,
            "intent_accuracy": intent_acc_wilson,
        },
        "latency_ms": {
            "p50_total": round(p50_total, 2),
            "p95_total": round(p95_total, 2),
            "p50_by_step": {
                k: round(float(np.percentile(v, 50)), 2) for k, v in step_latencies.items() if v
            },
            "p95_by_step": {
                k: round(float(np.percentile(v, 95)), 2) for k, v in step_latencies.items() if v
            },
        },
        "tokens": {
            "mean_input_tokens": round(float(np.mean(in_tokens)), 1) if in_tokens else 0.0,
            "mean_output_tokens": round(float(np.mean(out_tokens)), 1) if out_tokens else 0.0,
            "tokens_per_second": mean_tokens_per_sec,
        },
        "cost_usd": {
            "mean_per_request": round(float(np.mean(costs)), 6) if costs else 0.0,
            "total_batch_cost": round(float(np.sum(costs)), 6) if costs else 0.0,
        },
        "revision_distribution": {
            "0_revisions_pct": share_0_rev,
            "1_revision_pct": share_1_rev,
            "2_or_more_revisions_pct": share_2_rev,
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    console.print(f"[bold green]Saved live evaluation results to {OUTPUT_FILE}[/bold green]")

    # Terminal Summary Table
    table = Table(title=f"Live Model Evaluation (n={n}, Model: {chosen_model})")
    table.add_column("Dimension", style="cyan")
    table.add_column("Value", style="bold green")
    table.add_column("Wilson 95% Confidence Interval", style="dim")

    table.add_row(
        "Judge Pass Rate",
        f"{judge_pass_wilson['value']}%",
        f"[{judge_pass_wilson['ci_lower']}%, {judge_pass_wilson['ci_upper']}%]",
    )
    table.add_row(
        "Escalation Recall",
        f"{esc_recall_wilson['value']}%",
        f"[{esc_recall_wilson['ci_lower']}%, {esc_recall_wilson['ci_upper']}%]",
    )
    table.add_row(
        "Escalation Precision",
        f"{esc_prec_wilson['value']}%",
        f"[{esc_prec_wilson['ci_lower']}%, {esc_prec_wilson['ci_upper']}%]",
    )
    table.add_row(
        "Hallucinated URL Rate",
        f"{url_halluc_wilson['value']}%",
        f"[{url_halluc_wilson['ci_lower']}%, {url_halluc_wilson['ci_upper']}%]",
    )
    table.add_row("Median Total Latency (p50)", f"{p50_total:.1f} ms", "Live Network Hop Included")
    table.add_row("Tail Total Latency (p95)", f"{p95_total:.1f} ms", "Live Network Hop Included")
    table.add_row("Mean Cost per Request", f"${np.mean(costs):.6f}", f"Source: {price_source}")
    table.add_row(
        "Revisions (0 / 1 / 2+)",
        f"{share_0_rev}% / {share_1_rev}% / {share_2_rev}%",
        "Bounded Retry Loop",
    )
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Run live evaluation against Gemini API")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()
    run_live_eval(sample_size=args.samples, rate_limit_delay=args.delay)


if __name__ == "__main__":
    main()
