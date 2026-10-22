"""
demo.py
Interactive CLI demonstration of verifiable-support-agent.
Allows testing arbitrary customer support tweets in real time with instant rendering.
"""

import io
import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.config import PAIRED_CONVERSATIONS_FILE
from src.data_loader import load_or_process_paired_data
from src.llm_client import LLMClient
from src.pipeline import SupportAgentPipeline

# force_terminal=True + color_system="auto" makes rendering instant in Git Bash
console = Console(force_terminal=True, color_system="auto")


def main():
    console.print(
        Panel.fit(
            "[bold cyan]verifiable-support-agent[/bold cyan] - Interactive Live CLI\n"
            "[dim]A Trust-Calibrated Customer Support Agent with Grounded RAG & Risk Triage[/dim]",
            border_style="cyan",
        )
    )

    console.print("[dim]Initializing agent and loading historical knowledge base...[/dim]")
    kb_df = load_or_process_paired_data(PAIRED_CONVERSATIONS_FILE)
    llm = LLMClient(offline=True)
    pipeline = SupportAgentPipeline(knowledge_base_df=kb_df, llm_client=llm)
    console.print(f"[green][OK][/green] Pipeline ready! Knowledge base contains [bold]{len(kb_df)}[/bold] resolution pairs.\n")

    sample_queries = [
        "My iPhone 13 battery drains from 100% to 20% in 3 hours. Battery health is 84%.",
        "Battery on my iPhone expanded, cracked the screen, and is smoking!",
        "Someone hacked my Apple ID and locked me out of my phone. My phone is 555-0192.",
        "Was charged $49.99 for a subscription I canceled. I want a refund.",
        "How do I set up Personal Hotspot on my iPhone to share data with Mac?",
    ]

    console.print("[bold yellow]Sample queries (type 1-5 or any custom tweet):[/bold yellow]")
    for i, q in enumerate(sample_queries, 1):
        console.print(f"  [cyan]{i}.[/cyan] [dim]\"{q}\"[/dim]")
    console.print("\nType [bold red]'exit'[/bold red] to quit.\n")

    while True:
        try:
            user_input = input("Enter Customer Tweet: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[cyan]Goodbye![/cyan]")
            break

        if not user_input:
            continue
        if user_input.lower() in ["exit", "quit", "q"]:
            console.print("[cyan]Goodbye![/cyan]")
            break

        # Check if user typed a number 1-5
        if user_input.isdigit() and 1 <= int(user_input) <= len(sample_queries):
            user_input = sample_queries[int(user_input) - 1]
            console.print(f"[dim]Selected: \"{user_input}\"[/dim]")

        # Process through pipeline with latency measurement
        t0 = time.time()
        result = pipeline.process(user_input)
        latency_ms = (time.time() - t0) * 1000

        # Render structured triage card
        is_escalated = result["should_escalate"]
        esc_color = "red" if is_escalated else "green"
        esc_status = "ESCALATED TO HUMAN AGENT" if is_escalated else "AUTO-HANDLED BY AI"

        card = Table(show_header=False, box=None, padding=(0, 1))
        card.add_row("[bold]Normalized Query:[/bold]", f"[white]{result['customer_query']}[/white]")
        card.add_row(
            "[bold]Predicted Intent:[/bold]",
            f"[bold magenta]{result['intent']}[/bold magenta] (Confidence: [bold]{result['intent_confidence']:.2f}[/bold])",
        )
        card.add_row(
            "[bold]Triage Decision:[/bold]",
            f"[{esc_color} bold]{esc_status}[/{esc_color} bold] (Tier: [dim]{result['escalation_tier']}[/dim])",
        )
        card.add_row(
            "[bold]Stated Reason:[/bold]",
            f"[{esc_color}]{result['escalation_reason']}[/{esc_color}]",
        )
        card.add_row(
            "[bold]RAG Grounding:[/bold]",
            f"Similarity: [bold]{result['max_similarity_score']:.2f}[/bold] (Well-grounded: {result['is_well_grounded']})",
        )
        card.add_row(
            "[bold]Drafted Reply:[/bold]",
            f"[italic cyan]\"{result['drafted_reply']}\"[/italic cyan]",
        )
        card.add_row(
            "[bold]Latency:[/bold]",
            f"[dim]{latency_ms:.1f} ms[/dim]",
        )

        console.print(
            Panel(
                card,
                title=f"[{esc_color} bold]Triage & Resolution Audit Card[/{esc_color} bold]",
                border_style=esc_color,
            )
        )
        console.print()


if __name__ == "__main__":
    main()
