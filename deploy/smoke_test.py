"""
deploy/smoke_test.py
Automated end-to-end smoke verification script for live Cloud Run service.
Tests /health, /metrics, normal automated triage, and safety hazard escalation.
"""

import argparse
import sys
import time

import requests
from rich.console import Console
from rich.table import Table

console = Console()


def run_smoke_tests(base_url: str):
    url = base_url.rstrip("/")
    console.print(f"[bold cyan]Running Production Smoke Tests[/bold cyan] against [dim]{url}[/dim]\n")

    results = []

    # 1. Health Probe
    try:
        t0 = time.perf_counter()
        r = requests.get(f"{url}/health", timeout=10)
        lat = round((time.perf_counter() - t0) * 1000.0, 2)
        if r.status_code == 200 and r.json().get("status") == "healthy":
            results.append(("GET /health", "PASS", f"Status 200 OK ({lat} ms)"))
        else:
            results.append(("GET /health", "FAIL", f"Status {r.status_code}: {r.text}"))
    except Exception as exc:
        results.append(("GET /health", "FAIL", str(exc)))

    # 2. Metrics Endpoint
    try:
        t0 = time.perf_counter()
        r = requests.get(f"{url}/metrics", timeout=10)
        lat = round((time.perf_counter() - t0) * 1000.0, 2)
        if r.status_code == 200 and "requests" in r.json():
            results.append(("GET /metrics (JSON)", "PASS", f"Status 200 OK ({lat} ms)"))
        else:
            results.append(("GET /metrics (JSON)", "FAIL", f"Status {r.status_code}"))
    except Exception as exc:
        results.append(("GET /metrics (JSON)", "FAIL", str(exc)))

    # 3. Normal Triage Request
    try:
        t0 = time.perf_counter()
        payload = {
            "customer_query": "How do I set up Personal Hotspot on my iPhone to share data with Mac?",
            "ticket_id": "smoke_test_001",
        }
        r = requests.post(f"{url}/triage", json=payload, timeout=20)
        lat = round((time.perf_counter() - t0) * 1000.0, 2)
        data = r.json()
        if (
            r.status_code == 200
            and data.get("decision") == "draft"
            and len(data.get("drafted_reply", "")) > 0
        ):
            results.append((
                "POST /triage (Normal)",
                "PASS",
                f"Auto-Drafted [Resolution #{data.get('cited_resolution_ids', ['?'])[0]}] ({lat} ms)",
            ))
        else:
            results.append(("POST /triage (Normal)", "FAIL", f"Status {r.status_code}: {r.text}"))
    except Exception as exc:
        results.append(("POST /triage (Normal)", "FAIL", str(exc)))

    # 4. Safety Hazard Escalation Request
    try:
        t0 = time.perf_counter()
        payload = {
            "customer_query": "iPhone battery is swollen, smoking, and caught fire on my desk!",
            "ticket_id": "smoke_hazard_001",
        }
        r = requests.post(f"{url}/triage", json=payload, timeout=20)
        lat = round((time.perf_counter() - t0) * 1000.0, 2)
        data = r.json()
        if (
            r.status_code == 200
            and data.get("should_escalate") is True
            and data.get("escalation_tier") == "TIER_1_HARD_GUARDRAIL"
        ):
            results.append((
                "POST /triage (Safety Hazard)",
                "PASS",
                f"Escalated to Human ({lat} ms) Reason: {data.get('reason_code')}",
            ))
        else:
            results.append(("POST /triage (Safety Hazard)", "FAIL", f"Status {r.status_code}: {r.text}"))
    except Exception as exc:
        results.append(("POST /triage (Safety Hazard)", "FAIL", str(exc)))

    # Print Summary Table
    table = Table(title="Production Smoke Test Verification", header_style="bold magenta")
    table.add_column("Endpoint & Test Case", style="cyan", width=30)
    table.add_column("Result", style="bold", width=12)
    table.add_column("Diagnostics", style="dim", width=45)

    all_passed = True
    for test, res, diag in results:
        style = "green" if res == "PASS" else "red"
        if res != "PASS":
            all_passed = False
        table.add_row(test, f"[{style}]{res}[/{style}]", diag)

    console.print(table)

    if not all_passed:
        console.print("\n[red]One or more smoke tests failed.[/red]")
        sys.exit(1)
    else:
        console.print("\n[green][OK] All production smoke tests passed successfully![/green]")


def main():
    parser = argparse.ArgumentParser(description="Live Cloud Run Smoke Test Runner")
    parser.add_argument("url", type=str, help="Base URL of deployed Cloud Run service")
    args = parser.parse_args()
    run_smoke_tests(args.url)


if __name__ == "__main__":
    main()
