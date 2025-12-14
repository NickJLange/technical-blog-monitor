# Contributing to Technical Blog Monitor

Thank you for your interest in contributing! This document outlines the standards and workflows for maintaining a high-quality codebase.

## 🛠 Development Environment

We use **uv** for dependency management and **Python 3.11+**.

```bash
# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install
```

## 📐 Coding Standards

### Style & Formatting
- **Code Style**: We follow [PEP 8](https://peps.python.org/pep-0008/).
- **Formatter**: Code must be formatted with **Ruff** (configured in `pyproject.toml`).
- **Linter**: We use **Ruff** for linting.
- **Type Checking**: All code must be fully typed and pass **MyPy** strict mode.

```bash
# Format and lint
uv run ruff check . --fix
uv run ruff format .

# Type check
uv run mypy monitor/
```

### Best Practices

1.  **DRY (Don't Repeat Yourself)**:
    - Avoid duplicating logic. If you copy-paste code, refactor it into a shared utility or base class.
    - Example: Feed parsing logic should be shared between RSS and Atom implementations.

2.  **Library Standardization**:
    - **Prefer established libraries** over custom implementations.
    - **Retries**: Use `tenacity` instead of `while` loops with `sleep`.
    - **HTTP**: Use `httpx` for async HTTP requests.
    - **Logging**: Use `structlog` for structured, context-rich logging.
        - **Configuration**: Use `pydantic-settings` for all config handling.
        - **Data Validation**: Use `pydantic` models for data structures.
    
    4.  **Backend Standards**:
        -   **Database**: We exclusively use **PostgreSQL** with `pgvector` for both caching and vector storage. Do not introduce new database dependencies (e.g., Redis, Qdrant) without architectural approval.
        -   **Migration**: Database schema changes should be managed via SQL scripts or migration tools (future work).
    
    3.  **Code Structure**:
        -   **Modules**: Keep files focused (Single Responsibility Principle).
    - **Async/Await**: This is an async-first codebase. Avoid blocking calls (CPU-bound work should use `run_in_executor`).

## 🧪 Testing

We use **pytest** for testing. All new features and bug fixes must include tests.

- **Unit Tests**: Test individual components in isolation.
- **Integration Tests**: Test interactions between components (e.g., FeedProcessor -> DB).

```bash
# Run all tests
uv run pytest

# Run fast tests (skip slow integration tests)
uv run pytest -m "not slow"
```

## 🔄 Refactoring Guidelines

When modifying existing code, look for opportunities to improve:

- **Simplification**: Can complex logic be replaced by a library function?
- **Extraction**: Can a large function be broken down?
- **Duplication**: Is this logic used elsewhere?

## 📝 Pull Request Workflow

1.  Create a feature branch: `feat/description` or `fix/issue`.
2.  Make granular, atomic commits with clear messages (Conventional Commits).
3.  Add tests for your changes.
4.  Run linting and type checking locally.
5.  Open a PR and describe your changes, focusing on *why* the change was made.
