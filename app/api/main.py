"""
app/api/main.py
FastAPI production application exposing /triage, /health, and /metrics endpoints.
Configured with structured JSON logging, trace_id propagation, and defensive validation.
"""

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.agents.orchestrator import OrchestratorAgent
from app.api.schemas import HealthResponse, TriageRequest, TriageResponse

# Configure structured JSON logger
logger = logging.getLogger("support_agent_api")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)

# In-memory operational metrics store
_app_start_time = time.time()
_metrics_counters = {
    "total_requests": 0,
    "escalated_requests": 0,
    "auto_resolved_requests": 0,
    "total_tokens": 0,
    "total_cost_usd": 0.0,
}
_latencies_ms: list[float] = []

# Cached singleton orchestrator
_orchestrator: OrchestratorAgent | None = None


def get_orchestrator() -> OrchestratorAgent:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = OrchestratorAgent()
    return _orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Warm up orchestrator
    get_orchestrator()
    yield
    # Shutdown logic if needed


app = FastAPI(
    title="Verifiable Support Agent API",
    version="2.0.0",
    description="Trust-calibrated Google ADK multi-agent support triage and grounded resolution API on GCP.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_and_log_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID", f"trace_{uuid.uuid4().hex[:12]}")
    request.state.trace_id = trace_id

    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    response.headers["X-Trace-ID"] = trace_id

    # Structured Cloud Logging payload
    log_record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "trace_id": trace_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "latency_ms": elapsed_ms,
    }
    logger.info(json.dumps(log_record))
    return response


@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def health_check() -> HealthResponse:
    """Fast probe endpoint (<2ms) for Cloud Run container health verification."""
    uptime = round(time.time() - _app_start_time, 2)
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        uptime_seconds=uptime,
        timestamp=datetime.now(UTC).isoformat(),
    )


@app.post(
    "/triage",
    response_model=TriageResponse,
    status_code=status.HTTP_200_OK,
    tags=["Triage"],
)
def triage_ticket(
    payload: TriageRequest,
    request: Request,
) -> TriageResponse:
    """
    Evaluates an incoming customer inquiry through the hierarchical multi-agent system.
    Returns intent classification, human escalation decision, grounded draft, and citations.
    """
    trace_id = getattr(request.state, "trace_id", f"trace_{uuid.uuid4().hex[:12]}")
    ticket_id = payload.ticket_id or f"ticket_{uuid.uuid4().hex[:8]}"

    t0 = time.perf_counter()
    orchestrator = get_orchestrator()

    try:
        state = orchestrator.process_ticket(
            customer_query=payload.customer_query,
            ticket_id=ticket_id,
            trace_id=trace_id,
        )
    except Exception as exc:
        logger.error(json.dumps({
            "event": "triage_error",
            "trace_id": trace_id,
            "error": str(exc),
        }))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Multi-agent triage execution failed: {exc}",
        ) from exc

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # Update metrics
    _metrics_counters["total_requests"] += 1
    if state.should_escalate:
        _metrics_counters["escalated_requests"] += 1
    else:
        _metrics_counters["auto_resolved_requests"] += 1
    _metrics_counters["total_tokens"] += state.total_tokens
    _metrics_counters["total_cost_usd"] = round(
        _metrics_counters["total_cost_usd"] + state.total_cost_usd, 6
    )
    _latencies_ms.append(elapsed_ms)

    decision = "escalate" if state.should_escalate else "draft"

    return TriageResponse(
        ticket_id=state.ticket_id,
        intent=state.intent,
        intent_confidence=state.intent_confidence,
        decision=decision,
        should_escalate=state.should_escalate,
        escalation_reason=state.escalation_reason if state.should_escalate else None,
        escalation_tier=state.escalation_tier,
        reason_code=state.reason_code,
        drafted_reply=state.drafted_reply,
        cited_resolution_ids=state.cited_resolution_ids,
        critic_passed=state.critic_verdict.passed,
        revisions_needed=state.revision_count,
        trace_id=trace_id,
        step_latencies_ms=state.step_timings_ms,
        step_metrics=state.step_metrics,
        total_cost_usd=state.total_cost_usd,
        total_tokens=state.total_tokens,
    )


@app.get("/metrics", tags=["Monitoring"])
def get_metrics(accept: str | None = Header(default=None)) -> Any:
    """
    Exposes operational metrics:
    - Structured JSON by default.
    - Prometheus exposition format if Accept header contains 'text/plain'.
    """
    total = _metrics_counters["total_requests"]
    escalated = _metrics_counters["escalated_requests"]
    auto_resolved = _metrics_counters["auto_resolved_requests"]
    tokens = _metrics_counters["total_tokens"]
    cost = _metrics_counters["total_cost_usd"]

    p50 = round(float(np.percentile(_latencies_ms, 50)), 2) if _latencies_ms else 0.0
    p95 = round(float(np.percentile(_latencies_ms, 95)), 2) if _latencies_ms else 0.0

    # Prometheus exposition format
    if accept and "text/plain" in accept:
        prom_lines = [
            "# HELP support_agent_requests_total Total number of support triage requests",
            "# TYPE support_agent_requests_total counter",
            f'support_agent_requests_total{{status="total"}} {total}',
            f'support_agent_requests_total{{status="escalated"}} {escalated}',
            f'support_agent_requests_total{{status="auto_resolved"}} {auto_resolved}',
            "# HELP support_agent_tokens_total Total input and output tokens consumed",
            "# TYPE support_agent_tokens_total counter",
            f"support_agent_tokens_total {tokens}",
            "# HELP support_agent_cost_usd_total Total estimated cost in USD",
            "# TYPE support_agent_cost_usd_total counter",
            f"support_agent_cost_usd_total {cost:.6f}",
            "# HELP support_agent_latency_ms End-to-end triage latency in milliseconds",
            "# TYPE support_agent_latency_ms gauge",
            f'support_agent_latency_ms{{quantile="0.5"}} {p50}',
            f'support_agent_latency_ms{{quantile="0.95"}} {p95}',
        ]
        return PlainTextResponse("\n".join(prom_lines), media_type="text/plain; version=0.0.4")

    # Structured JSON format
    return {
        "uptime_seconds": round(time.time() - _app_start_time, 2),
        "requests": {
            "total": total,
            "escalated": escalated,
            "auto_resolved": auto_resolved,
            "escalation_rate": round(escalated / total, 4) if total > 0 else 0.0,
        },
        "tokens": {
            "total_tokens": tokens,
            "total_cost_usd": cost,
        },
        "latency_ms": {
            "p50": p50,
            "p95": p95,
            "sample_count": len(_latencies_ms),
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
