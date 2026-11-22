"""
tests/test_api.py
FastAPI TestClient integration tests covering /health, /metrics, /triage,
and defensive payload validation.
"""

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "2.0.0"
    assert "uptime_seconds" in data
    assert "timestamp" in data


def test_metrics_endpoint_json():
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "requests" in data
    assert "latency_ms" in data
    assert "total" in data["requests"]


def test_metrics_endpoint_prometheus():
    response = client.get("/metrics", headers={"Accept": "text/plain"})
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    text = response.text
    assert "# HELP support_agent_requests_total" in text
    assert "support_agent_requests_total" in text


def test_triage_normal_query():
    payload = {
        "customer_query": "How do I set up Personal Hotspot on my iPhone to share data with Mac?",
        "ticket_id": "ticket_test_001",
    }
    response = client.post("/triage", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ticket_id"] == "ticket_test_001"
    assert data["intent"] == "USAGE_FEATURE_HOWTO"
    assert data["decision"] == "draft"
    assert data["should_escalate"] is False
    assert len(data["drafted_reply"]) > 0
    assert len(data["cited_resolution_ids"]) > 0
    assert "trace_id" in data
    assert "triage" in data["step_latencies_ms"]


def test_triage_safety_hazard_escalation():
    payload = {
        "customer_query": "Battery on my iPhone expanded, cracked the screen, and there is smoke!",
    }
    response = client.post("/triage", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "escalate"
    assert data["should_escalate"] is True
    assert data["escalation_tier"] == "TIER_1_HARD_GUARDRAIL"
    assert "smoke" in data["escalation_reason"].lower()


def test_triage_validation_errors():
    # Empty query (min_length=1)
    res_empty = client.post("/triage", json={"customer_query": ""})
    assert res_empty.status_code == 422

    # Oversized query (>1000 chars)
    oversized = "a" * 1001
    res_oversized = client.post("/triage", json={"customer_query": oversized})
    assert res_oversized.status_code == 422
