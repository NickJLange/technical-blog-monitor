# AGENTS.md

Instructions for AI coding agents working on this repository.

## Project Overview

Python daemon that monitors technical blogs, renders posts in headless browsers, extracts content, generates embeddings, and stores them in PostgreSQL with pgvector for semantic search.

**Key architecture:** Unified PostgreSQL storage - both caching and vector embeddings use the same database with a shared connection pool.

## Common Commands

```bash
# Install dependencies
uv sync

# Install Playwright browsers (one-time)
uv run playwright install

# Run tests
uv run pytest monitor/tests/ -v

# Linting and type checking
uv run ruff check .
uv run mypy monitor/

# Run once in debug mode
uv run monitor --once --log-level DEBUG

# Run specific feed
uv run monitor --feed "AWS Blog" --once
```

## Architecture

```
Feed Discovery → Browser Rendering → Text Extraction → Embedding → PostgreSQL+pgvector
     ↓                  ↓                  ↓              ↓              ↓
RSS/Atom/JSON    Playwright         Readability      OpenAI/HF      Unified DB
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `monitor/main.py` | Entry point, orchestrator, lifecycle management |
| `monitor/config.py` | Pydantic settings, env vars with `__` nesting |
| `monitor/feeds/` | RSS/Atom/JSON feed processors |
| `monitor/fetcher/browser.py` | Playwright browser pool |
| `monitor/extractor/` | Article text/metadata extraction |
| `monitor/embeddings/` | OpenAI, HuggingFace, Ollama embedding clients |
| `monitor/vectordb/pgvector.py` | PostgreSQL+pgvector vector storage |
| `monitor/cache/postgres.py` | PostgreSQL-based cache with TTL |
| `monitor/db/postgres_pool.py` | Shared asyncpg connection pool |

### Data Models

- `BlogPost` - discovered posts from feeds
- `EmbeddingRecord` - processed content with vectors
- `ArticleContent` - extracted article text/metadata

## Configuration

Uses environment variables with `__` delimiter for nesting:

```bash
# Feeds (indexed)
FEEDS__0__NAME="AWS Blog"
FEEDS__0__URL="https://aws.amazon.com/blogs/aws/feed/"

# Unified PostgreSQL storage
VECTOR_DB__DB_TYPE=pgvector
VECTOR_DB__CONNECTION_STRING=postgresql://user@localhost:5432/blogmon
CACHE__BACKEND=postgres
# CACHE__POSTGRES_DSN falls back to VECTOR_DB__CONNECTION_STRING

# Embeddings
EMBEDDING__TEXT_MODEL_TYPE=openai
EMBEDDING__OPENAI_API_KEY=sk-...
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
get_embedding_client()    # Returns OpenAI/HF/Ollama client
get_vector_db_client()    # Returns pgvector client
get_cache_client()        # Returns PostgreSQL/filesystem/memory cache
```

### Shared PostgreSQL pool
Both `PgVectorDBClient` and `PostgresCacheClient` share the same `asyncpg` pool via `monitor.db.postgres_pool.get_pool()`.

## Testing

```bash
# Unit tests
uv run pytest monitor/tests/ -v

# Integration tests (require feeds)
uv run python test_feeds.py

# Full pipeline test
uv run python test_full_pipeline.py
```

Tests use in-memory implementations for databases/caches when possible.

## Troubleshooting

### Playwright issues
```bash
uv run playwright install --force
uv run playwright install-deps
```

### Clear cache
```bash
rm -rf cache/
```

### Debug configuration
```python
from monitor.config import load_settings
settings = load_settings()  # Shows validation errors
```

## Pending Work (Redis Removal)

The following tasks remain to fully remove Redis from the codebase:

1. **pyproject.toml**: Remove `redis[hiredis]` and `aioredis` from dependencies
2. **monitor/cache/redis.py**: Delete this file entirely
3. **monitor/cache/__init__.py**: Remove Redis imports and CacheBackend.REDIS handling
4. **monitor/config.py**: Remove `redis_url`, `redis_password`, and `REDIS` from CacheBackend enum
5. **monitor/main.py**: Remove `RedisJobStore` import and redis scheduler code (lines 25, 125-127)
6. **.env.example**: Remove the Redis scheduler URL comment (line 125)
7. **requirements.txt**: Remove `redis` and `aioredis` entries
8. Run `uv sync` and `uv run pytest monitor/tests/ -v` to verify
