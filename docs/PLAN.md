# PLAN.md — Verifiable Support Agent v2 (Multi-Agent, Vector Search, GCP)

> **How to use this file in Google Antigravity**
> 1. Copy your existing `verifiable-support-agent` repo to a new folder (or branch `v2`) and open it as the workspace.
> 2. Save this file as `PLAN.md` in the repo root.
> 3. Paste **Section 0 (Agent Rules)** into the workspace rules (or the first message of the session). Check Antigravity's docs for where workspace rules live in your version.
> 4. Run one **Phase prompt** at a time (Sections 4.1–4.8). Review the plan and diffs the agent produces before approving the next phase.
> 5. Do the **human tasks** in Section 3 yourself; the agent cannot do them.
>
> Product names, model IDs, and CLI flags change. The rules below tell the agent to check current official docs before using any of them.

---

## 0. AGENT RULES (paste first)

```
You are helping me build "Verifiable Support Agent v2" as a portfolio project for a Google Cloud Forward Deployed Engineer internship. Follow these rules for the whole project.

1. Read PLAN.md fully before acting. Work on ONE phase at a time. Before coding, show me a short implementation plan and wait for my approval.
2. Language and style: Python 3.11, type hints, small modules, pytest tests for every new module. Use ruff for lint. Keep functions short and documented.
3. Never invent metrics. Every number that goes in the README or resume must come from a script in /eval that I can re-run. Save raw results to /eval/results/*.json with the git commit hash and timestamp.
4. Never hardcode secrets. Use environment variables locally (.env, git-ignored) and Secret Manager on GCP. Commit a .env.example only.
5. Before using any Google Cloud, Vertex AI, ADK, or pgvector API, flag, or model name, check the current official documentation and use what it says today. If docs and PLAN.md disagree, tell me and follow the docs.
6. Keep cloud cost minimal: smallest instance sizes, Cloud Run max-instances=2, min-instances=0, and tell me every resource you create so I can delete it later.
7. Preserve the existing v1 behavior (intent classifier, deterministic PII/safety guardrails, golden set, LLM judge). Reuse v1 code; do not rewrite what already works.
8. After each phase: run tests, run the relevant eval, update docs/ADRs, and give me a short walkthrough listing files changed, commands to reproduce, and results.
9. If something is ambiguous or requires my account, billing, or a real stakeholder, stop and ask instead of guessing.
```

---

## 1. Goal and success criteria

**Goal:** Turn the v1 support-triage pipeline into a production-style multi-agent system that uses a vector database, is deployed on Google Cloud, is traced and measured, and is backed by a written discovery document.

**Why (maps to the JD gaps):**

| JD gap | Evidence this project produces |
|---|---|
| GCP | Cloud Run + Vertex AI (Gemini) + Cloud SQL + Secret Manager + Cloud Logging/Trace + CI/CD deploy |
| Vector databases | Embeddings + pgvector (Cloud SQL), A/B vs v1 retrieval |
| Multi-agent frameworks | Google ADK orchestrator with sub-agents, tool use (ReAct-style), self-reflection loop |
| Technical discovery | `docs/discovery.md` from a real stakeholder interview, plus ADRs |
| LLM-native metrics | tokens/sec, cost per request, p50/p95 latency per agent step |

**Done means:**
- [ ] Public GitHub repo with README, architecture diagram, ADRs, discovery doc
- [ ] Service deployed on Cloud Run, reachable via a demo URL (or recorded demo if cost requires shutdown)
- [ ] `make eval` reproduces all headline metrics from raw result files
- [ ] CI runs tests + eval smoke test; deploy workflow works from GitHub Actions
- [ ] Resume bullets filled with real numbers from `/eval/results`

---

## 2. Target architecture

```
Client (curl / small web UI)
        |
   FastAPI  (/triage, /health, /metrics)
        |
   ADK Root Agent: "Orchestrator"   <-- hierarchical delegation
        |
        +--> TriageAgent      tool: classify_intent (v1 sklearn model), risk_gate (v1 guardrails)
        +--> RetrievalAgent   tool: search_resolutions (embeddings -> pgvector, top-k)
        +--> DraftAgent       grounded response draft using retrieved resolutions only
        +--> PolicyGuard      tool: pii_check, url_allowlist_check (deterministic) + LLM review
        +--> CriticAgent      scores draft with v1 judge rubric; loop max 2 retries (self-reflection)
        |
   Observability: OpenTelemetry -> Cloud Trace; structured logs -> Cloud Logging;
                  per-step tokens, latency, cost recorded via ADK callbacks
        |
   Data: Cloud SQL (Postgres + pgvector) for resolution embeddings; Secret Manager for config
   LLM: Gemini via Vertex AI (model ID checked in current docs)
```

**Design notes (put these in ADRs):**
- Deterministic guardrails stay outside the LLM and have final say (same principle as v1).
- Escalation: if TriageAgent risk gate says high-risk or confidence is below threshold, skip drafting and return `escalate_to_human` with reasons.
- The self-reflection loop is bounded (max 2 retries) so latency and cost stay predictable.
- "ReAct-style" = the agent reasons, calls a tool, observes the result, and continues. Describe it that way in the README; don't overclaim a custom ReAct implementation.

---

## 3. Human tasks (you must do these; the agent cannot)

### 3.1 GCP setup (about 1 hour)
1. Create a Google Cloud project and link billing (new-account credits may apply; confirm current offers).
2. **Create a billing budget with alerts first** (for example 50%, 90%, 100% of a small amount).
3. Install and authenticate the `gcloud` CLI: `gcloud auth login`, `gcloud auth application-default login`.
4. Enable the APIs the agent lists in Phase 6 when it asks (Vertex AI, Cloud Run, Cloud SQL Admin, Secret Manager, Artifact Registry, Cloud Build, Cloud Trace, Cloud Logging).
5. Note your PROJECT_ID and preferred region. Pick a region where your chosen Gemini model is available.

### 3.2 Technical discovery (real evidence, about 1 week elapsed)
1. Choose a stakeholder with a real support or inquiry workflow: a campus office, club, professor, a local business, or a friend running a small online store.
2. Hold a 30–45 minute session. Questions to ask:
   - What requests do you get most, and how many per week?
   - Which are easy, which are risky (money, personal data, complaints)?
   - Where do answers live today (docs, chats, spreadsheets)? How current are they?
   - What would a wrong answer cost you? What must never be auto-answered?
   - How would you judge a good draft? What would make you trust it?
   - What tools and constraints exist (data privacy, budget, approval steps)?
3. Take notes. Get permission to describe the session (anonymize if needed).
4. Fill `docs/discovery.md` (template in Phase 0). If a stakeholder is not possible, say so honestly and describe the v1 AppleSupport dataset as the use case; do not label it a customer interview.

### 3.3 Verification you must do yourself
- Read every ADR and be able to explain each decision aloud.
- Re-run `make eval` yourself before putting numbers on the resume.

---

## 4. Phases and paste-ready prompts

Estimated effort: 5–6 weeks part-time. Each prompt below is meant to be pasted as-is.

### 4.0 Phase 0 — Discovery doc and repo hygiene (Week 1)

**Deliverables:** `docs/discovery.md`, `docs/adr/0001-record-architecture-decisions.md`, repo structure, `Makefile`, `.env.example`, CI skeleton.

**Target repo structure:**
```
app/
  api/            # FastAPI routes
  agents/         # ADK agents (orchestrator, triage, retrieval, draft, policy, critic)
  tools/          # classify_intent, risk_gate, search_resolutions, pii_check, url_check
  retrieval/      # embedding client, vector store, ingestion
  observability/  # tracing, metrics callbacks, cost model
  v1/             # existing v1 code moved here, unchanged behavior
eval/
  datasets/       # golden set (v1), retrieval eval set
  runners/        # retrieval_eval.py, e2e_eval.py, latency_cost_eval.py
  results/        # raw JSON outputs (committed)
docs/
  discovery.md, architecture.md, adr/
deploy/
  Dockerfile, cloudrun.md, scripts/
tests/
Makefile, README.md, PLAN.md, .env.example
```

**`docs/discovery.md` template (agent should create it empty; you fill it in):**
```
# Technical Discovery
## Stakeholder and context (who, role, date, format of session)
## Problem statement
## Users and volumes
## Current workflow and pain points
## Data sources (what exists, format, freshness, sensitivity)
## Constraints (privacy, budget, approvals, tooling)
## Risk tiers (what may be auto-drafted vs must be escalated)
## Success metrics (as stakeholder defines them)
## Open questions and assumptions
## How findings changed the design (link ADRs)
```

**Prompt to paste:**
```
Phase 0. Inspect the repo and summarize v1: modules, tests, golden set, judge, guardrails, how to run it. Then propose a refactor that moves v1 into app/v1 without changing behavior and creates the folder structure in PLAN.md Section 4.0. Add: Makefile targets (install, test, lint, eval, run, docker-build), .env.example, ruff config, a GitHub Actions workflow running lint + tests, docs/discovery.md as an empty template with the headings in PLAN.md, and ADR 0001. Show me the plan first. After approval implement it, run all v1 tests to prove nothing broke, and give me a walkthrough.
```

**Acceptance:** all v1 tests still pass; `make test` and `make lint` work; CI is green.

---

### 4.1 Phase 1 — Baseline and evaluation harness (Week 1–2)

**Why first:** you cannot claim improvement without a frozen baseline.

**Deliverables:** `eval/runners/e2e_eval.py`, `eval/results/baseline_v1.json`.

**Metrics to record for v1 (re-run, don't copy from the resume):** Intent Macro-F1, escalation False Negative Rate, judge pass rate on the 200-sample golden set, Cohen's κ vs human labels, hallucinated URL/policy rate, p50/p95 latency, and cost per request if the judge calls an LLM.

**Prompt to paste:**
```
Phase 1. Build a reproducible evaluation harness around the v1 pipeline. Create eval/runners/e2e_eval.py that runs the 200-sample golden set through v1 and writes eval/results/baseline_v1.json with: intent macro-F1, escalation false negative rate, judge pass rate, Cohen's kappa against the human labels, hallucinated-URL/policy rate (URLs or policy claims in drafts not present in the retrieved sources), p50/p95 latency, and cost per request (token counts x a configurable price table in app/observability/cost_model.py; leave prices in a config file with a source comment and date). Include git commit hash, timestamp, and model name in the output. Add a `make eval-baseline` target and pytest smoke tests that run the harness on 5 samples without network calls (use recorded fixtures or mocks). Do not change v1 logic. Show the plan first.
```

**Acceptance:** `make eval-baseline` writes a JSON file; numbers roughly match what v1 reported (investigate if they don't, and tell me why).

---

### 4.2 Phase 2 — Embeddings and vector database (Week 2)

**Deliverables:** `app/retrieval/{embedder.py,vector_store.py,ingest.py}`, a pgvector schema/migration, `eval/runners/retrieval_eval.py`, `eval/results/retrieval_ab.json`, ADR 0002 (vector store choice).

**Plan:**
- Local dev: Docker `pgvector/pgvector` Postgres image via `docker-compose.yml`.
- Embeddings: Vertex AI text embedding model (check current model name and dimensions in docs). Allow a local fallback embedder behind the same interface for offline tests.
- Schema: `resolutions(id, brand_text, issue_text, resolution_text, intent, embedding vector(N), source_hash)` with an approximate-nearest-neighbor index (HNSW or IVFFlat; justify in the ADR).
- Retrieval eval set: 100+ queries each labeled with the correct resolution(s). Build it from the golden set and have the agent propose labels that you review manually.

**Prompt to paste:**
```
Phase 2. Add a vector retrieval layer. 1) Define an Embedder interface with a Vertex AI implementation (check current docs for the model name and output dimension) and a deterministic local fake for tests. 2) Add docker-compose.yml with pgvector Postgres, a SQL migration creating a resolutions table with a vector column and an ANN index (explain HNSW vs IVFFlat in docs/adr/0002-vector-store.md, comparing pgvector on Cloud SQL, Vertex AI Vector Search, and FAISS/Chroma, and justify choosing pgvector). 3) Write ingest.py that embeds the historical brand resolutions from the dataset in batches, is idempotent via source_hash, and logs counts. 4) Write search_resolutions(query, k, intent=None) with optional metadata filtering. 5) Build eval/runners/retrieval_eval.py comparing v1 retrieval vs vector retrieval on a labeled query set (Recall@1/3/5, MRR, p50/p95 latency) and writing eval/results/retrieval_ab.json. Show the plan first, then implement, run the eval, and report results honestly even if v1 retrieval wins on some metrics.
```

**Acceptance:** retrieval A/B JSON exists; ADR explains trade-offs; tests pass without network.

---

### 4.3 Phase 3 — Multi-agent system with Google ADK (Week 3)

**Deliverables:** `app/agents/*`, `app/tools/*`, ADR 0003 (why ADK, orchestration pattern), unit tests with mocked LLM.

**Agent responsibilities:**

| Agent | Role | Tools |
|---|---|---|
| Orchestrator (root) | Decides the path, delegates to sub-agents, assembles final JSON | sub-agents |
| TriageAgent | Intent + risk classification, escalation decision | `classify_intent`, `risk_gate` (v1 code wrapped as tools) |
| RetrievalAgent | Finds grounding resolutions | `search_resolutions` |
| DraftAgent | Writes reply using only retrieved content, cites resolution IDs | none |
| PolicyGuard | Deterministic PII/URL/policy checks plus LLM review | `pii_check`, `url_allowlist_check` |
| CriticAgent | Scores draft with the judge rubric, returns pass or revise-with-feedback | `judge_score` |

**Control flow:** Orchestrator -> Triage -> (escalate? return) -> Retrieval -> Draft -> PolicyGuard -> Critic -> (revise? loop to Draft with critic feedback, max 2) -> return final response with citations and trace ID.

**Prompt to paste:**
```
Phase 3. Implement the multi-agent system with Google's Agent Development Kit (ADK) for Python. Check current ADK docs first for install name, agent classes, sub-agent delegation, tool definition, loop/sequential agents, and callbacks. Build the agents in PLAN.md Section 4.3: Orchestrator (root agent delegating via sub_agents), TriageAgent, RetrievalAgent, DraftAgent, PolicyGuard, CriticAgent with a bounded self-reflection loop (max 2 revisions, exit when the critic passes). Wrap existing v1 functions as tools (classify_intent, risk_gate, judge_score, pii_check, url_allowlist_check) without changing their logic. Deterministic guardrails must override LLM output: if pii_check or url_allowlist_check fails, the draft is blocked or regenerated. Use structured (JSON-schema) outputs between agents. Gemini is called via Vertex AI (configure through env vars, no keys in code). Write unit tests with a mocked model that cover: escalation path, normal path, one-revision path, guardrail-block path. Add ADR 0003 explaining the architecture, why hierarchical delegation, and why the loop is bounded. Show the plan first.
```

**Acceptance:** tests cover four paths; a local `adk run`/dev-UI session (check docs) or script processes a sample ticket end to end.

---

### 4.4 Phase 4 — FastAPI service and end-to-end eval (Week 3–4)

**Deliverables:** `app/api/main.py` with `/triage`, `/health`, `/metrics`; e2e eval for v2; `eval/results/e2e_v2.json`.

**Prompt to paste:**
```
Phase 4. Wrap the orchestrator in a FastAPI service. Endpoints: POST /triage (input: ticket text and optional metadata; output: intent, risk, decision (draft or escalate), draft with cited resolution IDs, critic verdict, trace_id, and per-step latency/tokens/cost), GET /health, GET /metrics (simple JSON or Prometheus text). Add request validation, timeouts, structured JSON logging with trace_id, and a request-size limit. Then extend eval/runners/e2e_eval.py to run v2 on the same 200-sample golden set and write eval/results/e2e_v2.json using the same metrics as baseline_v1.json, plus a comparison script `make eval-compare` that prints a v1 vs v2 table (macro-F1, FNR, judge pass rate, hallucinated URL rate, kappa, p50/p95 latency, cost per request). Report honestly if v2 is worse on any metric and explain the trade-off. Show the plan first.
```

**Acceptance:** `make eval-compare` prints a table from two result files. Expect higher latency and cost than v1 (more LLM calls). Your story is quality and groundedness vs cost, not "everything improved".

---

### 4.5 Phase 5 — Observability and LLM-native metrics (Week 4)

**Deliverables:** `app/observability/*`, per-step metrics, tracing, ADR 0004, `eval/runners/latency_cost_eval.py`.

**Metrics per agent step:** input/output tokens, latency, output tokens/sec, estimated cost, retries, guardrail blocks. **Per request:** total cost, p50/p95 latency, loop iterations.

**Prompt to paste:**
```
Phase 5. Add observability. Use ADK callbacks (check current docs) to record per-step model name, input/output tokens from usage metadata, latency, output tokens/sec, and estimated cost via app/observability/cost_model.py (price table in config, with source and date). Add OpenTelemetry tracing with spans per agent and tool call; make the exporter configurable: console locally, Google Cloud Trace on GCP. Emit structured logs with trace_id so they correlate in Cloud Logging. Include the per-step breakdown in the /triage response and aggregate p50/p95 in /metrics. Add eval/runners/latency_cost_eval.py that runs 100 requests and writes eval/results/latency_cost.json (cost per request, tokens/sec, p50/p95 by step, share of requests needing 0/1/2 revisions). Add ADR 0004 on what we trace, what we deliberately don't log (PII), and sampling. Show the plan first.
```

**Acceptance:** you can answer "where does latency and cost come from?" using the breakdown.

---

### 4.6 Phase 6 — Deploy to GCP (Week 4–5)

**Deliverables:** `deploy/Dockerfile`, `deploy/cloudrun.md`, GitHub Actions deploy workflow, Cloud SQL instance with pgvector, Secret Manager entries, working demo URL.

**Prompt to paste:**
```
Phase 6. Prepare and document deployment to Google Cloud. Check current official docs for every command. 1) Write a minimal multi-stage Dockerfile (non-root user, no secrets baked in). 2) Write deploy/cloudrun.md with step-by-step gcloud commands for: enabling required APIs; creating an Artifact Registry repo; creating the smallest Cloud SQL for PostgreSQL instance and enabling pgvector; storing config in Secret Manager; creating a dedicated service account with least-privilege roles (Vertex AI user, Cloud SQL client, secret accessor, trace agent, log writer); deploying to Cloud Run with max-instances=2, min-instances=0, a request timeout, and connecting to Cloud SQL securely. 3) Add a script to run migrations and ingestion against Cloud SQL. 4) Add a GitHub Actions deploy workflow using Workload Identity Federation (no long-lived JSON keys) triggered on tags or manual dispatch, which builds, pushes, and deploys. 5) Add a smoke test script that calls /health and /triage on the deployed URL. 6) List every cloud resource created and a teardown script/commands. Do NOT run commands that create billable resources yourself; output them for me to review and run. Show the plan first.
```

**You do:** review each command, run them, confirm the budget alert exists, then run the smoke test. Take screenshots of Cloud Run, Cloud Trace and Cloud Logging for the README.

**Cost safety:** Cloud SQL bills while the instance exists. After recording the demo and metrics, stop or delete it (the teardown script), and keep screenshots + a short screen recording in the README. Check current pricing and free-tier limits before you start.

**Acceptance:** `/triage` works on the public URL; traces appear in Cloud Trace; logs show `trace_id`.

---

### 4.7 Phase 7 — Documentation and portfolio polish (Week 5–6)

**Prompt to paste:**
```
Phase 7. Write the portfolio documentation. README.md: one-paragraph problem statement tied to docs/discovery.md; architecture diagram (Mermaid) matching the real code; quickstart (local with docker-compose, and cloud deploy pointer); results table generated from eval/results/*.json by a script (v1 vs v2: quality, groundedness, latency, cost); a "What I'd do next" and "Known limitations" section that is honest; screenshots placeholders for Cloud Run, Trace, Logs. Update docs/architecture.md and make sure every ADR has context, decision, consequences. Add a `make report` target that regenerates the results table. Do not include any number that is not read from a results file. Finally, list the exact resume bullets I can make with the real numbers, and flag any claim that is not fully supported by evidence.
```

---

### 4.8 Phase 8 — Interview-readiness check (Week 6, you + agent)

**Prompt to paste:**
```
Act as a Google Cloud FDE interviewer. Based on this repo, ask me 25 hard questions across: multi-agent design (why this delegation structure, failure modes, loops), vector search (index choice, recall vs latency, chunking, embedding drift), GCP (IAM, Cloud Run cold starts, Cloud SQL connectivity, cost), evaluation (judge bias, kappa meaning, metric choice), observability, and customer discovery (how I gathered requirements and how it changed the design). Ask one at a time, wait for my answer, then critique it and point to the file in this repo that supports or contradicts my answer.
```

---

## 5. Metrics to collect (fill from `/eval/results`, never from memory)

| Metric | v1 baseline | v2 | Source file |
|---|---|---|---|
| Intent Macro-F1 | | | e2e_*.json |
| Escalation False Negative Rate | | | e2e_*.json |
| Judge pass rate (200-sample golden set) | | | e2e_*.json |
| Cohen's kappa (judge vs human) | | | e2e_*.json |
| Hallucinated URL/policy rate | | | e2e_*.json |
| Retrieval Recall@3 / MRR | | | retrieval_ab.json |
| p50 / p95 latency (ms) | | | latency_cost.json |
| Cost per request ($) | | | latency_cost.json |
| Output tokens/sec | | | latency_cost.json |
| Requests needing 0/1/2 revisions | | | latency_cost.json |

---

## 6. Resume bullet templates (fill only after the evidence exists)

**Project line:**
`Support Agent v2 (Multi-Agent, GCP) | Python, Google ADK, Gemini (Vertex AI), pgvector, Cloud Run, Cloud Trace | GitHub Repository | Live Demo | CI/CD`

- Built a hierarchical multi-agent triage system (orchestrator, retrieval, drafting, policy-guard, critic agents) with a bounded self-reflection loop, improving **[metric]** from **[X]** to **[Y]** on a 200-sample golden set.
- Replaced keyword retrieval with embeddings + **pgvector** on Cloud SQL, raising Recall@3 from **[X]** to **[Y]**, and cut hallucinated URL/policy rate from **[X]** to **[Y]**.
- Deployed on **Cloud Run** with Gemini on **Vertex AI**, OpenTelemetry tracing to **Cloud Trace**, and GitHub Actions CI/CD; **~$[X] per request**, **p95 [Y] ms**, **[Z] output tokens/sec**.
- Ran a stakeholder discovery session and translated requirements into risk tiers and escalation rules, documented in ADRs.

Add to Skills: `Google Cloud Platform (Cloud Run, Vertex AI, Cloud SQL, Cloud Trace)`, `Google ADK`, `Vector Database (pgvector)`, `Embeddings`, `Multi-Agent Systems`, `OpenTelemetry`.

Only add the discovery bullet if you actually ran the session.

---

## 7. Risks and how to handle them

| Risk | Mitigation |
|---|---|
| v2 is slower or costlier than v1 | Expected. Report the trade-off; show the cost/latency breakdown and what you'd optimize (caching, smaller model for triage, parallel calls). |
| ADK API changes break generated code | Rule 5: agent checks current docs; pin versions in `requirements.txt`. |
| Cloud costs | Budget alerts, max-instances=2, teardown script, stop Cloud SQL after demo. |
| Agent produces untestable claims | Rule 3: all numbers from `/eval/results`. |
| Time runs out | Priority order: (1) GCP deploy, (2) vector DB, (3) ADK multi-agent, (4) discovery doc. Required qualifications come first. |
| Over-claiming on resume | Add a keyword only if you can explain it in an interview (Phase 8). |

---

## 8. Final checklist before updating the resume

- [ ] `make eval` reproduces every number from raw files
- [ ] Demo URL or recording works; README has screenshots
- [ ] ADRs 0001–0004 written and understood
- [ ] `docs/discovery.md` reflects a real conversation (or honestly states it was not possible)
- [ ] Cloud resources torn down or budget alert confirmed
- [ ] Resume updated with real numbers, one page
