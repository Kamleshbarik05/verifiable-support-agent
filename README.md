# Verifiable Support Agent v2 — Multi-Agent Support Triage & Grounded Resolution

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/Kamleshbarik05/verifiable-support-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Kamleshbarik05/verifiable-support-agent/actions/workflows/ci.yml)
[![Ruff Lint](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![OpenTelemetry](https://img.shields.io/badge/tracing-OpenTelemetry-blueviolet.svg)](https://opentelemetry.io/)
[![pgvector](https://img.shields.io/badge/vector%20db-pgvector-336791.svg)](https://github.com/pgvector/pgvector)

> **Multi-agent customer support triage and grounded resolution architecture with pgvector retrieval, local OpenTelemetry tracing, deterministic URL allowlisting, and bounded self-reflection.**

---

## 🎯 Problem Statement & Technical Discovery

In enterprise customer support, generating plausible conversational text is trivial; **proving that an automated multi-agent system can be trusted is the core engineering challenge**. When deploying LLMs on public customer channels (such as `@AppleSupport` on Twitter/X), generative models frequently generate hallucinated warranty policies, fabricate non-existent support URLs, leak customer PII, or fail to escalate physical hardware hazards (e.g., swollen smoking batteries) to human specialists.

Based on problem framing and domain requirements documented in [`docs/discovery.md`](docs/discovery.md), **`verifiable-support-agent v2`** replaces brittle, single-prompt LLM wrappers with a **hierarchical multi-agent architecture (Google ADK)** backed by **dense semantic vector retrieval (`pgvector`)**, **deterministic guardrail firewalls**, and **local OpenTelemetry tracing** (Cloud Trace = design target only; see [`docs/tracing_guide.md`](docs/tracing_guide.md)).

---

## 🏗️ Architecture & Multi-Agent Flow

The system implements hierarchical agent delegation compliant with the **Google Agent Development Kit (ADK)**:

```mermaid
flowchart TD
    Query["Customer Support Inquiry / Tweet"] --> Orchestrator["OrchestratorAgent (Root Governor)"]

    subgraph TriageGate ["Phase 1: Risk & Intent Gate"]
        Orchestrator --> TriageAgent["TriageAgent (Intent Classifier & Risk Gates)"]
        TriageAgent -->|"Swollen Battery / Legal Threat / PII"| FastEscalate["Short-Circuit Escalation (Tier 1/2)"]
    end

    subgraph GroundingPhase ["Phase 2: Semantic Grounding"]
        TriageAgent -->|"Standard Diagnostic Query"| RetrievalAgent["RetrievalAgent (Dense Vector Search)"]
        RetrievalAgent --> CloudSQL[("Cloud SQL / pgvector<br>HNSW Cosine Index")]
        RetrievalAgent --> QualityGate{"Grounding Quality Gate<br>Similarity >= 0.50?"}
        QualityGate -->|"Low Similarity (< 0.50)"| HallucinationEscalate["Escalate to Human (Prevent Hallucination)"]
    end

    subgraph ReflectionLoop ["Phase 3: Bounded Self-Reflection Loop (Max 2 Retries)"]
        QualityGate -->|"Grounded (Similarity >= 0.50)"| DraftAgent["DraftAgent (Grounded LLM Synthesis)"]
        DraftAgent --> PolicyGuard["PolicyGuard (Deterministic URL & PII Firewall)"]
        PolicyGuard -->|"Policy Violation (Ungrounded Link)"| DraftAgent
        PolicyGuard -->|"Policy Passed"| CriticAgent["CriticAgent (Multi-Dimensional QA Rubric)"]
        CriticAgent -->|"Score < 4 (Targeted Feedback)"| DraftAgent
    end

    CriticAgent -->|"Approved (Groundedness >= 4)"| VerifiedResponse["Verified Response Payload<br>(Cited IDs, OTel Trace, Step Metrics)"]
```

### Specialized Sub-Agents

| Agent | Architecture Pattern | Responsibility & Boundaries | Tools & Dependencies |
|---|---|---|---|
| **`OrchestratorAgent`** | Root Controller | Manages state lifecycle, early returns, and bounded retry loops ($\le 2$ revisions). | Sub-agent delegation |
| **`TriageAgent`** | Categorical Router | 7-class MECE intent categorization and Tier 1/2 risk routing. | `classify_intent`, `risk_gate` |
| **`RetrievalAgent`** | Semantic Searcher | Queries dense embeddings using HNSW cosine distance; enforces grounding gates. | `search_resolutions` |
| **`DraftAgent`** | Grounded Synthesizer | Generates concise replies strictly constrained to historical precedent; cites resolution IDs. | Vertex AI Gemini 1.5 Flash |
| **`PolicyGuard`** | Deterministic Firewall | Absolute veto authority: blocks ungrounded links and public PII leakage. | `url_allowlist_check`, `pii_check` |
| **`CriticAgent`** | Quality Evaluator | Evaluates groundedness, actionability, tone, and safety against the QA rubric. | `judge_score` |

---

## 📊 Benchmark Audit & Verified Results

All metrics below are generated from frozen evaluation artifacts in [`eval/results/`](eval/results/) using `make report`.

### Block 1: Golden Evaluation Set (200 Samples — Offline Deterministic Mode)

| Evaluation Metric | v1 Baseline (Monolithic) | v2 Multi-Agent (Google ADK) | Delta (v2 - v1) | Evaluation Mode & Provenance |
|---|---|---|---|---|
| **Intent Macro-F1** | `0.8734` | `0.8734` | `+0.0000` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation Recall** | `87.5%` | `87.5%` | `+0.0%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation Precision** | `28.0%` | `19.4%` | `-8.6%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Escalation FNR (Safety Liability)** | `12.5%` | `12.5%` | `+0.0%` | Offline mock (`eval/results/e2e_v2.json`) |
| **Hallucinated URL Rate** | `0.0%` | **`0.0%`** | `+0.0%` | Deterministic allowlist (`eval/results/e2e_v2.json`) |
| **Judge Pass Rate** | `100.0%` | `100.0%` | `+0.0%` | Offline mock judge, not an LLM evaluation (`eval/results/e2e_v2.json`) |
| **Cohen's Kappa (Escalation, n=50)** | `0.6935` | `0.6935` | `0.0000` | Synthetic calibration set, programmatic rules & offline mock judge (`eval/results/e2e_v2.json`) |
| **Cohen's Kappa (Safety, n=50)** | `1.0000` | `1.0000` | `0.0000` | Synthetic calibration set, programmatic rules & offline mock judge (`eval/results/e2e_v2.json`) |

- **Escalation Trade-off:** The system enforces an asymmetric safety priority: maximizing recall (87.5%) to guarantee hazardous hardware incidents (battery swelling/smoke) are never missed, trading off precision (19.4%) since reviewing false alarms is operationally cheap compared to catastrophic liability.
- **Escalation Baseline:** The False Negative Rate dropped from 88.0% (naive keyword baseline) to 12.5% in v1; v2 preserves this 12.5% safety rate across multi-agent handoffs.
- **URL Safeguards:** v1 and v2 both scored 0.0% hallucinated URLs on the golden set; v2 adds a deterministic domain allowlist and citation verification firewall as an architectural guarantee.

---

### Block 2: Vector Retrieval A/B Benchmark (100 Samples — HNSW Cosine vs Keyword Search)

| Retrieval Metric | v1 Baseline Retrieval | v2 Dense Vector (`pgvector` / HNSW) | Delta (v2 - v1) | Source JSON |
|---|---|---|---|---|
| **Retrieval Recall@1** | `11.0%` | **`71.0%`** | **`+60.0%`** | [`retrieval_ab.json`](eval/results/retrieval_ab.json) |
| **Retrieval Recall@3** | `35.0%` | **`86.0%`** | **`+51.0%`** | [`retrieval_ab.json`](eval/results/retrieval_ab.json) |
| **Retrieval Recall@5** | `50.0%` | **`88.0%`** | **`+38.0%`** | [`retrieval_ab.json`](eval/results/retrieval_ab.json) |
| **Mean Reciprocal Rank (MRR)** | `0.248` | **`0.783`** | **`+0.535`** | [`retrieval_ab.json`](eval/results/retrieval_ab.json) |
| **Median Search Latency ($p50$)** | `3.75 ms` | **`1.65 ms`** | **`-2.10 ms`** | [`retrieval_ab.json`](eval/results/retrieval_ab.json) |
| **Tail Search Latency ($p95$)** | `6.56 ms` | **`2.79 ms`** | **`-3.77 ms`** | [`retrieval_ab.json`](eval/results/retrieval_ab.json) |

---

### Block 3: Step Latency & Cost Telemetry (100 Samples — Offline Deterministic Mode)

| Telemetry Dimension | Measured Value | Evaluation Mode | Source JSON |
|---|---|---|---|
| **Median Total Latency ($p50$)** | `1.76 ms` | Local offline execution (CPU) | [`latency_cost.json`](eval/results/latency_cost.json) |
| **Tail Total Latency ($p95$)** | `2.90 ms` | Local offline execution (CPU) | [`latency_cost.json`](eval/results/latency_cost.json) |
| **Mean Cost per Request** | `$0.000005` | Pricing registry model | [`latency_cost.json`](eval/results/latency_cost.json) |
| **1-Pass Direct Approvals** | `97.0%` | Offline mock critic pass | [`latency_cost.json`](eval/results/latency_cost.json) |
| **2+ Revisions Rate** | `3.0%` | Bounded self-reflection retry | [`latency_cost.json`](eval/results/latency_cost.json) |

#### Step-by-Step Latency Breakdown ($p50$ / $p95$ in Offline Mode)
- **Triage (Intent Classification & Risk Gates):** $0.12\text{ ms}$ / $0.23\text{ ms}$
- **Retrieval (`pgvector` HNSW Cosine Search):** $1.44\text{ ms}$ / $2.24\text{ ms}$
- **Drafting (Grounded Synthesis & Citation):** $0.03\text{ ms}$ / $0.13\text{ ms}$
- **PolicyGuard (URL Allowlist & PII Regex):** $0.03\text{ ms}$ / $0.06\text{ ms}$
- **Critic (QA Rubric Grading):** $0.07\text{ ms}$ / $0.18\text{ ms}$

---

### What These Numbers Do and Do Not Show

- **What they DO show:** Verified multi-agent state delegation under bounded retry loops, deterministic Tier 1 hazard escalation, dense semantic vector retrieval recall improvements over keyword overlap, and accurate per-step token/cost accounting.
- **What they DO NOT show:** Live cloud network latency (live LLM generation adds 300–800ms per network hop), human annotator consensus (Cohen's kappa was measured on an algorithmic 50-sample synthetic calibration dataset), or live cloud infrastructure availability (Cloud Run/SQL are target designs, not deployed).

---

## ☁️ Target Deployment Architecture (not deployed)

> **Deployment Status:** The GCP topology outlined below represents a documented target deployment architecture that has not yet been executed or deployed to live cloud infrastructure. Unit/integration tests, in-memory pgvector emulation, offline benchmarks, and the local FastAPI server run entirely in local development environments.

```mermaid
flowchart LR
    Client["Client Traffic"] --> CloudRun["Google Cloud Run\n(min=0, max=2, 512Mi, 1 vCPU)"]
    
    subgraph GCPInfrastructure ["Google Cloud Platform (us-central1)"]
        SecretMgr["Secret Manager\n(Mounted DB Secrets)"] --> CloudRun
        CloudRun -->|Cloud SQL Auth Proxy Socket| CloudSQL["Cloud SQL for PostgreSQL 16\n(pgvector + HNSW Index)"]
        CloudRun -->|REST / gRPC| VertexAI["Vertex AI\n(Gemini 1.5 Flash + text-embedding-004)"]
        CloudRun -->|OTel Tracing| CloudTrace["Google Cloud Trace\n(100% Audit Sampling)"]
        CloudRun -->|Structured Logs| CloudLogging["Google Cloud Logging\n(trace_id correlated)"]
    end
```

- **Serverless Compute:** Google Cloud Run with strict cost-safety parameters (`min-instances=0, max-instances=2`, 512MB RAM, 80s timeout).
- **Managed Vector Store:** Cloud SQL for PostgreSQL 16 with native `pgvector` accessed via the built-in Cloud SQL Auth Proxy Unix Domain Socket (`/cloudsql/<INSTANCE_NAME>`).
- **Security & IAM:** Dedicated least-privilege service account (`sa-support-agent`) with fine-grained roles (`aiplatform.user`, `cloudsql.client`, `secretmanager.secretAccessor`, `cloudtrace.agent`, `logging.logWriter`).
- **Keyless CI/CD:** GitHub Actions deployment pipeline using Google Cloud **Workload Identity Federation** (zero long-lived JSON keys).
- **Cost Safety Teardown:** Automated script ([`deploy/teardown.sh`](deploy/teardown.sh)) deletes billable Cloud SQL and Cloud Run resources with one command.

---

## 🚀 Quickstart & Local Execution

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/kamleshbarik05/verifiable-support-agent.git
cd verifiable-support-agent
make install
```

### 2. Run Test Suite & Lint Checks
```bash
# Run all 37 unit and integration tests
make test

# Verify code style and formatting
make lint
```

### 3. Launch Local API Server & Interactive Swagger UI
```bash
make serve
# Open http://127.0.0.1:8000/docs in your browser
```

### 4. Reproduce Benchmark Results on Demand
```bash
# Run 200-sample golden evaluation benchmark
make eval-v2

# Run vector retrieval A/B benchmark (v1 vs pgvector)
make eval-retrieval

# Run LLM-native latency & cost benchmark (100 samples)
make eval-latency-cost

# Regenerate publication markdown report from raw JSON
make report

# (Optional) Run live model evaluation sample against Gemini API (requires GEMINI_API_KEY)
make eval-live
```

---

## 🏛️ Architectural Decision Records (ADRs)

Key architectural trade-offs are documented in compliance with architecture standards:
- [**ADR 0001: Record Architecture Decisions**](docs/adr/0001-record-architecture-decisions.md) — Selection of version-controlled lightweight ADRs.
- [**ADR 0002: Vector Store Architecture**](docs/adr/0002-vector-store.md) — Why PostgreSQL `pgvector` with HNSW indexing was chosen over FAISS, Chroma, and Vertex Vector Search.
- [**ADR 0003: Multi-Agent System Topology**](docs/adr/0003-multi-agent-architecture.md) — Rationale for Google ADK hierarchical delegation with bounded self-reflection loops.
- [**ADR 0004: Observability, Tracing & Cost Accounting**](docs/adr/0004-observability-and-cost-tracing.md) — Local OpenTelemetry tracing, 100% uniform audit sampling, and strict PII scrubbing (Cloud Trace = design target only; see [`docs/tracing_guide.md`](docs/tracing_guide.md)).

---

## ⚖️ Known Limitations & Engineering Trade-offs

1. **Multi-Agent Sequential Latency:** While sub-3ms in offline deterministic mode, live Gemini API network round-trips add 300–800ms per generative LLM call. Mitigated by short-circuiting Tier 1 safety escalations before invoking drafting agents.
2. **Cloud SQL Cold Billing:** Cloud SQL bills hourly while provisioned. Addressed by authoring an automated teardown script (`deploy/teardown.sh`) and providing thread-safe in-memory cosine fallback for local dev.
3. **100% Audit Sampling Volume:** Recording 100% of traces (`ALWAYS_ON`) incurs trace ingestion volume, accepted as a necessary trade-off for auditable safety tracking.

---

## 📁 Repository Layout

```
.
├── app/
│   ├── agents/            # ADK sub-agents (Orchestrator, Triage, Retrieval, Draft, PolicyGuard, Critic)
│   ├── api/               # FastAPI endpoints (/triage, /health, /metrics)
│   ├── config.py          # Centralized model and environment configuration
│   ├── observability/     # OpenTelemetry tracing, span sanitization, and pricing tables
│   ├── retrieval/         # Vector store, embedder interface, and schema
│   ├── tools/             # Deterministic tool wrappers
│   └── v1/                # Preserved v1 baseline modules and reference code
├── deploy/                # Dockerfile and cloud provisioning runbooks (target architecture)
├── docs/                  # Architecture specs, requirements analysis, ADRs, and plans
│   ├── adr/               # Architectural Decision Records (0001 - 0004)
│   ├── architecture.md    # System architecture specification
│   ├── discovery.md       # Problem framing & domain requirements analysis
│   └── PLAN.md            # Master development plan
├── eval/
│   ├── datasets/          # Golden evaluation and calibration datasets
│   ├── results/           # Frozen machine-readable JSON evaluation outputs
│   └── runners/           # Benchmark runners (e2e, retrieval A/B, latency/cost, live eval)
└── tests/                 # 37 unit and integration tests (pytest)
```

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.
