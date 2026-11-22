# Technical Discovery

## Stakeholder and Context
*(Who was interviewed, their role, date of session, format: e.g. 45-min Zoom / in-person interview, organization / business)*

## Problem Statement
*(Clear statement of the operational or technical problem the stakeholder faces)*

## Users and Volumes
*(Who submits inquiries, typical weekly/monthly volume, peak spikes, communication channels)*

## Current Workflow and Pain Points
*(Step-by-step description of how tickets/inquiries are handled today, bottlenecks, time lost, error rates)*

## Data Sources
*(Where ground-truth answers live today, format, update frequency, access permissions, sensitivity)*

## Constraints
*(Hard constraints around customer privacy/PII, cloud budget, human sign-off policies, technical dependencies)*

## Risk Tiers
*(Explicit boundary definitions: what inquiries may be auto-drafted by AI vs. what inquiries MUST be escalated to a human agent)*
- **Tier 1 (Critical / Immediate Escalation):**
- **Tier 2 (Policy / Financial / Ambiguity Risk):**
- **Tier 3 (Standard / Safe to Auto-Resolve):**

## Success Metrics
*(How the stakeholder defines success in quantitative and qualitative terms: e.g. first-response time, escalation accuracy, zero hallucinated policies)*

## Open Questions and Assumptions
*(Unresolved questions, data access dependencies, and baseline assumptions made for the technical architecture)*

## How Findings Changed the Design (Link ADRs)
*(Direct trace from stakeholder pain points to architectural decisions: e.g., why deterministic guardrails overrule the LLM, why escalation is bounded)*
- [ADR 0001: Record Architecture Decisions](docs/adr/0001-record-architecture-decisions.md)
