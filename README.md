# Technical Blog Monitor

A high-performance Python daemon that tracks technical blogs from major companies, renders new posts in a headless browser, extracts rich text and screenshots, creates multimodal (text + image) embeddings, and stores them in a pluggable vector database for semantic search.

---

## ✨ Key Features
| Capability | Details |
|------------|---------|
| **Hour-level monitoring** | Configurable scheduler polls RSS/Atom feeds (or JSON endpoints) every N minutes. |
| **Async & Multithreaded** | Built on `asyncio` + thread pools for optimal I/O and CPU throughput. |
| **Headless rendering** | Uses Playwright (Chromium/Firefox/WebKit) to fully render pages and capture full-page screenshots. |
| **Content extraction** | Robust article parser turns raw HTML into clean text, metadata, and media links. |
| **Caching layer** | Redis + local filesystem cache to avoid redundant downloads and re-processing. |
| **Pluggable embeddings** | Generate text and image embeddings with OpenAI, HuggingFace, Sentence-Transformers, or custom models. |
| **Vector DB abstraction** | Works with Qdrant, Chroma, Pinecone, Milvus, Weaviate (choose at runtime). |
| **Observability** | Structured JSON logging, Prometheus metrics, graceful shutdown & retries. |
| **Container-ready** | Multi-stage Dockerfile with Playwright browsers pre-installed. |
| **Extensible** | Modular codebase—add new feeds, extractors, or DB back-ends with minimal changes. |

---

## 📂 Repository Layout

```
technical-blog-monitor/
├── monitor/                 # Python package
│   ├── config.py            # Pydantic settings
│   ├── main.py              # Entry point / daemon bootstrap
│   ├── feeds/               # Blog feed adapters
│   ├── fetcher/             # HTTP & browser workers
│   ├── extractor/           # Text/image extraction logic
│   ├── embeddings/          # Model wrappers
│   ├── vectordb/            # DB abstraction layer
│   ├── cache/               # Redis & filesystem helpers
│   └── tests/               # Pytest suite
├── Dockerfile
├── pyproject.toml           # Poetry dependency spec
└── README.md                # You are here
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/your-org/technical-blog-monitor.git
cd technical-blog-monitor

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Install Playwright browsers (one-time)
uv run playwright install
```

### 2. Configure

Copy the example environment file and edit values as needed:

```bash
cp .env.example .env
```

Key items to set:

* `FEEDS__0__URL`, `FEEDS__1__URL`, … — feeds to monitor  
* `EMBEDDING__OPENAI_API_KEY` _or_ `EMBEDDING__HUGGINGFACE_API_KEY`  
* `VECTOR_DB__CONNECTION_STRING` and optional `VECTOR_DB__API_KEY`

### 3. Run once (debug)

```bash
uv run monitor --once --log-level DEBUG
```

### 4. Daemon mode

```bash
uv run monitor                      # runs indefinitely
```

### 5. Docker

```bash
docker build -t blog-monitor .
docker run --env-file .env blog-monitor
```

---

## ⚙️ Configuration Reference

All settings are typed in `monitor/config.py` and can be supplied via:

1. `.env` file (recommended)
2. Environment variables
3. Command-line overrides (`--log-level`, `--feed`, `--once`)

### Main sections

| Prefix | Purpose |
|--------|---------|
| `FEEDS__` | Multiple feed definitions (name, url, interval, enabled) |
| `BROWSER__` | Playwright options (headless, viewport, concurrency) |
| `CACHE__` | Redis URL, TTL, local cache path |
| `EMBEDDING__` | Model selection, API keys, batch size |
| `VECTOR_DB__` | DB type, connection, collection & metric |
| `SCHEDULER__` | APScheduler store & timing options |
| `METRICS__` | Prometheus & log settings |

Nested keys use double underscores (`__`) as delimiter.

---

## 🛠️ Usage Examples

### Process a specific feed

```bash
uv run monitor --feed "Google Cloud Blog" --once
```

### Query stored vectors (example with Qdrant)

```python
from qdrant_client import QdrantClient
client = QdrantClient(url="http://localhost:6333")
hits = client.search(
    collection_name="technical_blog_posts",
    query_vector=[...]  # your embedding
)
for point in hits:
    print(point.payload["title"], point.payload["url"])
```

---

## 👩‍💻 Development Guide

### Pre-commit setup

```bash
uv sync --group dev
uv run pre-commit install
```

Hooks run `black`, `ruff`, `isort`, `mypy`, and unit tests.

### Testing

```bash
uv run pytest -q
```

### Linting & type-checking

```bash
uv run ruff check .          # style & static checks
uv run mypy monitor/   # type safety
```

### Branching

* `main` – stable releases  
* `dev` – active development  
* Feature branches: `feat/<topic>`  
* Use conventional commits for clear history.

---

## 📅 Roadmap

See the [project plan](docs/PLAN.md) for the 3-week milestone breakdown, future enhancements (summarization, UI dashboard, multi-tenant support), and open issues.

---

## 🤝 Contributing

Pull requests are welcome! Please open an issue first to discuss major changes.  
Make sure pre-commit hooks pass and tests cover new code.

---

## 🛡 License

This project is licensed under the MIT License – see `LICENSE` for details.

---

## 🙏 Acknowledgements

* Playwright team for reliable browser automation  
* Pydantic for ergonomic configuration  
* OpenAI & HuggingFace for amazing embedding models  
* Qdrant, Chroma, Pinecone, Milvus, Weaviate communities  
* All open-source contributors who make this ecosystem possible
