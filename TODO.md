# TODO.md - Opinionated Refactors for Future Work

This document outlines a list of opinionated refactoring goals to further improve the codebase's maintainability, performance, and reliability. These items are noted for future consideration and are aligned with established software engineering best practices.

## 🌟 Web View & Content Enhancements

*   **Improve Article Summaries:**
    *   Current state: Summaries are aggressively truncated to 200 characters in the web view.
    *   Goal: Increase limit, implement "Read More" expansion, and improve fallback logic when metadata description is missing.
*   **Display Article Images:**
    *   Current state: Images are extracted but not displayed in the web view.
    *   Goal: Render the main "hero" image for each article in the dashboard card.
*   **Local Image Caching:**
    *   Current state: Images are hotlinked (original URLs preserved).
    *   Goal: Implement an option to download and cache images locally to prevent link rot and improve privacy.
*   **Better Image Extraction:**
    *   Current state: `extract_article_content` gets all images but doesn't smartly pick a hero image.
    *   Goal: Wire up `image_extractor.get_main_image` to the main pipeline.

## 🧠 Knowledge Retention & Enhanced Summarization

*   **✅ COMPLETED: Address `pgvector` Embedding Dimension Limit via MRL:**
    *   Previous state: `pgvector` indices have hard limit of 2000 dimensions. Qwen3-8B outputs 4096 dimensions.
    *   Solution: Implemented Matryoshka Representation Learning (MRL) truncation. Qwen3-8B embeddings now truncated to 1920 dimensions via `EMBEDDING__EMBEDDING_DIMENSIONS` config.
    *   Status: Working in production with HNSW indexing strategy.
    *   Reference: Commits 65af53a, e10a1f7

*   **⚠️ Phase 2 - Enhanced Summarization (PARTIAL):**
     *   ✅ Implemented full LLM summarization pipeline using Ollama (Olmo-3-7B model).
     *   ✅ Summaries are insight-focused, 256-token limit, stored in article metadata.
     *   ✅ Increased timeout to 300s for slower local models.
     *   ❌ **Currently DISABLED** (`generate_summary: bool = False`) - causing pipeline slowdowns
     *   **Tasks:**
         - [ ] Identify and fix what's causing summarization bottlenecks (timeout? model performance?)
         - [ ] Profile summarization performance on Olmo-3-7B
         - [ ] Consider async queue for LLM generation (non-blocking)
         - [ ] Add configurable summary length/prompt templates
         - [ ] Re-enable with optimizations and test at scale across 30 blogs
         - [ ] Reference: `monitor/main.py` lines 329-338, `monitor/llm/ollama.py`

*   **❌ Phase 3 - Spaced Repetition Review System (NOT STARTED):**
     *   Current state: Infrastructure exists but not wired up
     *   Tests exist: `tests/integration/test_knowledge_retention.py`
     *   **Tasks:**
         - [ ] Implement `mark_as_read` API endpoint (`/api/posts/{id}/mark-read`)
         - [ ] Implement `get_due_reviews` query (returns posts where `next_review_at <= now`)
         - [ ] Add metadata fields: `read_status`, `read_at`, `next_review_at`, `review_stage`
         - [ ] Implement review scheduling: Stage 1 (30 days), Stage 2 (90 days), Stage 3 (archived)
         - [ ] Update web dashboard with "Review Queue" tab
         - [ ] Add "Mark as Read" button to article cards
         - [ ] Add review card view (shows enhanced summary instead of full text)
         - [ ] Add review completion endpoint (progress to next stage)
         - [ ] Reference: `monitor/vectordb/pgvector.py` (add `get_due_reviews()` query)

## 🚀 Refactoring Goals

*   **Standardize Error Handling:** Implement a consistent, application-wide error handling strategy (e.g., custom exception classes, centralized error logging, user-friendly error messages).
*   **Optimize Database Queries:** Review and optimize frequently executed database queries for performance, including proper indexing, eager loading, and avoiding N+1 problems.
*   **Implement Caching Layer:** Further enhance or refine the caching strategy to reduce database load and improve response times, potentially introducing more granular control or additional cache types where beneficial.
*   **Refactor Auth Module:** If applicable, refactor any authentication/authorization logic for clarity, security, and scalability, potentially integrating with standard libraries or frameworks.
*   **Add Input Validation:** Implement robust input validation at all service boundaries (e.g., API endpoints, external data ingests) to prevent invalid data and security vulnerabilities.
*   **Improve Logging:** Enhance existing logging with more context, structured data, and appropriate log levels to facilitate debugging, monitoring, and auditing.
*   **Enhance Test Coverage:** Increase unit, integration, and end-to-end test coverage to ensure code quality, prevent regressions, and validate system behavior.
*   **Update Dependencies:** Regularly review and update project dependencies to leverage new features, security fixes, and performance improvements.
*   **Document API Endpoints:** Provide comprehensive documentation for all API endpoints, including request/response schemas, authentication requirements, and error codes.
*   **Centralize Configuration:** Refine and centralize application configuration management to reduce redundancy and simplify deployment across different environments.