# Verified Benchmark Report

*Generated on 2026-11-23 08:48:16 UTC*

| Evaluation Dimension | v1 Baseline (Monolithic) | v2 Multi-Agent (Google ADK) | Delta (v2 - v1) | Source JSON |
|---|---|---|---|---|
| **Intent Macro-F1** | `0.8734` | `0.8734` | `+0.0000` | `eval/results/e2e_v2.json` |
| **Escalation Recall** | `87.5%` | `87.5%` | `+0.0%` | `eval/results/e2e_v2.json` |
| **Escalation FNR (Safety Risk)** | `12.5%` | `12.5%` | `+0.0%` | `eval/results/e2e_v2.json` |
| **Hallucinated URL Rate** | `0.0%` | `0.0%` | `+0.0%` | `eval/results/e2e_v2.json` |
| **Retrieval Recall@1** | `11.0%` | `71.0%` | `+60.0%` | `eval/results/retrieval_ab.json` |
| **Retrieval Recall@3** | `35.0%` | `86.0%` | `+51.0%` | `eval/results/retrieval_ab.json` |
| **Mean Reciprocal Rank (MRR)** | `0.248` | `0.783` | `+0.535` | `eval/results/retrieval_ab.json` |
| **p50 Latency** | `3.2 ms` | `1.8 ms` | `-1.4 ms` | `eval/results/latency_cost.json` |
| **p95 Latency** | `5.2 ms` | `2.9 ms` | `-2.3 ms` | `eval/results/latency_cost.json` |
| **Cost per Request** | `$0.000000` | `$0.000005` | `+$0.000005` | `eval/results/latency_cost.json` |
| **1-Pass Direct Approvals** | N/A | `97.0%` | N/A | `eval/results/latency_cost.json` |

---

### Step-by-Step Latency Breakdown (v2 ADK Orchestrator)
- **Triage (Intent + Risk Gates):** p50 = `0.12 ms`, p95 = `0.23 ms`
- **Retrieval (pgvector HNSW cosine search):** p50 = `1.44 ms`, p95 = `2.24 ms`
- **Drafting (Grounded Synthesis):** p50 = `0.03 ms`, p95 = `0.13 ms`
- **PolicyGuard (Firewall & URL Check):** p50 = `0.03 ms`, p95 = `0.06 ms`
- **Critic (QA Rubric Grading):** p50 = `0.07 ms`, p95 = `0.18 ms`
