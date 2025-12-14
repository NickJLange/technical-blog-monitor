# Container Deployment Guide

This guide covers running the Technical Blog Monitor as a containerized daemon using Podman or Docker.

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/NickJLange/technical-blog-monitor.git
cd technical-blog-monitor

# Start all services (PostgreSQL + Blog Monitor daemon)
docker-compose up -d

# View logs
docker-compose logs -f blog-monitor

# Stop services
docker-compose down
```

The system will be fully operational within 60 seconds:
- PostgreSQL with pgvector running on localhost:5432
- Blog monitor daemon running and processing feeds
- Data persisted to `./data` and `./cache` directories

### Using Podman

```bash
# Build the image
podman build -t technical-blog-monitor .

# Run with PostgreSQL
podman run -d \
  --name blogmon-postgres \
  -e POSTGRES_DB=blogmon \
  -e POSTGRES_USER=blogmon \
  -e POSTGRES_PASSWORD=password \
  pgvector/pgvector:pg16

podman run -d \
  --name blog-monitor \
  --link blogmon-postgres:postgres \
  -e VECTOR_DB__CONNECTION_STRING=postgresql://blogmon:password@postgres:5432/blogmon \
  -e CACHE__BACKEND=postgres \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/cache:/app/cache \
  technical-blog-monitor
```

## Configuration

### Environment Variables

The daemon is configured entirely via environment variables. Key categories:

#### Database Configuration

```bash
# Unified PostgreSQL storage (recommended)
VECTOR_DB__DB_TYPE=pgvector
VECTOR_DB__CONNECTION_STRING=postgresql://user:pass@host:5432/blogmon
CACHE__BACKEND=postgres
CACHE__POSTGRES_DSN=postgresql://user:pass@host:5432/blogmon

# OR memory cache (for testing)
CACHE__BACKEND=memory
VECTOR_DB__DB_TYPE=qdrant
VECTOR_DB__CONNECTION_STRING=http://qdrant:6333
```

#### Feed Configuration (indexed, 0-based)

```bash
FEEDS__0__NAME=AWS Blog
FEEDS__0__URL=https://aws.amazon.com/blogs/aws/feed/
FEEDS__0__CHECK_INTERVAL_MINUTES=60
FEEDS__0__MAX_POSTS_PER_CHECK=10
FEEDS__0__ENABLED=true

FEEDS__1__NAME=Azure Blog
FEEDS__1__URL=https://azure.microsoft.com/en-us/blog/feed/
# ... etc
```

#### Embedding Configuration

```bash
# Local embedding (no API key needed)
EMBEDDING__TEXT_MODEL_TYPE=sentence_transformers
EMBEDDING__TEXT_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDING__USE_GPU=false

# OR OpenAI
EMBEDDING__TEXT_MODEL_TYPE=openai
EMBEDDING__TEXT_MODEL_NAME=text-embedding-ada-002
EMBEDDING__OPENAI_API_KEY=sk-...
```

#### Browser Configuration

```bash
BROWSER__MAX_CONCURRENT_BROWSERS=2
BROWSER__TIMEOUT_SECONDS=30
BROWSER__HEADLESS=true
BROWSER__BLOCK_ADS=true
```

#### Article Processing

```bash
ARTICLE_PROCESSING__FULL_CONTENT_CAPTURE=true
ARTICLE_PROCESSING__CONCURRENT_ARTICLE_TASKS=2
ARTICLE_PROCESSING__MAX_ARTICLES_PER_FEED=20
ARTICLE_PROCESSING__ARCHIVE_HTML=true
ARTICLE_PROCESSING__ARCHIVE_SCREENSHOTS=false
```

#### Logging

```bash
METRICS__LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR, CRITICAL
METRICS__STRUCTURED_LOGGING=true
```

### Custom Environment File

Create a `.env` file for docker-compose:

```bash
# .env
POSTGRES_PASSWORD=your_secure_password
EMBEDDING__OPENAI_API_KEY=sk-your-key
FEEDS__0__URL=https://your-blog-feed.com/feed

# Start with custom env
docker-compose --env-file .env up -d
```

## Container Architecture

### Image Details

- **Base Image**: `python:3.12-slim` (minimal runtime, <150MB)
- **Build Stage**: Uses `uv` for fast Python dependency installation
- **Runtime User**: Non-root `blogmon` user for security
- **Playwright**: Chromium browser pre-installed in image

### Multi-stage Build

The Containerfile uses a two-stage build to keep the final image small:

1. **Builder stage**: Installs build tools and Python dependencies with uv
2. **Runtime stage**: Copies only necessary files, installs Playwright browsers

### Health Checks

```bash
# The container includes a health check that validates configuration loading
docker ps  # Shows (healthy) or (unhealthy)

# Manual health check
docker exec blog-monitor python -c "from monitor.config import load_settings; load_settings()"
```

## Volumes and Data

### Important Directories

```
/app/data/
  ├── screenshots/     # Article screenshots (optional)
  └── cache/          # Filesystem cache (if enabled)

/app/cache/           # Filesystem cache root
```

### Docker Compose Volume Mapping

```yaml
volumes:
  - ./data:/app/data           # Article data
  - ./cache:/app/cache         # Cache storage
  - postgres_data:/var/lib/postgresql/data  # Database
```

### Persisting Data

With docker-compose, data is automatically persisted in named volumes:

```bash
# View volume location
docker volume inspect blogmon_postgres_data

# Backup database
docker exec blogmon-postgres pg_dump -U blogmon blogmon > backup.sql

# Restore database
docker exec -i blogmon-postgres psql -U blogmon blogmon < backup.sql
```

## Networking

### Docker Compose Network

Services communicate via the `blogmon-network` bridge network:

```
blog-monitor:5432 → postgres (internal DNS name)
```

### Custom Networks

For external PostgreSQL:

```bash
podman run -d \
  --network host \
  -e VECTOR_DB__CONNECTION_STRING=postgresql://user@external-host:5432/blogmon \
  technical-blog-monitor
```

### Port Mapping

```bash
# Web dashboard (if enabled via METRICS)
docker-compose ports blog-monitor
# → 8080/tcp -> 0.0.0.0:8080

# PostgreSQL
docker-compose ports postgres
# → 5432/tcp -> 0.0.0.0:5432
```

## Monitoring and Logs

### View Logs

```bash
# Follow daemon logs
docker-compose logs -f blog-monitor

# Last 100 lines
docker-compose logs --tail 100 blog-monitor

# Timestamp format
docker-compose logs --timestamps blog-monitor

# With Podman
podman logs -f blog-monitor
```

### Structured Logging

When `METRICS__STRUCTURED_LOGGING=true` (default in docker-compose.yml):

```json
{"timestamp": "2025-12-14T03:13:20.716400Z", "level": "info", "event": "Processing feed", "feed_name": "AWS Blog"}
```

### Health Check Status

```bash
docker-compose ps  # Shows health status for each service

# Manual health check
docker-compose exec blog-monitor python -c "from monitor.config import load_settings; load_settings()" && echo "HEALTHY" || echo "UNHEALTHY"
```

## Performance Tuning

### Memory Limits

```yaml
services:
  blog-monitor:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

### CPU Limits

```yaml
services:
  blog-monitor:
    deploy:
      resources:
        limits:
          cpus: '2'
        reservations:
          cpus: '1'
```

### Browser Concurrency

```bash
# Control concurrent browser instances
BROWSER__MAX_CONCURRENT_BROWSERS=2

# Increase for more feeds, decrease for resource-constrained environments
```

### Connection Pool

```bash
# Adjust PostgreSQL connection pool size
# (configured in monitor/db/postgres_pool.py)
# Default: min_size=2, max_size=10
```

## Security Considerations

### Running as Non-Root

The container runs as user `blogmon` (UID 1000) for security:

```bash
docker run --user 1000:1000 technical-blog-monitor
```

### Secrets Management

Never commit `.env` files with secrets. Use Docker Secrets or a vault:

```bash
# Docker Secrets (Docker Swarm)
docker secret create openai_key -

# Docker Buildkit secrets (build-time)
docker build --secret openai_key=$(cat ~/.openai_key) .

# Or environment variable from secure storage
docker-compose -f docker-compose.yml up
# With EMBEDDING__OPENAI_API_KEY from .env (not committed)
```

### Network Isolation

```yaml
# Only expose necessary ports
ports:
  - "127.0.0.1:5432:5432"  # PostgreSQL only from localhost
  - "127.0.0.1:8080:8080"  # Web dashboard only from localhost
```

### Read-Only Filesystem (Advanced)

```yaml
services:
  blog-monitor:
    read_only: true
    tmpfs:
      - /tmp
      - /run
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
docker-compose logs blog-monitor

# Common issues:
# 1. PostgreSQL connection refused → Wait for postgres to be healthy
# 2. Missing OPENAI_API_KEY → Set EMBEDDING__TEXT_MODEL_TYPE=sentence_transformers
# 3. Out of disk space → Check /app/data and /app/cache
```

### High Memory Usage

```bash
# Reduce concurrent browsers
BROWSER__MAX_CONCURRENT_BROWSERS=1

# Reduce cache size
ARTICLE_PROCESSING__MAX_ARTICLES_PER_FEED=5
```

### Slow Feed Processing

```bash
# Enable structured logging to see timing
METRICS__STRUCTURED_LOGGING=true
METRICS__LOG_LEVEL=DEBUG

# Increase concurrency (if resources allow)
ARTICLE_PROCESSING__CONCURRENT_ARTICLE_TASKS=4
BROWSER__MAX_CONCURRENT_BROWSERS=3
```

### Database Connection Issues

```bash
# Verify PostgreSQL is running and healthy
docker-compose ps
# Status should show "healthy" for postgres

# Test connection from host
psql postgresql://blogmon:password@localhost:5432/blogmon

# Check for connection pool exhaustion
docker-compose logs postgres | grep "too many connections"
```

## Production Deployment

### Kubernetes

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: blog-monitor-config
data:
  VECTOR_DB__DB_TYPE: pgvector
  VECTOR_DB__CONNECTION_STRING: postgresql://blogmon@postgres:5432/blogmon
  CACHE__BACKEND: postgres
  METRICS__LOG_LEVEL: INFO
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: blog-monitor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: blog-monitor
  template:
    metadata:
      labels:
        app: blog-monitor
    spec:
      containers:
      - name: blog-monitor
        image: technical-blog-monitor:latest
        envFrom:
        - configMapRef:
            name: blog-monitor-config
        env:
        - name: EMBEDDING__OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: blog-monitor-secrets
              key: openai-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        healthCheck:
          exec:
            command:
            - python
            - -c
            - "from monitor.config import load_settings; load_settings()"
          initialDelaySeconds: 60
          periodSeconds: 30
```

### Docker Swarm

```bash
docker stack deploy -c docker-compose.yml blogmon

# Scale the daemon (note: single-instance safe)
docker service scale blogmon_blog-monitor=1

# View status
docker stack ps blogmon
```

## Building Custom Images

### Custom Base Image

```dockerfile
# Use your organization's base image
FROM your-registry/python:3.12-slim
COPY . /app
# ... rest of Containerfile
```

### Build Arguments

```bash
docker build \
  --build-arg PYTHON_VERSION=3.12 \
  --build-arg PLAYWRIGHT_BROWSER=chromium \
  -t technical-blog-monitor:custom .
```

## Maintenance

### Updating Dependencies

```bash
# Update uv.lock and rebuild
docker-compose build --no-cache blog-monitor

# Restart with new image
docker-compose down
docker-compose up -d
```

### Cleaning Up

```bash
# Stop and remove containers
docker-compose down

# Remove all data
docker-compose down -v

# Prune unused images/volumes
docker image prune -a
docker volume prune
```

## Reference

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Podman Documentation](https://docs.podman.io/)
- [pgvector Image](https://hub.docker.com/r/pgvector/pgvector)

---

**Generated**: 2025-12-14  
**Version**: 0.1.0  
**Status**: Production-Ready
