# Problem Framing & Requirements Analysis (no stakeholder interview conducted)

> **Context Note:** No live stakeholder interview was conducted. This requirements analysis and technical specification is derived entirely from empirical analysis of the public `@AppleSupport` customer inquiry dataset and domain analysis of automated customer support failure modes.

---

## 1. Context & Data Profile
- **Dataset:** Public `@AppleSupport` Twitter customer inquiry dataset (Kaggle Customer Support on Twitter).
- **Communication Channel:** Public social media mentions requiring rapid triage, risk routing, and grounded resolution drafting.
- **Inquiry Profile:** Heterogeneous customer inquiries spanning hardware defects, software/OS troubleshooting, Apple ID authentication, and billing/refund requests.

---

## 2. Problem Statement
When deploying generative AI models on customer support channels, unstructured text synthesis creates significant operational and liability risks:
1. **Hallucinated URLs & Policies:** LLMs frequently invent non-existent support URLs or misstate warranty/repair policies.
2. **Safety & Hazard Blindness:** LLMs attempt conversational troubleshooting on physical device hazards (e.g., swollen or smoking lithium-ion batteries) instead of halting automation immediately.
3. **Public PII Exposure:** Customers frequently tweet personal email addresses, phone numbers, or account details into public channels.
4. **Latency & Cost Runaway:** Unbounded iterative drafting or multi-step agent loops risk latency spikes and unpredictable token costs.

---

## 3. Ground Truth & Data Sources
- **Historical Precedent Store:** Verified historical customer support interaction pairs extracted from the dataset, embedded into 768-dimensional dense vectors and indexed for nearest-neighbor similarity search.
- **URL Allowlist Domain Registry:** Deterministic set of authorized domain prefixes (`support.apple.com`, `apple.com`, `reportaproblem.apple.com`).

---

## 4. Deterministic Risk Tiers & Escalation Boundaries
Inquiries are categorized into strict risk tiers before drafting:
- **Tier 1 (Critical Safety & Legal Guardrail — Immediate Escalation):**
  - Physical device hazards (smoking batteries, device thermal runaway, explosions).
  - Legal threats, regulatory compliance claims, and public PII leakage.
  - *Action:* Hard escalation to human safety specialists; zero automated LLM reply generation.
- **Tier 2 (Policy, Financial & Quality Gate):**
  - Financial refunds, unauthorized payment disputes, and account security lockouts.
  - Ambiguous inquiries where intent classification confidence falls below 0.70 or vector retrieval similarity falls below 0.50.
  - *Action:* Human escalation with triage metadata and reason codes.
- **Tier 3 (Standard Diagnostic — Eligible for Grounded Drafting):**
  - Technical diagnostic and feature how-to questions backed by verified retrieval precedent.

---

## 5. Success Metrics
- **Hallucinated URL Rate:** 0.0% (strictly enforced via deterministic URL allowlist and citation verification).
- **Escalation Recall:** $\ge 85\%$ on physical hazard, legal, and financial risk triggers.
- **Grounding Gate:** Reject synthesis if retrieval cosine similarity is $< 0.50$.
- **Bounded Reflection Loop:** Max 2 revision attempts before falling back to human escalation.

---

## 6. Architectural Decision Traceability
These requirements directly informed the architectural decisions documented in ADRs:
- [ADR 0001: Record Architecture Decisions](adr/0001-record-architecture-decisions.md)
- [ADR 0002: Vector Store Architecture](adr/0002-vector-store.md)
- [ADR 0003: Multi-Agent System Topology](adr/0003-multi-agent-architecture.md)
- [ADR 0004: Observability, Tracing & Cost Accounting](adr/0004-observability-and-cost-tracing.md)
