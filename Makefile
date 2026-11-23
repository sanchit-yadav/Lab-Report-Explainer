# ==============================================================================
# AI Clinical Lab Report Explainer — Production Automation Makefile
# ==============================================================================

.PHONY: help install test eval redteam demo run-api run-web docker-build docker-up lint clean

PYTHON ?= python
PYTEST ?= pytest

help:
	@echo "Available commands:"
	@echo "  make install       Install dependencies in virtual environment"
	@echo "  make test          Run complete unit, integration, and security test suites"
	@echo "  make eval          Execute 63-case golden clinical evaluation harness"
	@echo "  make redteam       Execute 55-vector adversarial red team attack suite"
	@echo "  make demo          Generate synthetic blood reports for live demonstration"
	@echo "  make run-api       Start production FastAPI REST microservice"
	@echo "  make run-web       Start interactive Streamlit clinical web app"
	@echo "  make docker-build  Build multi-stage production Docker image"
	@echo "  make docker-up     Start API, Web, Postgres, and Redis containers"
	@echo "  make clean         Remove cache files, logs, and temporary artifacts"

install:
	pip install -e .

test:
	$(PYTEST) tests/test_tracing.py tests/test_rag_cache.py tests/test_pipeline_stages.py tests/test_citations.py tests/test_redteam.py tests/test_security_guardrails.py -v

eval:
	$(PYTHON) -m evals.run_evals

redteam:
	$(PYTHON) -m redteam.run_redteam

demo:
	$(PYTHON) scripts/generate_demo_reports.py

run-api:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

run-web:
	streamlit run app.py

docker-build:
	docker build -t lab_report_explainer:latest .

docker-up:
	docker compose up -d

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
