# Local OpenTelemetry Distributed Tracing Guide

This guide describes how to configure, execute, and inspect distributed trace waterfalls locally using **OpenTelemetry (OTel)** and **Jaeger**.

> **Architecture Honesty Note:**
> Live Google Cloud Trace integration is a **target deployment design** that has never been executed on Google Cloud. Distributed tracing in this repository runs locally via OpenTelemetry exporting to a local Jaeger container (or local stdout console fallback).

---

## 1. Quickstart: Start Jaeger Locally

The repository includes a pre-configured Jaeger all-in-one container in `docker-compose.yml`.

Start the Jaeger container in the background:
```bash
docker-compose up -d jaeger
```

Verify that the Jaeger UI is accessible:
- **Jaeger UI:** [http://localhost:16686](http://localhost:16686)
- **OTLP HTTP Receiver:** `http://localhost:4318/v1/traces`
- **OTLP gRPC Receiver:** `localhost:4317`

---

## 2. Configuration & Exporter Modes

Tracing behavior is controlled by the `OTEL_EXPORTER` environment variable:

| Mode | Target | Description |
| :--- | :--- | :--- |
| `otlp` or `jaeger` | `http://localhost:4318/v1/traces` | Exports spans via standard OTLP HTTP to local Jaeger. |
| `console` | `stdout` | Formatted terminal output for immediate span debugging. |
| `none` (default) | In-memory | Zero-network in-memory recording for tests and offline evals. |
| `gcp` | Google Cloud Trace | **Design target only** (requires GCP credentials, never executed). |

### Set Environment Variables
```bash
# Export to local Jaeger container
export OTEL_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces

# Or on Windows PowerShell:
$env:OTEL_EXPORTER="otlp"
$env:OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318/v1/traces"
```

*Note: If the Jaeger container is not running, the tracer catches the connection error and automatically falls back to `console` stdout logging without crashing the application.*

---

## 3. Generate a Distributed Trace

### Option A: Via FastAPI Endpoint
Start the local API server:
```bash
make serve
```

Send a sample customer support query:
```bash
curl -X POST http://127.0.0.1:8000/triage \
  -H "Content-Type: application/json" \
  -d '{"customer_query": "My AirPods Pro will not pair with my iPhone after the iOS update."}'
```

The response includes the unique `trace_id` in both the JSON payload and the `X-Trace-ID` HTTP header:
```json
{
  "ticket_id": "ticket_1700812345",
  "trace_id": "trace_7a8b9c1d2e",
  "intent": "HARDWARE_CONNECTIVITY",
  "should_escalate": false,
  "drafted_reply": "Try resetting your AirPods: place them in the case...",
  "citations": ["res_2841"],
  "total_cost_usd": 0.000018
}
```

### Option B: Via Python One-Liner
```bash
python -c "
import os
os.environ['OTEL_EXPORTER'] = 'console'
from app.agents.orchestrator import OrchestratorAgent
orchestrator = OrchestratorAgent()
state = orchestrator.process_ticket('My AirPods Pro will not pair with my iPhone.')
print('Generated Trace ID:', state.trace_id)
"
```

---

## 4. Trace Hierarchy & Span Waterfall

When an inbound inquiry is processed, `OrchestratorAgent` coordinates hierarchical sub-agent execution, creating a parent-child span waterfall:

```
[Trace: trace_7a8b9c1d2e]
 └── OrchestratorAgent.process_ticket (Root Span)
      ├── TriageAgent.classify_and_route
      │    └── deterministic_regex_risk_gate
      ├── RetrievalAgent.dense_vector_search
      │    └── pgvector_hnsw_cosine_query
      ├── DraftAgent.synthesize_draft (draft_revision_0)
      │    └── llm_generate_content
      ├── PolicyGuard.enforce_guardrails (policy_guard_pass_0)
      │    ├── deterministic_pii_sanitization_gate
      │    └── deterministic_url_allowlist_validator
      └── CriticAgent.grade_and_review (critic_pass_0)
           └── rubric_groundedness_evaluation
```

### Span Details & Attributes

1. **`OrchestratorAgent.process_ticket` (Root)**
   - `ticket_id`: Unique ticket identifier.
   - `trace_id`: W3C distributed trace ID.
   - `escalated`: Whether the ticket was escalated to human tier.
   - `total_cost_usd`: Aggregate LLM token expenditure.
   - `revision_count`: Number of reflection cycles (0, 1, or 2).

2. **`TriageAgent.classify_and_route`**
   - `intent`: Identified customer intent category (e.g., `HARDWARE_CONNECTIVITY`).
   - `intent.confidence`: Classification probability score.
   - `hazard.detected`: Boolean safety indicator (battery swelling, physical threats).

3. **`RetrievalAgent.dense_vector_search`**
   - `retrieval.k`: Number of nearest neighbors retrieved ($k=3$).
   - `retrieval.max_similarity`: Cosine similarity score of top precedent.
   - `retrieval.model`: Active embedding model (`gemini-embedding-001` or fallback).

4. **`DraftAgent.synthesize_draft`**
   - `step_name`: `draft_revision_0` (or `_1`, `_2` during reflection).
   - `model_name`: Active LLM model name.
   - `input_tokens` & `output_tokens`: Token consumption for generation.
   - `tokens_per_second`: Generative token throughput velocity.
   - `estimated_cost_usd`: Dollar cost per pricing registry.

5. **`PolicyGuard.enforce_guardrails`**
   - `policy.passed`: True if zero PII was leaked and all URLs match allowlist.
   - `guardrail.type`: `PII` or `URL_ALLOWLIST`.

6. **`CriticAgent.grade_and_review`**
   - `rubric.groundedness`: 1–5 score against retrieved historical precedents.
   - `rubric.actionability`: 1–5 score for actionable troubleshooting path.
   - `rubric.brand_tone`: 1–5 score for empathy and concise brand voice.
   - `rubric.safety_pass`: Boolean compliance verdict.

---

## 5. Data Governance & PII Redaction

To prevent PII leakage into centralized observability backends:
- **Zero Raw Prompts in Spans:** Raw customer query text is **never** added to span attributes.
- **Automated Scrubbing:** Any incidental string passed to span attributes is sanitized via `scrub_pii()`, replacing emails and phone numbers with `[REDACTED_EMAIL]` and `[REDACTED_PHONE]`.
- **Audit Compliance:** 100% uniform trace sampling (`ALWAYS_ON`) guarantees complete, non-repudiable audit logs for all safety escalations without capturing private consumer data.
