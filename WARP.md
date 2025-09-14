# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is a high-performance Python daemon that monitors technical blogs from major companies, renders posts in headless browsers, extracts rich content, and stores them in vector databases for semantic search. The system is built for production scale with async/multithread architecture, pluggable components, and container deployment.

## Common Development Commands

### Setup and Installation
```bash
# Install dependencies with Poetry
poetry install

# Install Playwright browsers (one-time setup)
poetry run playwright install

# Set up pre-commit hooks
poetry install --with dev
pre-commit install
```

### Running the Application
```bash
# Run once in debug mode (good for testing)
poetry run monitor --once --log-level DEBUG

# Run specific feed only
poetry run monitor --feed "Google Cloud Blog" --once

# Run as daemon (production mode)
poetry run monitor

# Run with Docker
docker build -t blog-monitor .
docker run --env-file .env blog-monitor
```

### Testing and Quality Assurance
```bash
# Run all tests
pytest -q

# Run tests with coverage
pytest -q --cov=monitor --cov-report=term-missing

# Run specific test files
python test_basic.py
python test_feeds.py

# Linting and formatting
ruff .                    # Static analysis and linting
mypy monitor/            # Type checking
black .                  # Code formatting
isort .                  # Import sorting

# Security checks
bandit -r monitor -ll    # Security vulnerability scanning
```

### Development Workflow
```bash
# Pre-commit will run automatically, or manually:
pre-commit run --all-files

# Check configuration without running
poetry run python -c "from monitor.config import load_settings; print(load_settings())"
```

## Architecture Overview

The system follows a modular, layered architecture with clear separation of concerns:

### Core Processing Pipeline
```
Feed Discovery → Content Rendering → Text Extraction → Embedding Generation → Vector Storage
     ↓               ↓                    ↓                    ↓                 ↓
RSS/Atom/JSON → Playwright Browser → Readability Parser → OpenAI/HF Models → Qdrant/Chroma
```

### Key Architectural Components

**Application Context (`monitor/main.py`)**
- Central orchestrator that manages all component lifecycles
- Handles graceful shutdown and resource cleanup
- Manages async task tracking and error handling
- Provides dependency injection for all services

**Feed Processing (`monitor/feeds/`)**
- Abstract base class `FeedProcessor` with pluggable implementations
- Auto-detects feed types (RSS, Atom, JSON) based on URL patterns and content
- Implements caching and deduplication to avoid reprocessing
- Handles concurrent processing with semaphores for rate limiting

**Browser Pool (`monitor/fetcher/browser.py`)**
- Manages pool of Playwright browser instances for concurrent rendering
- Supports multiple browser types (Chromium, Firefox, WebKit)
- Implements stealth mode and ad blocking for better content extraction
- Takes full-page screenshots and handles timeouts gracefully

**Content Extraction (`monitor/extractor/`)**
- Uses readability-lxml for clean article text extraction
- Extracts metadata (author, publish date, tags, word count)
- Handles various HTML structures and edge cases
- Thread pool execution for CPU-bound parsing tasks

**Embedding Generation (`monitor/embeddings/`)**
- Pluggable architecture supporting OpenAI, HuggingFace, Sentence Transformers
- Separate text and image embedding pipelines
- Batch processing for efficiency
- Retry logic with exponential backoff

**Vector Database (`monitor/vectordb/`)**
- Abstract interface supporting Qdrant, Chroma, Pinecone, Milvus, Weaviate
- Handles both text and image embeddings with separate collections
- Implements upsert operations and similarity search
- Connection pooling and batch operations

**Configuration System (`monitor/config.py`)**
- Pydantic-based settings with environment variable support
- Nested configuration with `__` delimiter (e.g., `FEEDS__0__URL`)
- Validation and type checking for all configuration values
- Support for secrets and optional parameters

**Caching Layer (`monitor/cache/`)**
- Pluggable backends: Redis, filesystem, in-memory
- Cache keys for feeds, posts, and article content
- TTL management and cache invalidation
- Used for deduplication and performance optimization

### Data Models

**BlogPost (`monitor/models/blog_post.py`)**
- Primary entity representing discovered blog posts
- Handles ID generation, deduplication, and status tracking
- Includes metadata like tags, publication dates, and processing status

**EmbeddingRecord (`monitor/models/embedding.py`)**
- Represents processed content with text and optional image embeddings
- Links back to original BlogPost with rich metadata
- Optimized for vector database storage and retrieval

**ArticleContent (`monitor/models/article.py`)**
- Structured representation of extracted article content
- Includes cleaned text, HTML, metadata, and word counts
- Handles content validation and cleaning

## Configuration

The system uses environment variables with hierarchical configuration:

### Essential Environment Variables
```bash
# Feed Configuration (can have multiple feeds with incrementing numbers)
FEEDS__0__NAME="Google Cloud Blog"
FEEDS__0__URL="https://cloud.google.com/blog/products/rss"
FEEDS__0__CHECK_INTERVAL_MINUTES=60

# Embedding Configuration
EMBEDDING__TEXT_MODEL_TYPE=openai
EMBEDDING__OPENAI_API_KEY=sk-your-key-here
EMBEDDING__TEXT_MODEL_NAME=text-embedding-ada-002

# Vector Database Configuration
VECTOR_DB__DB_TYPE=qdrant
VECTOR_DB__CONNECTION_STRING=http://localhost:6333
VECTOR_DB__COLLECTION_NAME=technical_blog_posts

# Browser Configuration
BROWSER__HEADLESS=true
BROWSER__MAX_CONCURRENT_BROWSERS=3
BROWSER__STEALTH_MODE=true
```

### Configuration Patterns
- Use `FEEDS__N__` pattern for multiple feeds (N = 0, 1, 2, ...)
- Nested settings use double underscore delimiter (`CACHE__REDIS_URL`)
- Boolean values: `true`/`false` (case insensitive)
- Optional settings have sensible defaults

## Key Development Patterns

### Async/Await with Resource Management
The codebase extensively uses async context managers and proper resource cleanup:
```python
async with app_lifecycle(settings) as app_context:
    # All resources are properly initialized and cleaned up
```

### Pluggable Architecture
All major components are pluggable through abstract base classes and factory functions:
- `get_feed_processor()` - Auto-detects and returns appropriate feed parser
- `get_embedding_client()` - Returns configured embedding provider
- `get_vector_db_client()` - Returns configured vector database client

### Error Handling and Retries
- Uses `tenacity` library for retry logic with exponential backoff
- Structured logging with `structlog` for debugging
- Graceful degradation when optional components fail

### Concurrency Management
- Uses `asyncio.Semaphore` to limit concurrent operations
- Combines asyncio for I/O-bound tasks with ThreadPoolExecutor for CPU-bound tasks
- Task tracking and cancellation for clean shutdown

## Testing Strategy

### Test Files Structure
- `test_basic.py` - Tests core functionality without heavy dependencies
- `test_feeds.py` - Tests feed parsing with real blog URLs
- `monitor/tests/` - Unit tests for specific modules

### Testing Approach
- Uses dummy implementations for external services during testing
- Memory-based implementations for caches and databases in tests
- Async test support with `pytest-asyncio`
- Coverage tracking with minimum 80% threshold

## Troubleshooting Common Issues

### Playwright Browser Issues
```bash
# Reinstall browsers if rendering fails
poetry run playwright install --force

# Check browser dependencies
poetry run playwright install-deps
```

### Feed Processing Issues
- Check `.env` configuration for correct feed URLs
- Use `--log-level DEBUG` to see detailed feed parsing logs
- Clear cache if feeds aren't updating: `rm -rf cache/`

### Memory and Performance
- Adjust `MAX_CONCURRENT_TASKS` for your system resources
- Monitor browser pool size with `BROWSER__MAX_CONCURRENT_BROWSERS`
- Use Redis for caching in production to share state across instances

### Configuration Debugging
The configuration system provides detailed validation errors. Use:
```python
from monitor.config import load_settings
settings = load_settings()  # Will show validation errors
```

## Production Deployment

### Docker Deployment
The included Dockerfile is optimized for production:
- Multi-stage build to minimize image size
- Non-root user for security
- Pre-installed Playwright browsers
- Health check endpoint on port 8000

### Environment Considerations
- Set `ENVIRONMENT=production` for production logging
- Use external Redis for caching in multi-instance deployments
- Configure proper vector database connection strings
- Set appropriate resource limits in container orchestration

### Monitoring
- Prometheus metrics available when `METRICS__PROMETHEUS_ENABLED=true`
- Structured JSON logging when `METRICS__STRUCTURED_LOGGING=true`
- Health checks through metrics endpoint
