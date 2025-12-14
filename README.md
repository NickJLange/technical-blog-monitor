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
| **Caching layer** | PostgreSQL-based cache with TTL support to avoid redundant downloads and re-processing. Memory cache for dev/test. |
| **Pluggable embeddings** | Generate text and image embeddings with OpenAI, HuggingFace, Sentence-Transformers, or custom models. |
| **Vector DB abstraction** | Primary support for **PgVector** (PostgreSQL) for efficient vector storage and search. |
| **Observability** | Structured JSON logging, Prometheus metrics, graceful shutdown & retries. |
| **Container-ready** | Multi-stage Dockerfile with Playwright browsers pre-installed. |
| **Extensible** | Modular codebase—add new feeds, extractors, or back-ends with minimal changes. |

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
│   ├── vectordb/            # DB abstraction layer (PgVector)
│   ├── cache/               # PostgreSQL & Memory caching
│   └── tests/               # Unit tests
├── tests/                   # Integration & E2E tests
├── docs/                    # Documentation
├── scripts/                 # Utility scripts
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
* `VECTOR_DB__CONNECTION_STRING` (PostgreSQL connection string)

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
| `CACHE__` | PostgreSQL DSN, TTL, backend selection (postgres/memory) |
| `EMBEDDING__` | Model selection, API keys, batch size |
| `VECTOR_DB__` | DB type (pgvector), connection, collection |
| `SCHEDULER__` | APScheduler store & timing options |
| `METRICS__` | Prometheus & log settings |

Nested keys use double underscores (`__`) as delimiter.

---

## 🛠️ Usage Examples

### Process a specific feed

```bash
uv run monitor --feed "Google Cloud Blog" --once
```

### Query stored vectors (PgVector)

The system automatically stores embeddings in the configured PostgreSQL database using the `pgvector` extension. You can query it using standard SQL or the `monitor.vectordb.pgvector` client.

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
# Run full test suite including E2E
bash scripts/run_all_tests.sh
```

For detailed testing instructions, see [docs/TESTING.md](docs/TESTING.md).

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
* PgVector for efficient vector similarity search in Postgres
* All open-source contributors who make this ecosystem possible
