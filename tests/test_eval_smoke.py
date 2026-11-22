"""
tests/test_eval_smoke.py
Fast, zero-network smoke tests for the evaluation harness and cost model.
Ensures CI executes without external API dependencies.
"""

import pytest

from app.observability.cost_model import calculate_cost, get_model_pricing
from eval.runners.e2e_eval import check_hallucinated_urls, extract_urls, run_e2e_benchmark


def test_cost_model_gemini_flash_calculation():
    pricing = get_model_pricing("gemini-1.5-flash-002")
    assert pricing is not None
    assert pricing.input_cost_per_million == 0.075
    assert pricing.output_cost_per_million == 0.30

    # 10,000 input tokens, 2,000 output tokens
    # input: 0.01 * 0.075 = 0.00075
    # output: 0.002 * 0.30 = 0.00060
    # total = 0.00135
    cost = calculate_cost("gemini-1.5-flash-002", input_tokens=10_000, output_tokens=2_000)
    assert pytest.approx(cost, 1e-6) == 0.00135


def test_cost_model_offline_mock_is_zero():
    cost = calculate_cost("offline-mock", input_tokens=50_000, output_tokens=10_000)
    assert cost == 0.0


def test_url_extraction():
    text = "Visit https://support.apple.com/iphone-battery or http://apple.co/help for details."
    urls = extract_urls(text)
    assert "https://support.apple.com/iphone-battery" in urls
    assert "http://apple.co/help" in urls


def test_check_hallucinated_urls_detects_unauthorized_link():
    draft = "Please visit https://unauthorized-fake-apple.com/claim-refund to get your money back."
    grounding = [{"apple_resolution": "Contact Apple Support at https://getsupport.apple.com"}]
    gold = "Official Apple resolution: Visit https://support.apple.com/billing"

    is_hallucinated = check_hallucinated_urls(draft, grounding, gold)
    assert is_hallucinated is True


def test_check_hallucinated_urls_passes_grounded_link():
    draft = "You can schedule a service appointment at https://getsupport.apple.com."
    grounding = [
        {"apple_resolution": "Visit https://getsupport.apple.com for Genius Bar scheduling."}
    ]
    gold = "Official Apple resolution: Visit https://getsupport.apple.com"

    is_hallucinated = check_hallucinated_urls(draft, grounding, gold)
    assert is_hallucinated is False


def test_e2e_eval_smoke_run(tmp_path):
    output_json = tmp_path / "smoke_baseline.json"
    result = run_e2e_benchmark(
        model_version="v1",
        sample_size=5,
        offline=True,
        output_file=output_json,
    )

    assert result["system"] == "v1_baseline"
    assert result["sample_size"] == 5
    assert output_json.exists()

    metrics = result["metrics"]
    assert "intent_macro_f1" in metrics
    assert "escalation_fnr" in metrics
    assert "hallucinated_url_rate" in metrics
    assert "latency_p50_ms" in metrics
    assert "cost_per_request_usd" in metrics
    assert 0.0 <= metrics["intent_macro_f1"] <= 1.0
