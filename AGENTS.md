# AGENTS.md

Instructions for AI coding agents working on this repository.

## Project Overview

Python daemon that monitors technical blogs, renders posts in headless browsers, extracts content, generates embeddings, and stores them in a pluggable vector database for semantic search.

**Architecture:** Async/multithreaded pipeline with pluggable backends for caching, embeddings, and vector storage.

## Common Commands

```bash
# Install dependencies
pip install poetry && poetry install

# Install Playwright browsers (one-time)
poetry run playwright install

# Run tests
poetry run pytest -q

# Linting and type checking
poetry run ruff .
poetry run mypy monitor/

# Run once in debug mode
poetry run monitor --once --log-level DEBUG

# Run specific feed
poetry run monitor --feed "AWS Blog" --once --log-level DEBUG
```

## Architecture

```
Feed Discovery → Browser Rendering → Text Extraction → Embedding → Vector DB
     ↓                  ↓                  ↓              ↓              ↓
RSS/Atom/JSON    Playwright         Readability      OpenAI/HF      Qdrant/Chroma
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
| `monitor/vectordb/` | Vector database abstraction (Qdrant, Chroma, Pinecone, etc.) |
| `monitor/cache/` | Caching layer (Redis, filesystem, in-memory) |

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
FEEDS__0__CHECK_INTERVAL_MINUTES=60
FEEDS__0__MAX_POSTS_PER_CHECK=3

# Browser
BROWSER__HEADLESS=true
BROWSER__MAX_CONCURRENT_BROWSERS=3
BROWSER__TIMEOUT_SECONDS=30

# Cache
CACHE__BACKEND=memory          # Options: memory, filesystem, redis
CACHE__CACHE_TTL_HOURS=168
CACHE__REDIS_URL=redis://localhost:6379/0  # If backend=redis

# Embeddings
EMBEDDING__TEXT_MODEL_TYPE=openai
EMBEDDING__OPENAI_API_KEY=sk-...
EMBEDDING__EMBEDDING_DIMENSIONS=1536

# Vector DB
VECTOR_DB__DB_TYPE=qdrant      # Options: qdrant, chroma, pinecone, milvus, weaviate
VECTOR_DB__CONNECTION_STRING=http://localhost:6333
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
get_vector_db_client()    # Returns pluggable VDB client
```

### Configuration with Pydantic validation
All settings validated at load time using `monitor.config.Settings`.

## Testing

```bash
# Unit tests
poetry run pytest monitor/tests/ -v

# Integration tests (require redis/services)
poetry run pytest test_feeds.py -v

# Full pipeline test
poetry run python test_basic.py
```

Tests use in-memory implementations for databases when possible.

## Troubleshooting

### Playwright issues
```bash
poetry run playwright install --force
```

### Redis connection errors
Ensure Redis is running: `redis-cli ping`

### Clear cache
```bash
rm -rf cache/
```

### Debug configuration
```python
from monitor.config import load_settings
settings = load_settings()  # Shows validation errors
```

## Development Workflow

1. Create feature branch from `master`: `git checkout -b feat/<topic>` or `docs/<topic>`
2. Make changes, commit with conventional commits
3. Run tests: `poetry run pytest -q`
4. Push and open PR against `master`
5. After review, squash commits if needed and merge

## Notes

- Python 3.11+ required
- All timestamps in UTC
- Structured logging enabled by default (JSON output)
- Pre-commit hooks available: `pre-commit install`
- Use Poetry for dependency management: `poetry add <package>`
