# Container Quick Start

## 30-Second Setup

```bash
# Start everything (PostgreSQL + daemon)
docker-compose up -d

# Watch logs
docker-compose logs -f blog-monitor

# Verify services are running
docker-compose ps

# Stop everything
docker-compose down
```

## Common Commands

### Logs & Monitoring
```bash
docker-compose logs blog-monitor            # View daemon logs
docker-compose logs -f blog-monitor         # Follow logs
docker-compose logs --tail 50 blog-monitor  # Last 50 lines
docker-compose ps                           # Service status + health
```

### Database Access
```bash
docker-compose exec postgres psql -U blogmon -d blogmon
SELECT COUNT(*) FROM blog_posts_technical_blog_posts;
\q  # Exit psql
```

### Configuration
```bash
# Edit docker-compose.yml to change:
# - Feed URLs
# - Processing settings
# - Logging level
# - API keys

docker-compose up -d --force-recreate  # Apply changes
```

### Cleanup
```bash
docker-compose down          # Stop services
docker-compose down -v       # Stop + delete data
docker image prune           # Remove old images
docker volume prune          # Remove orphaned volumes
```

## Configuration Examples

### Using OpenAI Embeddings
```bash
# Add to docker-compose.yml or .env:
EMBEDDING__TEXT_MODEL_TYPE=openai
EMBEDDING__TEXT_MODEL_NAME=text-embedding-ada-002
EMBEDDING__OPENAI_API_KEY=sk-your-key-here
```

### Using Sentence Transformers (No API Key)
```bash
# Already set in docker-compose.yml by default
EMBEDDING__TEXT_MODEL_TYPE=sentence_transformers
EMBEDDING__TEXT_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDING__USE_GPU=false
```

### Add More Feeds
```bash
FEEDS__3__NAME=My Custom Blog
FEEDS__3__URL=https://myblog.com/feed
FEEDS__3__MAX_POSTS_PER_CHECK=10
FEEDS__3__ENABLED=true
```

### Enable Web Dashboard
```bash
METRICS__ENABLED=true
# Then access http://localhost:8080
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `postgres: connection refused` | Wait 30s for postgres to start, then restart blog-monitor |
| `Missing OpenAI API key` | Use sentence_transformers (no key needed) or set API key |
| `Out of memory` | Reduce `BROWSER__MAX_CONCURRENT_BROWSERS` to 1 |
| `Slow processing` | Reduce `ARTICLE_PROCESSING__MAX_ARTICLES_PER_FEED` |
| `Container keeps restarting` | Check logs: `docker-compose logs blog-monitor` |

## Resource Usage

Typical resource consumption:

```
PostgreSQL + Blog Monitor:
  Memory: ~500MB - 2GB (depends on cache size)
  CPU: 0-50% (spiky during feed processing)
  Disk: 500MB - 5GB (depends on articles cached)
```

## Stopping vs Removing

```bash
docker-compose stop              # Pause services (data persists)
docker-compose start             # Resume services

docker-compose down              # Stop and remove containers
docker-compose down -v           # Stop, remove containers AND data

docker-compose restart           # Stop then start all services
```

## Health Checks

```bash
# Check individual service health
docker-compose exec postgres pg_isready -U blogmon
docker-compose exec blog-monitor python -c "from monitor.config import load_settings; load_settings()"

# View health status
docker-compose ps
```

## Performance

Optimize for your environment:

```yaml
# .env or docker-compose.yml
BROWSER__MAX_CONCURRENT_BROWSERS=2      # 1=slow, 2=balanced, 3+=fast
ARTICLE_PROCESSING__CONCURRENT_ARTICLE_TASKS=2
CACHE__CACHE_TTL_HOURS=168              # 1 week default
```

## Next Steps

- Read [CONTAINER_GUIDE.md](CONTAINER_GUIDE.md) for detailed documentation
- Check [.env.example](.env.example) for all configuration options
- View [README.md](README.md) for project overview
- See [AGENTS.md](AGENTS.md) for architecture details

---

**Need help?** Check the logs: `docker-compose logs -f blog-monitor`
