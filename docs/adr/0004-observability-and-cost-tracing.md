# ADR 0004: Observability, Distributed Tracing, and LLM Cost Accounting

## Status
Accepted

## Date
2026-11-23

## Context
Deploying multi-agent systems in enterprise customer support introduces operational risks:
1. **Latency Opacity:** Multi-agent architectures involve sequential handoffs and bounded self-reflection loops. Without distributed tracing, it is impossible to determine whether tail latency originates from vector search, LLM generation, or repetitive critic revisions.
2. **Cost Predictability:** Generative LLM architectures incur variable token-based expenses. Production teams require granular, step-by-step cost attribution to detect runaway token consumption.
3. **Data Governance & PII Protection:** In public support channels, customer tickets frequently leak personal email addresses, phone numbers, and account credentials. Storing unredacted customer inquiries in centralized observability backends (Cloud Trace, Jaeger, Datadog) violates GDPR, CCPA, and SOC2 compliance.
4. **Local OpenTelemetry Tracing & Cloud Trace Design Target:** Locally, local OpenTelemetry tracing exports to a local Jaeger container or stdout console. Google Cloud Trace is a target design only, never executed against live GCP.

## Decision

### 1. OpenTelemetry as the Instrumentation Standard
We adopt the vendor-neutral **OpenTelemetry (OTel)** specification rather than proprietary cloud SDKs.
- **Tracer Provider Configuration:** Configurable via the `OTEL_EXPORTER` environment variable:
  - `console`: Formatted local stdout span rendering for development.
  - `otlp`: OTLP span export to local collector (e.g. Jaeger container).
  - `gcp`: Export to Google Cloud Trace via `opentelemetry-exporter-gcp-trace` (target deployment design).
  - `none`: Lightweight in-memory span recorder with zero cloud or network dependencies, ensuring local unit tests and offline evaluation harnesses run in milliseconds without credentials.
- **W3C TraceContext Propagation:** All inbound requests receive or generate an explicit W3C `trace_id`, propagated through FastAPI headers (`X-Trace-ID`), sub-agent spans, and structured JSON logs.

### 2. 100% Uniform Trace Sampling (`ALWAYS_ON`)
We mandate **100% uniform trace sampling (`ALWAYS_ON`)** across all environments:
- **Rationale:** Customer support triage deals directly with safety hazards (battery fires, physical threats), legal escalation risks, and financial disputes. Dropping traces via probabilistic head sampling (e.g., 10%) risks losing the audit trail for critical safety escalations and policy violations.
- **Trade-off:** We consciously accept increased Cloud Trace ingestion volume in return for complete, non-repudiable auditability of every single customer interaction.

### 3. Strict PII Redaction & Data Governance
We enforce a hard data boundary between operational telemetry and customer personal data:
- **Zero Raw Queries in Spans:** Raw customer query text is **strictly forbidden** from OpenTelemetry span attributes.
- **Sanitized Attributes:** Span attributes record only operational dimensions: `intent`, `intent.confidence`, `tokens.input`, `tokens.output`, `tokens.per_second`, `cost.usd`, `step.latency_ms`, `revision_count`, and `query.char_length`.
- **Regex Scrubbing:** Any incidental string attribute containing email patterns (`[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+`) or phone patterns (`\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b`) is scrubbed automatically by `scrub_pii()` to `[REDACTED_EMAIL]` and `[REDACTED_PHONE]` before being committed to span memory.

### 4. Granular LLM-Native Step Telemetry
Each agent boundary (`TriageAgent`, `RetrievalAgent`, `DraftAgent`, `PolicyGuard`, `CriticAgent`) records a strongly typed `StepMetric`:
- `latency_ms`: Step execution time in milliseconds.
- `input_tokens` and `output_tokens`: Token consumption.
- `tokens_per_second`: Generative drafting velocity ($N_{\text{output}} / \Delta t$).
- `estimated_cost_usd`: Dollar cost computed via versioned Vertex AI pricing tables in `app/observability/cost_model.py`.

### 5. Google Cloud Logging & Cloud Trace Correlation (Target Architecture)
Structured JSON logs emitted by the application include the standard GCP trace field:
```json
{
  "event": "triage_completed",
  "ticket_id": "ticket_1001",
  "logging.googleapis.com/trace": "projects/<PROJECT_ID>/traces/<TRACE_ID>",
  "latency_ms": 1.7,
  "cost_usd": 0.000042
}
```
This enables one-click navigation between Cloud Logging and Cloud Trace in the Google Cloud Console.

## Consequences

### Positive
- **White-box Auditing:** Engineers can pinpoint exact latency bottlenecks across Triage, Vector Retrieval, LLM Drafting, Guardrail validation, and Critic scoring.
- **Cost Transparency:** Every response payload exposes exact token and cost breakdowns, preventing unexpected billing surprises.
- **Compliance Guarantee:** Zero PII leakage into distributed trace storage.

### Negative / Trade-offs
- **Ingestion Volume:** 100% trace sampling incurs higher Cloud Trace ingestion costs at enterprise volume, which can be mitigated in future phases via Cloud Trace rate-limiting quotas or tail-based sampling proxies.
