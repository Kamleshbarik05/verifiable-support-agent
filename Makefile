# ==============================================================================
# Verifiable Support Agent v2 — Automation Makefile
# ==============================================================================

.PHONY: help install test lint eval eval-baseline eval-v2 eval-retrieval eval-compare eval-latency-cost report run serve docker-build clean

PYTHON ?= python

help:
	@echo "Available targets:"
	@echo "  install         Install all project dependencies"
	@echo "  test            Run pytest test suite"
	@echo "  lint            Run ruff linter and style checks"
	@echo "  eval-baseline   Run reproducible 200-sample v1 baseline evaluation"
	@echo "  eval-v2         Run reproducible 200-sample v2 multi-agent evaluation"
	@echo "  eval-retrieval  Run retrieval A/B benchmark (v1 vs pgvector)"
	@echo "  eval-compare    Compare v1 vs v2 side-by-side benchmark results"
	@echo "  eval-latency-cost Run LLM-native latency, cost, and revision benchmark"
	@echo "  report          Generate Markdown and Rich benchmark audit report"
	@echo "  serve           Start FastAPI development server on port 8000"
	@echo "  run             Run interactive CLI demonstration"
	@echo "  docker-build    Build Cloud Run production container image"
	@echo "  clean           Clean bytecode and temporary test caches"

install:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install ruff pytest pytest-cov httpx uvicorn

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check .

eval-baseline:
	$(PYTHON) eval/runners/e2e_eval.py --model v1 --sample-size 200 --output eval/results/baseline_v1.json

eval-v2:
	$(PYTHON) eval/runners/e2e_eval.py --model v2 --sample-size 200 --output eval/results/e2e_v2.json

eval-retrieval:
	$(PYTHON) eval/runners/retrieval_eval.py --sample-size 100 --output eval/results/retrieval_ab.json

eval-compare:
	$(PYTHON) eval/runners/compare_eval.py

eval-latency-cost:
	$(PYTHON) eval/runners/latency_cost_eval.py --sample-size 100 --output eval/results/latency_cost.json

eval-live:
	$(PYTHON) eval/runners/live_eval.py --samples 30 --delay 2.0

report:
	$(PYTHON) eval/runners/generate_report.py

eval:
	$(PYTHON) app/v1/evaluate.py

run:
	$(PYTHON) app/v1/demo.py

serve:
	$(PYTHON) -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker build -t verifiable-support-agent:v2 -f deploy/Dockerfile .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
