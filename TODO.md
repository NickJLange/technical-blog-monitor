# Technical Blog Monitor - TODO

## Feed Failure Fix Tasks

### 403 Forbidden - Sites Blocking Bot Access (6 feeds)
Requires User-Agent spoofing, JavaScript rendering, or login handling

- [ ] Airbnb Engineering (medium.com/airbnb-engineering)
  - Status: 403 Forbidden
  - Solution: Medium blocks bots; need browser rendering or API alternative
  
- [ ] OpenAI Blog (openai.com/blog/)
  - Status: 403 Forbidden
  - Solution: Possibly bot detection; try User-Agent variation
  
- [ ] DoorDash Engineering (careersatdoordash.com/career-areas/engineering/)
  - Status: 403 Forbidden
  - Solution: May require JavaScript execution
  
- [ ] Docker Blog (docker.com/blog/)
  - Status: 403 Forbidden
  - Solution: Bot detection or rate limiting
  
- [ ] Lyft Engineering (eng.lyft.com)
  - Status: 403 Forbidden (redirects to medium.com identity)
  - Solution: Medium platform; need special handling
  
- [ ] Twitter Engineering (blog.twitter.com/engineering/)
  - Status: 403 Forbidden
  - Solution: May need API authentication

---

### Malformed/Invalid XML RSS Feeds (9 feeds)
Feeds return HTML or invalid XML instead of proper RSS/Atom

- [ ] Google Cloud Blog (cloud.google.com/blog/)
  - Error: "<unknown>:2:0: syntax error"
  - Solution: Auto-detect HTML; switch to scraping or find proper feed URL
  
- [ ] Anthropic (anthropic.com/news)
  - Error: "<unknown>:2:49039: not well-formed (invalid token)"
  - Solution: Non-standard feed format; may need custom parser
  
- [ ] Apache Kafka (kafka.apache.org/blog)
  - Error: "<unknown>:37:16: not well-formed (invalid token)"
  - Solution: Malformed XML; try cleanup or web scraping
  
- [ ] GitLab Blog (about.gitlab.com/blog/)
  - Error: "<unknown>:2:382: not well-formed (invalid token)"
  - Solution: May need to find RSS endpoint; currently returns HTML
  
- [ ] Slack Engineering (slack.engineering/)
  - Error: "<unknown>:2:0: syntax error"
  - Solution: Returns HTML; implement HTML parsing fallback
  
- [ ] Stripe Engineering (stripe.com/blog/engineering)
  - Error: "<unknown>:10:0: not well-formed (invalid token)"
  - Solution: Invalid XML; find proper RSS feed or use scraper
  
- [ ] Redis Blog (redis.com/blog/)
  - Error: "<unknown>:2:6725: not well-formed (invalid token)"
  - Solution: Feed has encoding/XML issues
  
- [ ] Meta AI (ai.meta.com/blog/)
  - Error: "<unknown>:4:1420: not well-formed (invalid token)"
  - Solution: Malformed RSS response
  
- [ ] Spotify Engineering (engineering.atspotify.com/)
  - Error: "<unknown>:2:34872: not well-formed (invalid token)"
  - Solution: Invalid RSS structure
  
- [ ] LinkedIn Engineering (linkedin.com/blog/engineering)
  - Error: "<unknown>:60:15: mismatched tag"
  - Solution: Malformed feed response

---

### Rate Limiting / HTTP 429 (1 feed)
Site is rate-limiting requests

- [ ] HashiCorp Blog (hashicorp.com/blog)
  - Status: 429 Too Many Requests
  - Solution: Add request throttling, backoff strategy, or cache longer

---

### SSL/Certificate Errors (1 feed)
SSL verification failures

- [ ] Netflix Tech Blog (netflixtechblog.com)
  - Error: "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
  - Solution: Verify SSL cert chain; may need custom CA bundle or disable verification

---

### HTTP 406 Not Acceptable (1 feed)
Server rejecting request format

- [ ] Uber Engineering (uber.com/en-US/blog/engineering/)
  - Status: 406 Not Acceptable
  - Solution: May need to adjust Accept headers or User-Agent

---

## Implementation Strategy

### Phase 1: Quick Wins
1. **User-Agent Spoofing**: Apply to all feeds (may fix some 403s)
2. **SSL Fix**: Netflix - update certificates
3. **Rate Limiting**: HashiCorp - implement exponential backoff

### Phase 2: Feed Detection & Fallback
4. **RSS Feed Discovery**: Auto-detect actual RSS endpoints (common for Slack, GitLab, etc.)
5. **HTML Fallback Parser**: For sites returning HTML instead of RSS

### Phase 3: Browser Rendering (If Needed)
6. **JavaScript Rendering**: For sites requiring execution (Airbnb, some Medium blogs)
7. **Cookie/Auth Handling**: For protected content (Twitter, LinkedIn)

### Phase 4: Custom Integrations
8. **API Alternatives**: Use official APIs where available (GitHub, etc.)
9. **Web Scraping**: Last resort for sites without proper feeds

---

## Notes
- Current success rate: 11/30 feeds (37%)
- Total posts ingested: 44
- Focus on malformed XML feeds first (9) - likely quick wins with better feed detection
- 403 Forbidden errors may require browser-based approaches or alternative sources

---

## Knowledge Retention & Enhanced Summarization

### ⚠️ Phase 2 - Enhanced Summarization (PARTIAL)
*   ✅ Implemented full LLM summarization pipeline using Ollama (Olmo-3-7B model).
*   ✅ Summaries are insight-focused, 256-token limit, stored in article metadata.
*   ✅ Increased timeout to 300s for slower local models.
*   ❌ **Currently DISABLED** (`generate_summary: bool = False`) - causing pipeline slowdowns

**Tasks:**
- [ ] Identify and fix what's causing summarization bottlenecks (timeout? model performance?)
- [ ] Profile summarization performance on Olmo-3-7B
- [ ] Consider async queue for LLM generation (non-blocking)
- [ ] Add configurable summary length/prompt templates
- [ ] Re-enable with optimizations and test at scale across 30 blogs
- [ ] Reference: `monitor/main.py` lines 329-338, `monitor/llm/ollama.py`

### ❌ Phase 3 - Spaced Repetition Review System (NOT STARTED)
*   Current state: Infrastructure exists but not wired up
*   Tests exist: `tests/integration/test_knowledge_retention.py`

**Tasks:**
- [ ] Implement `mark_as_read` API endpoint (`/api/posts/{id}/mark-read`)
- [ ] Implement `get_due_reviews` query (returns posts where `next_review_at <= now`)
- [ ] Add metadata fields: `read_status`, `read_at`, `next_review_at`, `review_stage`
- [ ] Implement review scheduling: Stage 1 (30 days), Stage 2 (90 days), Stage 3 (archived)
- [ ] Update web dashboard with "Review Queue" tab
- [ ] Add "Mark as Read" button to article cards
- [ ] Add review card view (shows enhanced summary instead of full text)
- [ ] Add review completion endpoint (progress to next stage)
- [ ] Reference: `monitor/vectordb/pgvector.py` (add `get_due_reviews()` query)

---

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

---

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
