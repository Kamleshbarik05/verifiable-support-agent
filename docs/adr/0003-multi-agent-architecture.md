# ADR 0003: Hierarchical Multi-Agent Topology and Bounded Self-Reflection Loop

## Status
Accepted

## Context
Enterprise customer support tickets require multiple distinct cognitive responsibilities:
1. Risk triage and safety screening.
2. Semantic historical precedent retrieval.
3. Grounded drafting with strict factual citations.
4. Deterministic policy and PII verification.
5. Quality assurance grading against brand rubrics.

In a monolithic single-prompt LLM design, instruction drift is common: the model often prioritizes conversational empathy over strict compliance, hallucinating URLs or failing to escalate hazardous hardware conditions.

Furthermore, naive autonomous multi-agent choreographies (where agents pass messages peer-to-peer without centralized control) frequently suffer from circular reasoning, non-deterministic execution times, and unbounded API cost.

## Decision

### 1. Multi-Agent Framework: Google Agent Development Kit (ADK)
We adopt **Google's Agent Development Kit (ADK)** architecture with structured tool use, standardized agent interfaces (`BaseAgent`), and strongly typed Pydantic state contracts (`AgentState`).

### 2. Orchestration Pattern: Hierarchical Delegation with Root Orchestrator
We select a **Hierarchical Delegation** pattern governed by an `OrchestratorAgent`.
- The Root Orchestrator owns the state lifecycle and deterministically coordinates sub-agent execution order: `TriageAgent` $\rightarrow$ `RetrievalAgent` $\rightarrow$ `DraftAgent` $\rightarrow$ `PolicyGuard` $\rightarrow$ `CriticAgent`.
- Sub-agents do not communicate peer-to-peer; all state transitions flow through the typed `AgentState` schema.
- **Immediate Short-Circuiting:** If `TriageAgent` identifies a critical safety hazard (e.g. smoking battery, legal threat) or public PII exposure, the Orchestrator halts execution immediately, avoiding unnecessary downstream vector queries and LLM generation costs.

### 3. Bounded Self-Reflection Loop (Max 2 Revisions)
To enforce quality without risking runaway latency or budget exhaustion:
- The drafting and critique loop (`DraftAgent` $\leftrightarrow$ `CriticAgent` / `PolicyGuard`) is strictly bounded to a maximum of **2 revision cycles** (`max_revisions = 2`).
- If a draft fails deterministic guardrails or QA rubric standards after 2 revision attempts, the Orchestrator safely routes the ticket to a human agent (`CRITIC_QUALITY_REVISION_EXHAUSTED` or `POLICY_GUARD_REVISION_EXHAUSTED`).
- This guarantees a hard ceiling on worst-case latency ($\le 3\times$ baseline) and token spend.

### 4. Deterministic Guardrails Outside the LLM
`PolicyGuard` runs as a native deterministic Python firewall:
- Customer PII (emails, phone numbers) is detected via regex before automated replies can be drafted.
- Every URL in drafted text is validated against an official Apple domain allowlist and verified against retrieved grounding documents.
- If an unauthorized link is generated, `PolicyGuard` exercises absolute veto authority and forces draft revision or human escalation.

## Consequences

### Positive
- **Predictable Cost & Latency:** Maximum 3 LLM calls per automated ticket, preventing runaway token bills.
- **Zero Hallucinated URLs:** Deterministic allowlisting and grounding checks catch 100% of fabricated links.
- **Auditable Provenance:** Every transition, critique feedback, and citation ID is preserved in `AgentState`.
- **Decoupled Testability:** Each sub-agent and tool can be unit-tested in complete isolation with deterministic mocks.

### Negative / Trade-offs
- Higher average latency than a single-pass pipeline when revisions are triggered (mitigated by fast Vertex AI Gemini 1.5 Flash inference).
- Requires strict synchronization of the Pydantic `AgentState` schema across all sub-agents.
