# Technical Blog Monitor – Demo Guide

> A hands-on tour of the Python daemon we just scaffolded, using the **Uber Engineering Blog** as the target feed.

---

## 1 • What We Built

| Layer | Tech | Purpose |
|-------|------|---------|
| Scraper | `httpx`, `feedparser`, custom RSS/Atom/JSON processors | Detect new posts every hour |
| Renderer | `playwright` (headless Chromium) + async browser pool | Fully render pages & take screenshots |
| Extractor | `readability-lxml`, BeautifulSoup | Clean article text, pull metadata & images |
| Cache | pluggable (`postgres`, filesystem, in-mem) | Avoid re-fetching content |
| Embeddings | pluggable (`openai`, HF, or **dummy** for demo) | Generate text + image vectors |
| Vector DB | pluggable (`qdrant`, Chroma, Pinecone, or in-mem) | Store vectors for semantic search |
| Orchestrator | `asyncio`, `APScheduler` | Multithread/async daemon, graceful shutdown |
| Observability | `structlog`, Prometheus (opt) | Structured logs & metrics |

All settings are **env-driven** (`.env`), validated by **Pydantic**.

---

## 2 • Architecture Diagram

```
┌─ scheduler (APScheduler) ─ hourly ─┐
│                                    │
│         ┌─ feed processor (RSS) ───┤ fetches Uber Eng RSS/HTML
│         │                          │
│         │   new posts → asyncio TG │
│         ▼                          │
│   browser pool (Playwright)        │
│         │ render & screenshot      │
│         ▼                          │
│   extractor (readability)          │
│         │ text / meta / images     │
│         ▼                          │
│   embedding client (dummy)         │
│         │ text_vec  img_vec        │
│         ▼                          │
│   vector DB client (in-mem)        │
└───────── logs + metrics ───────────┘
```

---

## 3 • Running the Demo Locally

### 3.1  Install minimal deps

```bash
cd technical-blog-monitor
python -m pip install -r <(echo "
httpx feedparser readability-lxml beautifulsoup4
pydantic pydantic-settings structlog apscheduler
playwright aiofiles tenacity numpy python-dateutil
")
playwright install chromium
```

### 3.2  Configure

`.env` (already present) points **feed 0** to  
`https://www.uber.com/en-US/blog/engineering/` (Uber Engineering landing page – rendered, not RSS).  
The JSON/RSS processor autodetects format.

Key switches for the demo:

```
EMBEDDING__TEXT_MODEL_TYPE=custom   # uses DummyEmbeddingClient
VECTOR_DB__DB_TYPE=qdrant           # stub -> in-memory
CACHE__ENABLED=true                 # filesystem cache ./cache
```

### 3.3  One-shot run

```bash
python -m monitor.main --once --log-level DEBUG
```

Expected console highlights:

```
[INFO] Initializing browser pool …
[INFO] Processing feed 'Uber Engineering Blog'
[INFO] Found new posts count=1            # if a fresh item exists
[INFO] Rendered page and took screenshot  path=cache/screenshots/…
[INFO] Generated text embedding dim=1536  (dummy)
[INFO] Upserted record in in-mem VDB id=…
[INFO] Feed processing complete
```

Artifacts:

* `cache/screenshots/<timestamp>.png` – full-page screenshot
* Cached HTML/text under `cache/data/…`
* In-memory vector store populated with the embedding record.

---

## 4 • Inspecting Results

After the run open a Python REPL:

```python
>>> from monitor.vectordb import get_vector_db_client
>>> from monitor.config import VectorDBConfig, VectorDBType
>>> import asyncio, json

cfg = VectorDBConfig(db_type=VectorDBType.QDRANT, connection_string="memory://")
vdb = asyncio.run(get_vector_db_client(cfg))
print("Total points:", asyncio.run(vdb.count()))
```

You can also issue a similarity search with any sentence:

```python
q = "How Uber migrated workloads to Kubernetes"
emb = [0.001]*1536     # use dummy vector for demo
hits = asyncio.run(vdb.search_by_text(emb, limit=3))
for rec, score in hits:
    print(round(score,3), rec.title, rec.url)
```

---

## 5 • Key Features on Display

* **Format-agnostic feed discovery** – RSS/Atom/HTML auto-selection.
* **Async + thread pool mix** – HTTP & browser I/O vs. CPU extraction.
* **Pluggable everything** – swap dummy clients for real OpenAI/Qdrant by flipping `.env`.
* **Graceful shutdown & retries** – Tenacity auto-retries transient HTTP errors.

---

## 6 • Next Steps for Production

1. Swap `EMBEDDING__TEXT_MODEL_TYPE=openai` and add your key.
2. Point `VECTOR_DB__CONNECTION_STRING` to a running Qdrant.
3. Deploy the Docker image (`docker build -t blog-monitor .`) as a **K8s CronJob**.

---

## 7 • Troubleshooting Tips

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Playwright errors | Browsers not installed | `playwright install chromium` |
| “No new posts” | Cache holds fingerprint | Delete `cache/` or bump `FEEDS__0__CHECK_INTERVAL_MINUTES` |
| ImportError | Missing pip deps | rerun install snippet above |
| Headless blocked by robots | set `BROWSER__STEALTH_MODE=false` and tweak UA |

---

## 8 • Conclusion

You now have an **end-to-end multimodal ingestion pipeline** tailored for technical blogs, demonstrated with the Uber Engineering site. Replace dummy components with real services and schedule the daemon – you’ll never miss an engineering update again. 🚀
