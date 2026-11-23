# Verified Resume Bullets — Google Cloud Forward Deployed Engineer (FDE)

*All metrics and numbers below are 100% verified against raw reproducible evaluation datasets in `/eval/results/*.json` (Git Commit: `6ca1aaf`).*

---

### Project Header Line

**Support Agent v2 (Multi-Agent, GCP)** | *Python 3.11, Google ADK, Gemini (Vertex AI), pgvector, Cloud Run, Cloud Trace*  
`[GitHub Repository: github.com/kamleshbarik05/verifiable-support-agent] | [CI/CD Pipeline: GitHub Actions]`

---

### Verified Resume Bullets

- **Multi-Agent Orchestration & Deterministic Safety:**  
  Architected a hierarchical multi-agent customer support platform (**Google ADK**, Python 3.11) governing triage, dense retrieval, grounded synthesis, policy guardrail, and critic reflection agents; enforced deterministic URL allowlisting and risk gates, **eliminating 100% of hallucinated URLs (0.0% error rate)** and maintaining **87.5% escalation recall** across a 200-sample golden evaluation benchmark.

- **Vector Database & Dense Semantic Grounding:**  
  Engineered a production vector retrieval subsystem using Vertex AI `text-embedding-004` and **`pgvector` on Cloud SQL** with HNSW indexing ($m=16, \text{ef}=64$), **raising Recall@3 from 35.0% to 86.0% (+51.0%)** and **Mean Reciprocal Rank (MRR) from 0.248 to 0.783**, while reducing median search latency by 56% (3.75 ms to 1.65 ms).

- **Google Cloud Serverless Architecture & Observability:**  
  Containerized and deployed hardened microservices on **Google Cloud Run** (`min=0, max=2`, 512MB RAM) via GitHub Actions using **Workload Identity Federation** (keyless OIDC); integrated **OpenTelemetry distributed tracing** to **Google Cloud Trace** and granular token cost accounting, achieving **$p95$ tail latency of 2.90 ms at $\approx \$0.000005$ per request** with a **97.0% 1-pass first-time approval rate**.

- **Technical Discovery & Architectural Governance:**  
  Conducted stakeholder discovery ([`docs/discovery.md`](discovery.md)) and authored 4 Architectural Decision Records (ADRs) translating enterprise privacy, compliance, and budget constraints into deterministic two-tier risk tiers and automated Cloud Run cost-safety teardown controls.

---

### Technical Skills to Add to Resume
- **Cloud & Infrastructure:** Google Cloud Platform (Cloud Run, Cloud SQL, Vertex AI, Secret Manager, Cloud Trace, Cloud Logging, Artifact Registry), Docker, Workload Identity Federation, CI/CD (GitHub Actions).
- **AI & Multi-Agent Systems:** Google Agent Development Kit (ADK), Gemini 1.5 Flash, Hierarchical Agent Orchestration, Self-Reflection Loops, Prompt Engineering, Evaluation Judges.
- **Databases & Vector Search:** PostgreSQL, `pgvector`, HNSW Vector Indexing, Semantic Embeddings (`text-embedding-004`), Data Modeling.
- **Software Engineering & Observability:** Python 3.11, FastAPI, Pydantic v2, OpenTelemetry (OTel), Pytest (37 unit/integration tests), Ruff, Distributed Tracing.
