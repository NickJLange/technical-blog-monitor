.PHONY: help install test lint type-check format clean docs postgres up down verify

## Help
help:
	@echo "Technical Blog Monitor - Development Tasks"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install dependencies with uv"
	@echo "  make install-browsers Install Playwright browsers"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all unit tests"
	@echo "  make test-verbose     Run tests with verbose output"
	@echo "  make test-coverage    Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             Run ruff linter"
	@echo "  make type-check       Run mypy type checker"
	@echo "  make format           Auto-format code with ruff"
	@echo "  make verify           Run all quality checks (lint, type-check, test)"
	@echo ""
	@echo "Database:"
	@echo "  make postgres         Start PostgreSQL in Docker"
	@echo "  make postgres-stop    Stop PostgreSQL"
	@echo "  make postgres-reset   Reset PostgreSQL data"
	@echo ""
	@echo "Container:"
	@echo "  make up               Start all services (postgres + app) with docker/podman"
	@echo "  make down             Stop all services"
	@echo "  make docker-build     Build Docker image"
	@echo ""
	@echo "Run:"
	@echo "  make run-once         Run monitor once (single pass)"
	@echo "  make run-daemon       Run monitor as daemon with scheduler"
	@echo "  make run-feed FEED=<name>  Run specific feed (e.g., make run-feed FEED='AWS Blog')"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean            Remove cache, logs, and temp files"
	@echo "  make docs             Generate documentation (if available)"

## Setup & Installation
install:
	uv sync

install-browsers:
	uv run playwright install chromium

## Testing
test:
	uv run pytest monitor/tests/ -q

test-verbose:
	uv run pytest monitor/tests/ -v

test-coverage:
	uv run pytest monitor/tests/ -v --cov=monitor --cov-report=html
	@echo "Coverage report generated: htmlcov/index.html"

## Code Quality
lint:
	uv run ruff check .

type-check:
	uv run mypy monitor/

format:
	uv run ruff check --fix .
	uv run isort monitor/

verify: lint type-check test
	@echo "✅ All quality checks passed!"

## Database (PostgreSQL)
postgres:
	@command -v podman >/dev/null 2>&1 || { echo "podman not found. Install podman or use docker."; exit 1; }
	@echo "Starting PostgreSQL..."
	podman run -d --name blogmon-postgres \
		-e POSTGRES_DB=blogmon \
		-e POSTGRES_USER=blogmon \
		-e POSTGRES_PASSWORD=blogmon_secure_password \
		-v blogmon-postgres-data:/var/lib/postgresql/data \
		-p 5432:5432 \
		pgvector/pgvector:pg16
	@sleep 3
	@podman exec blogmon-postgres pg_isready -U blogmon
	@echo "✅ PostgreSQL ready at localhost:5432"

postgres-stop:
	podman stop blogmon-postgres || true
	podman rm blogmon-postgres || true

postgres-reset: postgres-stop
	podman volume rm blogmon-postgres-data || true
	make postgres

## Container (Docker/Podman)
docker-build:
	@command -v podman >/dev/null 2>&1 && DOCKER=podman || DOCKER=docker
	@echo "Building container image..."
	${DOCKER} build -t blogmon:latest -f Dockerfile.dev .
	@echo "✅ Image built: blogmon:latest"

up: postgres docker-build
	@command -v podman >/dev/null 2>&1 && DOCKER=podman || DOCKER=docker
	@echo "Starting blog monitor daemon..."
	${DOCKER} run -d \
		--name blogmon-daemon \
		--network blogmon-network \
		--env-file .env.docker \
		-v ./data:/app/data \
		-v ./cache:/app/cache \
		-p 8080:8080 \
		blogmon:latest
	@sleep 3
	@echo "✅ Services running:"
	@${DOCKER} ps --filter "name=blogmon" --format "table {{.Names}}\t{{.Status}}"
	@echo ""
	@echo "Web dashboard: http://localhost:8080"

down:
	@command -v podman >/dev/null 2>&1 && DOCKER=podman || DOCKER=docker
	@echo "Stopping services..."
	${DOCKER} stop blogmon-daemon || true
	${DOCKER} stop blogmon-postgres || true
	${DOCKER} rm blogmon-daemon || true
	${DOCKER} rm blogmon-postgres || true
	@echo "✅ Services stopped"

## Run
run-once:
	uv run monitor --once --log-level DEBUG

run-daemon:
	uv run monitor --log-level DEBUG

run-feed:
	uv run monitor --feed "$(FEED)" --once --log-level DEBUG

## Utilities
clean:
	@echo "Cleaning..."
	rm -rf cache/ data/ .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/ build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✅ Cleaned"

docs:
	@echo "Generating documentation..."
	@test -f README.md && echo "📄 See README.md for documentation"
	@test -f AGENTS.md && echo "📄 See AGENTS.md for developer guide"
	@test -f doc/diagrams && echo "📊 See doc/diagrams/ for architecture diagrams"

## Development Workflow
.DEFAULT_GOAL := help
