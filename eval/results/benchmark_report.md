# Verified Three-Block Benchmark Report

*Generated on 2026-11-23 12:48:15 UTC*
*Provenance: All numbers extracted directly from verified evaluation artifacts in eval/results/.*

---

## 📊 Benchmark Audit & Verified Results

All metrics below are generated directly from frozen evaluation artifacts in [`eval/results/`](eval/results/) using `make report`.

### Block 1: Golden Evaluation Set (200 Samples — Offline Deterministic Mode)

| Evaluation Metric | v1 Baseline (Monolithic) | v2 Multi-Agent (Google ADK) | Delta (v2 - v1) | Evaluation Mode & Provenance |
|---|---|---|---|---|
| **Intent Macro-F1** | `0.8734` | `0.8734` | `+0.0000` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation Recall** | `87.5%` | `100.0%` | `+12.5%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation Precision** | `28.0%` | `21.1%` | `-7.0%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation FNR (Safety Liability)** | `12.5%` | `0.0%` | `-12.5%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Hallucinated URL Rate** | `0.0%` | **`0.0%`** | `+0.0%` | Deterministic allowlist (`eval/results/e2e_v2.json`) |
| **Judge Pass Rate** | `100.0%` | `100.0%` | `+0.0%` | Offline mock judge, not an LLM evaluation (`eval/results/e2e_v2.json`) |
| **Cohen's Kappa (Escalation, n=50)** | `0.6935` | `0.6935` | `0.0000` | Synthetic calibration set, programmatic rules & offline mock judge, n=50 (`eval/results/e2e_v2.json`) |
| **Cohen's Kappa (Safety, n=50)** | `1.0000` | `1.0000` | `0.0000` | Synthetic calibration set, programmatic rules & offline mock judge, n=50 (`eval/results/e2e_v2.json`) |

- **Escalation Trade-off:** The system enforces an asymmetric safety priority: maximizing recall (100.0%) to guarantee hazardous hardware incidents (battery swelling/smoke) are never missed, trading off precision (21.1%) since reviewing false alarms is operationally cheap compared to catastrophic liability.
- **Escalation Baseline:** The False Negative Rate dropped from 88.0% (naive keyword baseline) to 12.5% in v1; v2 preserves this 0.0% safety rate across multi-agent handoffs.
- **URL Safeguards:** v1 and v2 both scored 0.0% hallucinated URLs on the golden set; v2 adds a deterministic domain allowlist and citation verification firewall as an architectural guarantee.

---

### Block 2: Vector Retrieval Benchmark (100 Held-Out Queries on Local pgvector)

Queries are held out from the indexed resolution precedents so no query's own resolution is present in the index ($n=100$, 768 dimensions, HNSW cosine index).

| Retrieval Metric | Keyword Baseline | Offline Embedder (Local Mock) | Real Embeddings (`gemini-embedding-001`) | Delta (Real vs Keyword) | Source JSON |
|---|---|---|---|---|---|
| **Retrieval Recall@1** | `11.0%` | `71.0%` | **`71.0%`** | `+60.0%` | [`retrieval_ab_pgvector.json`](eval/results/retrieval_ab_pgvector.json) |
| **Retrieval Recall@3** | `35.0%` | `86.0%` | **`86.0%`** | `+51.0%` | [`retrieval_ab_pgvector.json`](eval/results/retrieval_ab_pgvector.json) |
| **Retrieval Recall@5** | `50.0%` | `88.0%` | **`88.0%`** | `+38.0%` | [`retrieval_ab_pgvector.json`](eval/results/retrieval_ab_pgvector.json) |
| **Mean Reciprocal Rank (MRR)** | `0.248` | `0.783` | **`0.783`** | `+0.535` | [`retrieval_ab_pgvector.json`](eval/results/retrieval_ab_pgvector.json) |
| **Median Latency ($p50$)** | `3.73 ms` | `1.58 ms` | **`1.53 ms`** | `-2.20 ms` | [`retrieval_ab_pgvector.json`](eval/results/retrieval_ab_pgvector.json) |
| **Tail Latency ($p95$)** | `5.19 ms` | `2.67 ms` | **`2.76 ms`** | `-2.43 ms` | [`retrieval_ab_pgvector.json`](eval/results/retrieval_ab_pgvector.json) |

- **Embedding Model:** `gemini-embedding-001` (768 dimensions, unit-normalized).
- **Indexed Precedents:** 23 canonical customer support precedents with held-out test split.

---

### Block 3: Live Model Evaluation Sample (n=30 Stratified Golden Samples)

Evaluated via Google AI Studio against `gemini-3.5-flash` with rate limiting, exponential backoff, and Wilson 95% confidence intervals.
*Note: Sample size n=30 is small; reported confidence intervals reflect sampling uncertainty. Drafter and Judge agents both use the Gemini model family.*

| Metric Dimension | Measured Value | Wilson 95% Confidence Interval | Source & Environment |
|---|---|---|---|
| **Judge Pass Rate** | **`90.0%`** | `[74.4%, 96.5%]` | Live LLM Judge (`gemini-3.5-flash`) |
| **Escalation Recall** | **`100.0%`** | `[61.0%, 100.0%]` | Intent + Risk Gate routing |
| **Escalation Precision** | **`21.4%`** | `[10.2%, 39.5%]` | Intent + Risk Gate routing |
| **Hallucinated URL Rate** | **`0.0%`** | `[0.0%, 11.4%]` | Deterministic PolicyGuard allowlist |
| **Intent Classification Accuracy** | **`83.3%`** | `[66.4%, 92.7%]` | Stratified MECE intent match |
| **Median Total Latency ($p50$)** | **`3.85 ms`** | Auto-escalated tickets routed immediately | [`live_sample.json`](eval/results/live_sample.json) |
| **Tail Total Latency ($p95$)** | **`24195.72 ms`** | Includes live HTTP network round-trips & LLM generation | [`live_sample.json`](eval/results/live_sample.json) |
| **Mean Cost per Request** | **`$0.000018`** | Verified from [https://ai.google.dev/pricing](https://ai.google.dev/pricing) (2026-11-23) | [`live_sample.json`](eval/results/live_sample.json) |
| **Revision Distribution (0 / 1 / 2+)** | **`86.7%` / `3.3%` / `0.0%`** | Bounded self-reflection retry loop | [`live_sample.json`](eval/results/live_sample.json) |

---

### What These Numbers Do and Do Not Show

- **Why Offline Latency is Far Below Live Latency:** In Block 1 and Block 3 offline mocks, median execution latency is measured at `2.21 ms` because deterministic rule-based agents run entirely in-process on CPU with zero network hops. In Block 3 live evaluation, non-escalated tickets invoking live Gemini inference incur an end-to-end tail latency of `24195.7 ms` (24.20 s) due to real TLS handshakes, HTTP payload transport to Google AI Studio, and multi-token generative drafting and QA grading.
- **Safety Bias vs Precision:** Escalation recall is intentionally maintained at `100.0%` (offline) and `100.0%` (live sample) to guarantee zero missed physical hardware hazards (battery thermal runaway), accepting a precision of `21.1%` / `21.4%`.
- **Cohen's Kappa Provenance:** The `0.6935` Cohen's kappa score was produced on a 50-sample synthetic calibration dataset generated by programmatic rules in `create_golden_set.py` and evaluated with an offline mock judge ($n=50$). It does NOT represent human annotator consensus.
- **Deployment Status:** Cloud Run, Cloud SQL, Cloud Trace, and Vertex AI are target architectural designs and have never been provisioned or executed on live Google Cloud infrastructure. All local tests run via in-memory stores, local Docker containers, or direct Google AI Studio API calls.
