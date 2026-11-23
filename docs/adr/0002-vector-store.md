# ADR 0002: Vector Database and Approximate Nearest Neighbor (ANN) Index Choice

## Status
Accepted

## Context
In `verifiable-support-agent` v1, historical support resolutions were retrieved using an in-memory TF-IDF and scikit-learn / sentence-transformers model loaded into Python heap space.

In a target enterprise Google Cloud deployment, this architecture introduces major operational flaws:
1. **Cloud Run Memory & Cold Starts:** Loading dense vector arrays into Python memory inflates container RAM requirements (exceeding 1GB) and adds 10–15 seconds to serverless container cold-start times.
2. **Lack of Metadata Filtering (Hybrid Search):** Support triage requires filtering by diagnostic intent (e.g. `intent = 'HARDWARE_BATTERY_PERFORMANCE'`) before ranking candidates. In-memory arrays require custom, unindexed Python loops.
3. **No ACID Persistence:** Support teams update and ingest troubleshooting precedents continuously. In-memory embeddings require restarting running services to refresh the knowledge base.

We need a persistent vector search architecture that supports hybrid metadata filtering, fast query latencies (<10ms), and minimal cloud infrastructure cost.

## Decision

### 1. Vector Engine: PostgreSQL with `pgvector` on Cloud SQL
We choose **PostgreSQL 16 with the `pgvector` extension** targeted for **Google Cloud SQL** (with a local `pgvector/pgvector:pg16` Docker container for local development and testing).

#### Comparison of Alternatives:
| Evaluation Criteria | PostgreSQL + `pgvector` (Cloud SQL) | Google Vertex AI Vector Search | In-Memory FAISS / Chroma |
|---|:---:|:---:|:---:|
| **Optimal Scale** | Up to ~1,000,000 vectors | 10,000,000 to 1,000,000,000+ vectors | <50,000 vectors |
| **Minimum Cloud Cost** | ~$10–$25 / month (db-f1-micro) | ~$220+ / month (minimum dedicated node) | Free (absorbed in container RAM) |
| **Relational Joins & SQL** | ✅ Full SQL & relational tables | ❌ Standalone index only | ❌ No relational capabilities |
| **Hybrid Metadata Filtering** | ✅ Native B-Tree SQL indexing | ✅ Restricted metadata namespaces | ⚠️ Custom post-filter in Python |
| **Cloud Run Cold Start Impact** | ✅ 0 MB container memory impact | ✅ 0 MB container memory impact | ❌ Adds 10–15s & 1GB+ memory bloat |

**Rationale:** For customer support triage with tens of thousands of verified resolution precedents, Vertex AI Vector Search is cost-prohibitive for early-stage or mid-sized deployments. `pgvector` on Cloud SQL allows storing tickets, agent audits, and embeddings in a single ACID-compliant database.

---

### 2. Approximate Nearest Neighbor (ANN) Index: HNSW
We choose **HNSW (Hierarchical Navigable Small World)** using cosine distance:
```sql
CREATE INDEX resolutions_embedding_hnsw_idx
ON resolutions
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

#### HNSW vs. IVFFlat Comparison:
- **HNSW (Selected):** Builds a multi-layer proximity graph. Delivers >98% Recall@K, sub-5ms search latencies, and **does not require periodic index retraining** when new customer resolution pairs are upserted.
- **IVFFlat (Rejected):** Partitions vector space into Voronoi cells (`WITH (lists = 100)`). While it uses less memory, IVFFlat suffers significantly lower recall on un-normalized distributions and requires full index rebuilds (`REINDEX`) whenever resolution volumes shift.

---

### 3. Ingestion Strategy: Asymmetric Query-to-Issue Matching
- We embed `f"[{intent}] {customer_query}"` as the indexing target.
- Incoming customer tickets align semantically with historical customer problems, maximizing cosine similarity.
- The official resolution text is stored in the `resolution_text` payload column and retrieved for grounded LLM drafting.

## Consequences

### Positive
- **Low Cloud Cost:** Sized for the smallest Google Cloud SQL instance (`db-f1-micro` or `db-custom-1-3840`) in target deployment.
- **Zero Cold-Start Overhead:** Cloud Run containers remain stateless and lightweight (<256MB base memory).
- **Hybrid Search:** Combines B-Tree filtered SQL queries (`WHERE intent = ...`) with HNSW cosine ranking in a single query.
- **Idempotency:** SHA-256 `source_hash` column with `ON CONFLICT (source_hash) DO NOTHING` prevents duplicate embedding costs.

### Negative / Trade-offs
- In Cloud Run, connections to Cloud SQL require the Cloud SQL Auth Proxy or Unix domain sockets.
- In offline environments without Docker, the application must maintain a transparent in-memory fallback (implemented in `VectorStore`).
