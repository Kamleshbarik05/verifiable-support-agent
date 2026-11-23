"""
eval/runners/live_eval.py
Live model evaluation benchmark using Google AI Studio API key.
Runs a 30-sample slice of the golden evaluation set with per-call rate limiting,
exponential backoff, and full latency/token/cost telemetry.

Writes to eval/results/live_sample.json.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

# Load local environment if available
load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.config import GOLDEN_EVAL_FILE  # noqa: E402
from src.data_loader import load_golden_evaluation_set  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402

from app.agents.critic_agent import CriticAgent  # noqa: E402
from app.agents.draft_agent import DraftAgent  # noqa: E402
from app.agents.orchestrator import OrchestratorAgent  # noqa: E402
from app.config import DEFAULT_LIVE_MODEL  # noqa: E402

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


def run_live_eval(sample_size: int = 30, rate_limit_delay: float = 2.0):
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        console.print("[yellow]Warning: GEMINI_API_KEY is not set. Skipping live evaluation.[/yellow]")
        return

    console.print(
        f"[bold cyan]Starting Live Model Evaluation ({sample_size} samples) using {DEFAULT_LIVE_MODEL}...[/bold cyan]"
    )

    data = load_golden_evaluation_set(str(GOLDEN_EVAL_FILE))
    samples = data[:sample_size]

    # Initialize live LLM client
    live_llm = LLMClient(provider="gemini", offline=False)
    draft_agent = DraftAgent(llm_client=live_llm)
    critic_agent = CriticAgent()
    orchestrator = OrchestratorAgent(
        draft_agent=draft_agent,
        critic_agent=critic_agent,
    )

    latencies: list[float] = []
    costs: list[float] = []
    revisions: list[int] = []
    passed_judge_count = 0
    hallucinated_urls_count = 0

    for i, s in enumerate(samples):
        query = s.get("customer_query", "")
        t0 = time.perf_counter()

        # Retry with backoff for rate limits
        max_attempts = 3
        state = None
        for attempt in range(max_attempts):
            try:
                state = orchestrator.process_ticket(query)
                break
            except Exception as e:
                if "429" in str(e) or "ResourceExhausted" in str(e):
                    backoff = rate_limit_delay * (2 ** (attempt + 1))
                    console.print(f"[yellow]Rate limit encountered. Backing off {backoff:.1f}s...[/yellow]")
                    time.sleep(backoff)
                else:
                    console.print(f"[red]Error on sample {i + 1}: {e}[/red]")
                    break

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if state is not None:
            latencies.append(elapsed_ms)
            costs.append(state.total_cost_usd)
            revisions.append(state.revision_count)
            if state.critic_verdict and state.critic_verdict.passed:
                passed_judge_count += 1
            if state.policy_violations:
                hallucinated_urls_count += 1

        time.sleep(rate_limit_delay)

    if not latencies:
        console.print("[red]No samples processed successfully.[/red]")
        return

    import numpy as np

    p50_lat = float(np.percentile(latencies, 50))
    p95_lat = float(np.percentile(latencies, 95))
    mean_cost = float(np.mean(costs)) if costs else 0.0
    judge_pass_rate = (passed_judge_count / len(latencies)) * 100.0
    hallucinated_rate = (hallucinated_urls_count / len(latencies)) * 100.0

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit_sha(),
        "model_name": DEFAULT_LIVE_MODEL,
        "sample_size": len(latencies),
        "rate_limit_delay_sec": rate_limit_delay,
        "metrics": {
            "latency_p50_ms": round(p50_lat, 2),
            "latency_p95_ms": round(p95_lat, 2),
            "cost_per_request_usd": round(mean_cost, 6),
            "judge_pass_rate": round(judge_pass_rate, 1),
            "hallucinated_url_rate": round(hallucinated_rate, 1),
            "mean_revisions": round(float(np.mean(revisions)), 2) if revisions else 0.0,
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    console.print(f"[bold green]Saved live evaluation results to {OUTPUT_FILE}[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="Run live evaluation against Gemini API")
    parser.add_argument("--samples", type=int, default=30, help="Number of samples to evaluate")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between API calls in seconds")
    args = parser.parse_args()
    run_live_eval(sample_size=args.samples, rate_limit_delay=args.delay)


if __name__ == "__main__":
    main()
