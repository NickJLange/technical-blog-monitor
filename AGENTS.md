# AGENTS.md

Instructions for AI coding agents working on this repository.

## Project Overview

Python daemon that monitors technical blogs, renders posts in headless browsers, extracts content, generates embeddings, and stores them in a pluggable vector database for semantic search.

**Architecture:** Async/multithreaded pipeline with pluggable backends for caching, embeddings, and vector storage.

## Common Commands

```bash
# Install dependencies (using uv)
uv sync

# Install Playwright browsers (one-time)
uv run playwright install

# Run all tests (including E2E)
bash scripts/run_all_tests.sh

# Linting and type checking
uv run ruff check .
uv run mypy monitor/

# Run once in debug mode
uv run monitor --once --log-level DEBUG

# Run specific feed
uv run monitor --feed "AWS Blog" --once --log-level DEBUG
```

## Architecture

```
Feed Discovery → Browser Rendering → Text Extraction → Embedding → Vector DB
     ↓                  ↓                  ↓              ↓              ↓
RSS/Atom/JSON    Playwright         Readability      OpenAI/HF      PgVector (Postgres)
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `monitor/main.py` | Entry point, orchestrator, lifecycle management |
| `monitor/config.py` | Pydantic settings, env vars with `__` nesting |
| `monitor/feeds/` | RSS/Atom/JSON feed processors |
| `monitor/fetcher/browser.py` | Playwright browser pool |
| `monitor/extractor/` | Article text/metadata extraction |
| `monitor/embeddings/` | OpenAI, HuggingFace, Sentence-Transformers clients |
| `monitor/vectordb/` | Vector database abstraction (PgVector primary) |
| `monitor/cache/` | Caching layer (PostgreSQL, in-memory) |

### Data Models

- `BlogPost` - discovered posts from feeds
- `Article` - full article content including text and metadata
- `CacheEntry` - generic cache structure
- `Embedding` - vector representation of content

## Configuration

Uses environment variables with `__` delimiter for nesting:

```bash
# Feeds (indexed)
FEEDS__0__NAME="AWS Blog"
FEEDS__0__URL="https://aws.amazon.com/blogs/aws/feed/"
FEEDS__0__CHECK_INTERVAL_MINUTES=60
FEEDS__0__MAX_POSTS_PER_CHECK=3

# Browser
BROWSER__HEADLESS=true
BROWSER__MAX_CONCURRENT_BROWSERS=3
BROWSER__TIMEOUT_SECONDS=30

# Cache
CACHE__BACKEND=postgres        # Options: memory, postgres
CACHE__CACHE_TTL_HOURS=168
CACHE__POSTGRES_DSN=postgresql://user:pass@localhost:5432/dbname # If backend=postgres

# Embeddings
EMBEDDING__TEXT_MODEL_TYPE=openai
EMBEDDING__OPENAI_API_KEY=sk-...
EMBEDDING__EMBEDDING_DIMENSIONS=1536

# Vector DB
VECTOR_DB__DB_TYPE=pgvector    # Options: pgvector
VECTOR_DB__CONNECTION_STRING=postgresql://user:pass@localhost:5432/dbname
VECTOR_DB__COLLECTION_NAME=technical_blog_posts
```

## Code Patterns

### Async context managers for resource cleanup
```python
async with app_lifecycle(settings) as app_context:
    # Resources auto-cleaned on exit
```

### Factory functions for pluggable components
```python
get_feed_processor()      # Returns RSS/Atom/JSON parser
get_embedding_client()    # Returns OpenAI/HF client
get_vector_db_client()    # Returns PgVector client
get_cache_client()        # Returns Memory/Postgres client
```

### Configuration with Pydantic validation
All settings validated at load time using `monitor.config.Settings`.

## Testing

```bash
# Run complete suite
bash scripts/run_all_tests.sh

# Unit tests only
uv run pytest monitor/tests/ -v

# E2E pipeline test (requires Postgres)
uv run python tests/e2e/test_postgres_pipeline.py
```

## Troubleshooting

### Playwright issues
```bash
uv run playwright install --force
```

### Postgres connection errors
Ensure Postgres is running and `CACHE__POSTGRES_DSN` is correct. The system requires the `pgvector` extension installed on the database.

### Clear cache
```python
# Programmatic clearing
from monitor.cache import get_cache_client
client = await get_cache_client(config)
await client.clear()
```

### Debug configuration
```python
from monitor.config import load_settings
settings = load_settings()  # Shows validation errors
```

## Development Workflow

1. Create feature branch from `main`: `git checkout -b feat/<topic>`
2. Make changes, commit with conventional commits
3. Run tests: `uv run pytest -q`
4. Push and open PR against `main`
5. After review, squash commits if needed and merge

## Notes

- Python 3.11+ required
- Dependencies managed via `uv`
- All timestamps in UTC
- Structured logging enabled by default (JSON output)