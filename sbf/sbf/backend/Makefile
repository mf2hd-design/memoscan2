.PHONY: install dev test lint run docker-build docker-run clean

# Install production dependencies
install:
	pip install -r requirements.txt

# Install with development dependencies
dev:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-cov mypy ruff

# Run tests
test:
	PYTHONPATH=. pytest tests/ -v

# Run tests with coverage
coverage:
	PYTHONPATH=. pytest tests/ --cov=app --cov-report=html --cov-report=term

# Lint code
lint:
	ruff check app/ --select=E,F,W --ignore=E501,F401

# Auto-fix lint issues
lint-fix:
	ruff check app/ --select=E,F,W --ignore=E501,F401 --fix

# Type check
typecheck:
	mypy app/ --ignore-missing-imports

# Run development server
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run production server
run-prod:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Build Docker image
docker-build:
	docker build -t sbf-backend .

# Run Docker container
docker-run:
	docker run -p 8000:8000 --env-file .env sbf-backend

# Clean cache and build artifacts
clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	rm -rf app/__pycache__ app/**/__pycache__
	rm -rf htmlcov .coverage
	rm -rf /tmp/sbf_cache/*

# Validate all Python files
validate:
	python -m py_compile app/*.py app/**/*.py app/**/**/*.py

# Full check (lint + test + typecheck)
check: lint test
	@echo "All checks passed!"
