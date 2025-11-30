# Testing Guide

This document provides instructions for testing the Technical Blog Monitor.

## Quick Start

### Prerequisites

- Python 3.12+
- `uv` package manager
- Playwright browsers installed

### Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install
```

## Running Tests

### Unit Tests

Run the full test suite:

```bash
uv run pytest
```

Run specific test files:

```bash
# Feed processor tests
uv run pytest monitor/tests/test_feed_processor.py

# Article parser tests
uv run pytest monitor/tests/test_article_parser.py

# Security tests
uv run pytest monitor/tests/test_security.py
```

Run with coverage:

```bash
uv run pytest --cov=monitor --cov-report=html
```

### Integration Tests

Run basic integration tests:

```bash
# Test core functionality
uv run python test_basic.py

# Test feed parsing
uv run python test_feeds.py

# Test full pipeline
uv run python test_full_pipeline.py
```

## Running the Monitor

### One-Time Run

Process all configured feeds once and exit:

```bash
uv run monitor --once --log-level INFO
```

Process a specific feed:

```bash
uv run monitor --feed "AWS Blog" --once --log-level DEBUG
```

### Daemon Mode

Run continuously (processes feeds at configured intervals):

```bash
uv run monitor --log-level INFO
```

### Using Different Configurations

Use a specific environment file:

```bash
# Copy and modify the example
cp .env.example .env
# Edit .env with your settings
uv run monitor --once
```

Use Ollama for local embeddings:

```bash
cp .env.ollama .env
uv run monitor --once
```

## Test Scripts

### test_basic.py

Tests core functionality without heavy dependencies:

```bash
uv run python test_basic.py
```

**Tests:**
- Content extraction
- Embedding generation (dummy client)
- Vector database operations (in-memory)
- Caching

### test_feeds.py

Tests feed parsing for specific blogs:

```bash
uv run python test_feeds.py
```

**Tests:**
- RSS/Atom feed parsing
- Post extraction
- Feed-specific configurations

### test_full_pipeline.py

Tests the complete monitoring pipeline:

```bash
uv run python test_full_pipeline.py
```

**Tests:**
- Full application lifecycle
- Feed processing
- Browser rendering
- Embedding generation
- Vector storage

## Configuration

### Environment Variables

Key configuration options (see `.env.example` for full list):

```bash
# Feeds
FEEDS__0__NAME=AWS Blog
FEEDS__0__URL=https://aws.amazon.com/blogs/aws/feed/
FEEDS__0__ENABLED=true

# Embeddings
EMBEDDING__TEXT_MODEL_TYPE=custom  # or openai, ollama
EMBEDDING__EMBEDDING_DIMENSIONS=384

# Vector DB
VECTOR_DB__DB_TYPE=qdrant
VECTOR_DB__CONNECTION_STRING=http://localhost:6333

# Browser
BROWSER__HEADLESS=true
BROWSER__MAX_CONCURRENT_BROWSERS=2
```

### Testing Without External Services

For testing without OpenAI, Ollama, or vector databases:

1. Use `EMBEDDING__TEXT_MODEL_TYPE=custom` (dummy embeddings)
2. Use `VECTOR_DB__DB_TYPE=qdrant` with stub client
3. Set `CACHE__ENABLED=true` with filesystem cache

## Debugging

### Verbose Logging

```bash
uv run monitor --once --log-level DEBUG
```

### Check Configuration

```bash
uv run python -c "from monitor.config import load_settings; s = load_settings(); print(f'Feeds: {len(s.feeds)}')"
```

### Clear Cache

```bash
rm -rf cache/*
rm -rf data/*
```

## Common Issues

### Ollama Connection Errors

If using Ollama embeddings:

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if needed
ollama serve
```

### Playwright Browser Issues

```bash
# Reinstall browsers
uv run playwright install --force
```

### Feed Parsing Errors

Some feeds may have invalid XML/HTML. Check logs for specific errors:

```bash
uv run monitor --once --log-level DEBUG 2>&1 | grep -i error
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: astral-sh/setup-uv@v1
      - run: uv sync
      - run: uv run playwright install --with-deps
      - run: uv run pytest
```

## Performance Testing

Monitor processing time:

```bash
time uv run python test_full_pipeline.py
```

Check memory usage:

```bash
/usr/bin/time -l uv run python test_full_pipeline.py
```
