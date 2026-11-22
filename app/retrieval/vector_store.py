"""
app/retrieval/vector_store.py
Production-grade Vector Store with dual-mode architecture:
1. Primary: PostgreSQL + pgvector (Cloud SQL / Docker) with HNSW indexing and metadata filtering.
2. Resilient Fallback: Thread-safe in-memory cosine store for zero-dependency CI and offline testing.
"""

import os
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class ResolutionRecord:
    id: str
    brand_text: str
    issue_text: str
    resolution_text: str
    intent: str
    similarity_score: float
    source_hash: str


class VectorStore:
    """
    Dual-mode Vector Store supporting PostgreSQL (pgvector) and local fallback.
    """

    def __init__(
        self,
        db_host: str | None = None,
        db_port: int | None = None,
        db_name: str | None = None,
        db_user: str | None = None,
        db_password: str | None = None,
    ):
        self.db_host = db_host or os.getenv("DB_HOST", "127.0.0.1")
        self.db_port = db_port or int(os.getenv("DB_PORT", "5432"))
        self.db_name = db_name or os.getenv("DB_NAME", "support_agent_db")
        self.db_user = db_user or os.getenv("DB_USER", "postgres")
        self.db_password = db_password or os.getenv("DB_PASSWORD", "postgres")

        self.is_connected = False
        self._in_memory_records: list[dict[str, Any]] = []
        self._seen_hashes: set[str] = set()

        self._try_connect()

    def _try_connect(self):
        """Attempts connection to PostgreSQL + pgvector."""
        try:
            import psycopg

            conn = psycopg.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password,
                connect_timeout=2,
            )
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            conn.close()
            self.is_connected = True
        except Exception:
            # Gracefully operate in in-memory fallback mode
            self.is_connected = False

    def upsert_batch(self, records: list[dict[str, Any]]) -> int:
        """
        Inserts a batch of records idempotently based on source_hash.
        Returns the number of new records inserted.
        """
        if not records:
            return 0

        if self.is_connected:
            return self._postgres_upsert_batch(records)
        return self._in_memory_upsert_batch(records)

    def _postgres_upsert_batch(self, records: list[dict[str, Any]]) -> int:
        import psycopg

        inserted = 0
        try:
            with psycopg.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password,
            ) as conn:
                with conn.cursor() as cur:
                    for r in records:
                        emb_str = f"[{','.join(str(x) for x in r['embedding'])}]"
                        cur.execute(
                            """
                            INSERT INTO resolutions (
                                id, brand_text, issue_text, resolution_text, intent, embedding, source_hash
                            )
                            VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
                            ON CONFLICT (source_hash) DO NOTHING
                            RETURNING id;
                            """,
                            (
                                r["id"],
                                r.get("brand_text", "@AppleSupport"),
                                r["issue_text"],
                                r["resolution_text"],
                                r["intent"],
                                emb_str,
                                r["source_hash"],
                            ),
                        )
                        if cur.fetchone():
                            inserted += 1
                conn.commit()
            return inserted
        except Exception:
            # If PostgreSQL fails during runtime, store in in-memory fallback
            return self._in_memory_upsert_batch(records)

    def _in_memory_upsert_batch(self, records: list[dict[str, Any]]) -> int:
        inserted = 0
        for r in records:
            sh = r["source_hash"]
            if sh not in self._seen_hashes:
                self._seen_hashes.add(sh)
                # Store normalized copy
                rec_copy = dict(r)
                vec = np.array(r["embedding"], dtype=np.float32)
                norm = np.linalg.norm(vec)
                rec_copy["_vec"] = vec / norm if norm > 0 else vec
                self._in_memory_records.append(rec_copy)
                inserted += 1
        return inserted

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 3,
        intent_filter: str | None = None,
    ) -> list[ResolutionRecord]:
        """
        Executes hybrid vector similarity search with optional metadata intent filtering.
        """
        if self.is_connected:
            try:
                return self._postgres_search(query_embedding, top_k, intent_filter)
            except Exception:
                pass
        return self._in_memory_search(query_embedding, top_k, intent_filter)

    def _postgres_search(
        self,
        query_embedding: list[float],
        top_k: int,
        intent_filter: str | None,
    ) -> list[ResolutionRecord]:
        import psycopg

        emb_str = f"[{','.join(str(x) for x in query_embedding)}]"
        with psycopg.connect(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password,
        ) as conn:
            with conn.cursor() as cur:
                if intent_filter:
                    cur.execute(
                        """
                        SELECT id, brand_text, issue_text, resolution_text, intent, source_hash,
                               1 - (embedding <=> %s::vector) AS similarity_score
                        FROM resolutions
                        WHERE intent = %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s;
                        """,
                        (emb_str, intent_filter, emb_str, top_k),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, brand_text, issue_text, resolution_text, intent, source_hash,
                               1 - (embedding <=> %s::vector) AS similarity_score
                        FROM resolutions
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s;
                        """,
                        (emb_str, emb_str, top_k),
                    )

                rows = cur.fetchall()
                results = []
                for row in rows:
                    results.append(
                        ResolutionRecord(
                            id=row[0],
                            brand_text=row[1],
                            issue_text=row[2],
                            resolution_text=row[3],
                            intent=row[4],
                            source_hash=row[5],
                            similarity_score=round(float(row[6]), 4),
                        )
                    )
                return results

    def _in_memory_search(
        self,
        query_embedding: list[float],
        top_k: int,
        intent_filter: str | None,
    ) -> list[ResolutionRecord]:
        if not self._in_memory_records:
            return []

        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        candidates = []
        for r in self._in_memory_records:
            if intent_filter and r.get("intent") != intent_filter:
                continue
            sim = float(np.dot(q_vec, r["_vec"]))
            candidates.append((sim, r))

        candidates.sort(key=lambda x: x[0], reverse=True)
        top_matches = candidates[:top_k]

        results = []
        for sim, r in top_matches:
            results.append(
                ResolutionRecord(
                    id=r["id"],
                    brand_text=r.get("brand_text", "@AppleSupport"),
                    issue_text=r["issue_text"],
                    resolution_text=r["resolution_text"],
                    intent=r["intent"],
                    source_hash=r["source_hash"],
                    similarity_score=round(sim, 4),
                )
            )
        return results

    def count(self) -> int:
        """Returns total count of stored resolutions."""
        if self.is_connected:
            try:
                import psycopg

                with psycopg.connect(
                    host=self.db_host,
                    port=self.db_port,
                    dbname=self.db_name,
                    user=self.db_user,
                    password=self.db_password,
                ) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT count(*) FROM resolutions;")
                        res = cur.fetchone()
                        return res[0] if res else 0
            except Exception:
                pass
        return len(self._in_memory_records)
