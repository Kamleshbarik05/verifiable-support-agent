# Verified Benchmark Report

*Generated on 2026-11-23 11:31:11 UTC*
*Provenance: All numbers extracted directly from verified evaluation artifacts in `eval/results/`.*

---

## 1. End-to-End Golden Benchmark (200 Samples — Offline Deterministic Mode)

| Evaluation Metric | v1 Baseline (Monolithic) | v2 Multi-Agent (Google ADK) | Delta (v2 - v1) | Evaluation Mode & Source |
|---|---|---|---|---|
| **Intent Macro-F1** | `0.8734` | `0.8734` | `+0.0000` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation Recall** | `87.5%` | `87.5%` | `+0.0%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation Precision** | `28.0%` | `19.4%` | `-8.6%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation FNR (Safety Liability)** | `12.5%` | `12.5%` | `+0.0%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Hallucinated URL Rate** | `0.0%` | `0.0%` | `+0.0%` | Deterministic allowlist (`eval/results/e2e_v2.json`) |
| **Judge Pass Rate** | `100.0%` | `100.0%` | `+0.0%` | Offline mock judge, not an LLM evaluation (`eval/results/e2e_v2.json`) |
| **Cohen's Kappa (Escalation)** | `0.6935` | `0.6935` | `0.0000` | 50-sample synthetic calibration set (`eval/results/e2e_v2.json`) |
| **Cohen's Kappa (Safety)** | `1.0000` | `1.0000` | `0.0000` | 50-sample synthetic calibration set (`eval/results/e2e_v2.json`) |

> **Escalation Trade-off Note:** The system is intentionally tuned with an asymmetric safety bias: prioritizing high escalation recall (87.5%) to catch critical battery/legal hazards, accepting lower precision (19.4%) because false alarms cost an agent 30 seconds whereas a missed battery fire creates catastrophic enterprise liability.
> **Escalation FNR Baseline Note:** The escalation False Negative Rate dropped from 88.0% (naive keyword baseline) to 12.5% in the v1 pipeline; v2 matches v1's 12.5% FNR while introducing structured multi-agent state handoffs.
> **URL Hallucination Note:** v1 and v2 both scored 0.0% on the golden evaluation set; v2 adds an explicit deterministic domain allowlist and citation verification firewall as an architectural guarantee.

---

## 2. Vector Retrieval A/B Benchmark (100 Samples — HNSW Cosine vs v1 Keyword/Shallow Search)

| Retrieval Metric | v1 Baseline Retrieval | v2 Dense Vector (`pgvector` / HNSW) | Delta (v2 - v1) | Source JSON |
|---|---|---|---|---|
| **Retrieval Recall@1** | `11.0%` | `71.0%` | `+60.0%` | `eval/results/retrieval_ab.json` |
| **Retrieval Recall@3** | `35.0%` | `86.0%` | `+51.0%` | `eval/results/retrieval_ab.json` |
| **Retrieval Recall@5** | `50.0%` | `88.0%` | `+38.0%` | `eval/results/retrieval_ab.json` |
| **Mean Reciprocal Rank (MRR)** | `0.248` | `0.783` | `+0.535` | `eval/results/retrieval_ab.json` |
| **Median Search Latency (p50)** | `3.75 ms` | `1.65 ms` | `-2.10 ms` | `eval/results/retrieval_ab.json` |
| **Tail Search Latency (p95)** | `6.56 ms` | `2.79 ms` | `-3.77 ms` | `eval/results/retrieval_ab.json` |

---

## 3. Operational Telemetry & Cost Accounting (100 Samples — Offline Deterministic Mock)

| Metric | Measured Value | Evaluation Mode & Note | Source JSON |
|---|---|---|---|
| **Median Latency ($p50$)** | `1.76 ms` | Offline deterministic execution (no live network hops) | `eval/results/latency_cost.json` |
| **Tail Latency ($p95$)** | `2.90 ms` | Offline deterministic execution (no live network hops) | `eval/results/latency_cost.json` |
| **Mean Cost per Request** | `$0.000005` | Estimated token cost via pricing table registry | `eval/results/latency_cost.json` |
| **1-Pass Approval Rate** | `97.0%` | Offline mock critic passing drafts without revision | `eval/results/latency_cost.json` |
| **2+ Revisions Rate** | `3.0%` | Bounded retry loop triggered before approval/escalation | `eval/results/latency_cost.json` |

### Step-by-Step Latency Breakdown ($p50$ / $p95$ in Offline Mode)
- **Triage (Intent + Risk Gates):** 0.12 ms / 0.23 ms
- **Retrieval (Dense Cosine Search):** 1.44 ms / 2.24 ms
- **Drafting (Grounded Synthesis):** 0.03 ms / 0.13 ms
- **PolicyGuard (URL Allowlist & PII Regex):** 0.03 ms / 0.06 ms
- **Critic (QA Rubric Scoring):** 0.07 ms / 0.18 ms

---

## 5. What These Numbers Do and Do Not Show

### What These Numbers DO Show:
1. **Architectural & State Machine Correctness:** Proves that hierarchical multi-agent state delegation (Orchestrator -> Triage -> Retrieval -> Draft -> PolicyGuard -> Critic) operates reliably under deterministic transition gates without infinite loops.
2. **Deterministic Safety Enforcement:** Confirms that Tier 1 physical hazards (battery swelling/smoke) and public PII are vetoed and escalated deterministically before reaching any generative drafting stage.
3. **Retrieval Improvements from Dense Indexing:** Demonstrates that dense semantic indexing increases Recall@3 from 35.0% to 86.0% (+51.0%) and MRR from 0.248 to 0.783 compared to shallow word-overlap baselines.
4. **Deterministic Accounting:** Proves that token consumption and USD costs are tracked accurately at every agent boundary via versioned pricing models.

### What These Numbers DO NOT Show:
1. **Live Production Network Latency:** Sub-3ms latency figures reflect local offline CPU execution with mocked LLMs. A live system calling Vertex AI or Gemini APIs experiences 300–800ms of latency per generative LLM call.
2. **Real Enterprise Human Agreement:** The 0.6935 Cohen's kappa was computed on a 50-sample synthetic calibration dataset generated via algorithmic formulas in `app/v1/scripts/create_golden_set.py`, not by a panel of human domain annotators.
3. **Live Cloud Infrastructure Uptime:** The Cloud Run, Cloud SQL, and Cloud Trace components represent target deployment specifications and have not been provisioned or load-tested in a live GCP production project.
