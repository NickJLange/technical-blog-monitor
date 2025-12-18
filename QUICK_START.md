# Quick Start Guide

## Run the Pipeline

```bash
# One-time run (processes all feeds once)
uv run monitor --once --log-level INFO

# Daemon mode (continuous monitoring)
uv run monitor --log-level INFO

# Single feed only
uv run monitor --once --feed "Redis Blog"
```

## View the Dashboard

```bash
# Start web server
uv run python monitor/dashboard.py

# Open browser to http://localhost:8080
```

## Dashboard Features

- **Statistics:** Total posts, today's posts, this week's posts
- **Browse:** List all articles with sources and dates
- **Filter:** Filter by feed source (dropdown)
- **Pagination:** Navigate through 143+ articles

## Current Status

- **Enabled Feeds:** 20
- **Disabled Feeds:** 7 (require Cloudflare bypass)
- **Total Articles:** 143
- **Last Updated:** Today
- **Database:** PostgreSQL + pgvector (1920-dimensional embeddings)

## Troubleshooting

### Dashboard not connecting?
```bash
# Check if PostgreSQL is running
psql postgresql://njl@192.168.100.23:5433/blogmon -c "SELECT COUNT(*) FROM blog_posts_technical_blog_posts;"
```

### Feed processing stuck?
```bash
# Check logs (add to .env if needed)
METRICS__LOG_LEVEL=DEBUG
```

### Clear cache and reprocess
```bash
# Clear feed cache
DELETE FROM cache_entries WHERE key LIKE 'feed:%';
```

## Configuration

Main settings in `.env`:
- **20 feeds** configured with `FEEDS__N__*` variables
- **Ollama models** specified for embeddings and LLM
- **PostgreSQL** for storage and caching

## Next Steps

1. **Monitor:** Let it run for a week to collect more articles
2. **Enable:** Add `cloudscraper` to unlock 5 Cloudflare-protected feeds
3. **Extend:** Add more feeds (50+ available tech blogs)
4. **Enhance:** Enable full content capture (when article extraction improved)

## Files to Check

- `.env` - Configuration
- `monitor/feeds/` - Feed processing logic
- `monitor/web/app.py` - Dashboard backend
- `FINAL_E2E_REPORT.md` - Detailed test results

---

**Status:** ✅ All systems operational - 143 articles ready to search
