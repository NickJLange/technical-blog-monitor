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

*   **Address `pgvector` Embedding Dimension Limit:**
    *   Current state: `pgvector` indices (both `ivfflat` and `hnsw`) have a hard limit of 2000 dimensions. The currently specified embedding model (`Qwen3-Embedding-8B`) outputs 4096 dimensions, making it incompatible.
    *   Goal: Identify and configure an Ollama-compatible embedding model that outputs **2000 dimensions or fewer**.
*   **Evaluate Improved LLM Models:** Research and integrate better LLM models for summarization and other generation tasks, moving beyond initial defaults to more performant or cost-effective options. (This is distinct from the immediate `pgvector` embedding compatibility issue).
*   **Implement Spaced Repetition UI:**
    *   Current state: Backend APIs exist for marking as read and retrieving review items.
    *   Goal: Update the web dashboard (`monitor/web/templates/index.html`) to expose "Mark as Read" functionality and a "Review Queue" tab.

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