"""
deploy/migrate_cloudsql.py
Runs the SQL migration and populates historical support resolution embeddings into Cloud SQL pgvector.
Can be executed locally with Cloud SQL Auth Proxy or inside Google Cloud.
"""

import argparse
import os
from pathlib import Path

import psycopg
from rich.console import Console

from app.retrieval.embedder import get_embedder
from app.retrieval.ingest import ingest_resolutions
from app.retrieval.vector_store import VectorStore

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = REPO_ROOT / "app" / "retrieval" / "schema.sql"
PAIRED_CSV_FILE = REPO_ROOT / "eval" / "datasets" / "apple_conversations_paired.csv"


def run_migration(
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_pass: str,
):
    console.print(f"[bold cyan]Connecting to Cloud SQL PostgreSQL at[/bold cyan] {db_host}:{db_port}/{db_name}...")

    # 1. Apply schema.sql
    with open(SCHEMA_FILE, encoding="utf-8") as f:
        schema_sql = f.read()

    with psycopg.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_pass,
    ) as conn:
        with conn.cursor() as cur:
            console.print("[dim]Applying schema (enabling pgvector & creating HNSW indexes)...[/dim]")
            cur.execute(schema_sql)
            conn.commit()
    console.print("[green][OK] Schema migration applied successfully.[/green]")

    # 2. Batch Ingest Embeddings
    console.print("[dim]Ingesting historical resolutions with embeddings...[/dim]")
    store = VectorStore(
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_pass,
    )
    embedder = get_embedder(provider="local")

    stats = ingest_resolutions(
        csv_path=PAIRED_CSV_FILE,
        vector_store=store,
        embedder=embedder,
    )
    console.print(
        f"[green][OK] Ingestion complete:[/green] "
        f"Inserted: {stats['inserted']}, Total in DB: {store.count()}"
    )


def main():
    parser = argparse.ArgumentParser(description="Cloud SQL Migration & Ingestion Runner")
    parser.add_argument("--host", default=os.getenv("DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "5432")))
    parser.add_argument("--name", default=os.getenv("DB_NAME", "support_agent_db"))
    parser.add_argument("--user", default=os.getenv("DB_USER", "postgres"))
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "postgres"))
    args = parser.parse_args()

    run_migration(args.host, args.port, args.name, args.user, args.password)


if __name__ == "__main__":
    main()
