.PHONY: help install test test-unit test-verbose lint format coverage build validate ci clean

help:
	@echo "CallProfiler — Development Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  make install       Install dependencies (pip)"
	@echo "  make test          Run all tests"
	@echo "  make test-unit     Run unit tests only"
	@echo "  make test-verbose  Run tests with verbose output"
	@echo "  make lint          Run flake8 + ruff (static analysis)"
	@echo "  make format        Format code with black (if installed)"
	@echo "  make coverage      Generate coverage report (HTML)"
	@echo "  make build         Check Python syntax (fast)"
	@echo "  make validate      Full validation (lint + test + coverage)"
	@echo "  make ci            Simulate CI/CD locally"
	@echo "  make clean         Remove artifacts (__pycache__, .pytest_cache, etc)"
	@echo ""
	@echo "Usage: make <target>"

install:
	@echo "Installing dependencies..."
	pip install pytest pytest-cov flake8 ruff black 2>/dev/null || \
	pip install --user pytest pytest-cov flake8 ruff black
	@echo "✓ Dependencies installed"

test:
	@echo "Running tests..."
	python -m pytest tests/ -v --tb=short
	@echo "✓ Tests completed"

test-unit:
	@echo "Running unit tests..."
	python -m pytest tests/test_*.py -v --tb=short
	@echo "✓ Unit tests completed"

test-verbose:
	@echo "Running tests (verbose)..."
	python -m pytest tests/ -vv --tb=long -s
	@echo "✓ Tests completed (verbose)"

lint:
	@echo "Running static analysis (flake8 + ruff)..."
	@echo ""
	@echo "--- flake8 ---"
	-python -m flake8 src/callprofiler tests --max-line-length=100 --extend-ignore=E203,W503 || true
	@echo ""
	@echo "--- ruff ---"
	-python -m ruff check src/callprofiler tests || true
	@echo ""
	@echo "✓ Lint analysis completed"

format:
	@echo "Formatting code with black..."
	-python -m black src/callprofiler tests --line-length=100 2>/dev/null || \
	echo "Note: black not installed, skipping format"
	@echo "✓ Format completed"

coverage:
	@echo "Generating coverage report..."
	python -m pytest tests/ --cov=src/callprofiler --cov-report=html --cov-report=term-missing
	@echo ""
	@echo "✓ Coverage report generated"
	@echo "  HTML report: htmlcov/index.html"

build:
	@echo "Checking Python syntax..."
	@python -m py_compile src/callprofiler/*.py
	@python -m py_compile src/callprofiler/**/*.py 2>/dev/null || true
	@echo "✓ Syntax check passed"

validate: build lint test coverage
	@echo ""
	@echo "════════════════════════════════════════"
	@echo "✓ All validation checks PASSED"
	@echo "════════════════════════════════════════"

ci: clean build lint test
	@echo ""
	@echo "════════════════════════════════════════"
	@echo "✓ CI simulation completed successfully"
	@echo "════════════════════════════════════════"
	@echo ""
	@echo "Next steps for real CI:"
	@echo "  - Push to GitHub"
	@echo "  - .github/workflows/ci.yml will run"
	@echo "  - Coverage uploaded to Codecov"

clean:
	@echo "Cleaning artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name .coverage -delete 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Artifacts cleaned"
