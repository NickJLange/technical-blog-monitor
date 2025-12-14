# Project Structure & Organization

This document defines the standard file system layout for the Technical Blog Monitor project. Adhering to this structure ensures maintainability, discoverability, and a clean development environment.

## 📂 Standard Directory Layout

```
technical-blog-monitor/
├── monitor/                 # 📦 Main Python package (Source Code)
│   ├── feeds/               #    - Feed parsers (RSS, Atom, JSON)
│   ├── fetcher/             #    - HTTP & Browser clients
│   ├── extractor/           #    - Content cleaning & metadata
│   ├── embeddings/          #    - Vector embedding logic
│   ├── vectordb/            #    - Database adapters
│   ├── cache/               #    - Caching layer
│   └── web/                 #    - Web dashboard (if applicable)
│
├── tests/                   # 🧪 Top-level Tests (Integration/E2E)
│   ├── e2e/                 #    - End-to-End scenarios
│   └── integration/         #    - Component integration tests
│
├── docs/                    # 📚 Documentation
│   ├── architecture/        #    - Diagrams & Design docs
│   ├── guides/              #    - Container & Setup guides
│   └── reports/             #    - Test summaries & benchmarks
│
├── scripts/                 # 🛠 Utility Scripts
│   ├── maintenance/         #    - database_cleanup.py, etc.
│   └── dev/                 #    - local_setup.sh, etc.
│
├── data/                    # 💾 Data & Config Assets
│   ├── inputs/              #    - Seed files (sites.txt)
│   └── artifacts/           #    - Generated HTML/Screenshots (gitignored)
│
└── logs/                    # 📝 Runtime Logs (gitignored)
```

## 🧹 Current Refactoring Goals

The following items currently residing in the root directory have been identified for relocation:

### 1. Test Files → `tests/`
**Rationale:** Root-level tests clutter the workspace and mix concerns.
- `test_basic.py`
- `test_e2e_comprehensive.py`
- `test_e2e_simple.py`
- `test_feed_processor.py`
- `test_feeds.py`
- `test_full_pipeline.py`

### 2. Documentation → `docs/`
**Rationale:** Core docs (`README.md`, `CONTRIBUTING.md`, `AGENTS.md`) stay in root. Feature-specific or historical docs move.
- `CONTAINER_*.md` → `docs/guides/`
- `*_REPORT.md`, `*_SUMMARY.md` → `docs/reports/`
- `DEMO.md`, `SECURITY_FIX.md` → `docs/archive/`

### 3. Scripts → `scripts/`
**Rationale:** Executables should be grouped.
- `run_all_tests.sh`, `run_dashboard.sh`
- `generate_web_view.py`, `view_latest_entries.py`

### 4. Data & Artifacts → `data/` or `output/`
- `sites.txt` → `data/inputs/`
- `latest_articles.html` → `data/artifacts/`
- `*.log` → `logs/`

## 📏 File Placement Guidelines

1.  **Source Code:** Does it belong to the `monitor` package? Put it in `monitor/`.
2.  **Tests:** Is it a unit test? `monitor/tests/`. Is it a system/E2E test? `tests/`.
3.  **Config:** Application config goes in `.env`. Static data (lists of sites) goes in `data/`.
4.  **Temporary:** Logs and cache go to `logs/` and `cache/` respectively (and must be `.gitignore`d).
