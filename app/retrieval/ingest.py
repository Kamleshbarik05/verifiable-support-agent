"""
app/retrieval/ingest.py
Batch ingestion pipeline for historical support resolutions.
Embeds customer inquiries with intent context into pgvector.
Enforces idempotency using SHA-256 source hashing.
"""

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.progress import track

# Ensure project root and app/v1 are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.classifier import IntentClassifier  # noqa: E402
from src.config import PAIRED_CONVERSATIONS_FILE  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402

from app.retrieval.embedder import Embedder, get_embedder  # noqa: E402
from app.retrieval.vector_store import VectorStore  # noqa: E402

console = Console(force_terminal=True, color_system="auto")


def generate_source_hash(customer_query: str, resolution_text: str) -> str:
    """Computes SHA-256 digest over query and resolution for idempotent deduplication."""
    content = f"{customer_query.strip().lower()}|{resolution_text.strip().lower()}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest_resolutions_from_df(
    df: pd.DataFrame,
    vector_store: VectorStore,
    embedder: Embedder,
    batch_size: int = 50,
) -> dict[str, int]:
    """
    Ingests DataFrame records into the vector store in batches.
    Returns summary statistics: total, inserted, skipped.
    """
    llm = LLMClient(offline=True)
    classifier = IntentClassifier(llm_client=llm)

    total_records = len(df)
    inserted_count = 0
    skipped_count = 0

    batch: list[dict[str, Any]] = []

    for _, row in track(df.iterrows(), total=total_records, description="[cyan]Embedding and Ingesting...[/cyan]"):
        customer_query = str(row.get("customer_query", "")).strip()
        apple_resolution = str(row.get("apple_resolution", "")).strip()
        record_id = str(row.get("customer_tweet_id", f"res_{len(batch)}"))

        if not customer_query or not apple_resolution:
            continue

        # 1. Classify Intent
        intent_res = classifier.classify(customer_query)
        intent = intent_res["intent"]

        # 2. Compute SHA-256 Idempotency Hash
        source_hash = generate_source_hash(customer_query, apple_resolution)

        # 3. Asymmetric Embedding Target
        text_to_embed = f"[{intent}] {customer_query}"
        embedding = embedder.embed_text(text_to_embed)

        batch.append({
            "id": record_id,
            "brand_text": "@AppleSupport",
            "issue_text": customer_query,
            "resolution_text": apple_resolution,
            "intent": intent,
            "embedding": embedding,
            "source_hash": source_hash,
        })

        if len(batch) >= batch_size:
            num_inserted = vector_store.upsert_batch(batch)
            inserted_count += num_inserted
            skipped_count += (len(batch) - num_inserted)
            batch = []

    if batch:
        num_inserted = vector_store.upsert_batch(batch)
        inserted_count += num_inserted
        skipped_count += (len(batch) - num_inserted)

    return {
        "total_processed": total_records,
        "inserted": inserted_count,
        "skipped": skipped_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest support resolutions into pgvector store")
    parser.add_argument(
        "--csv-path",
        type=str,
        default=str(PAIRED_CONVERSATIONS_FILE),
        help="Path to paired conversations CSV",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="local",
        choices=["local", "vertex"],
        help="Embedder provider",
    )
    parser.add_argument("--batch-size", type=int, default=50, help="Ingestion batch size")
    args = parser.parse_args()

    csv_file = Path(args.csv_path)
    if not csv_file.exists():
        console.print(f"[red]Error:[/red] CSV file not found at {csv_file}")
        sys.exit(1)

    console.print(f"[bold cyan]Starting Ingestion Pipeline[/bold cyan] from [dim]{csv_file}[/dim]")
    df = pd.read_csv(csv_file)
    vector_store = VectorStore()
    embedder = get_embedder(provider=args.provider)

    stats = ingest_resolutions_from_df(
        df=df,
        vector_store=vector_store,
        embedder=embedder,
        batch_size=args.batch_size,
    )

    console.print(
        f"\n[green][OK] Ingestion Complete:[/green] "
        f"Processed: {stats['total_processed']} | "
        f"Inserted: {stats['inserted']} | "
        f"Skipped (Deduplicated): {stats['skipped']} | "
        f"Total in Store: {vector_store.count()}\n"
    )


if __name__ == "__main__":
    main()
