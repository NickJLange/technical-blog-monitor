# Feed Failure Fix Tasks

## 403 Forbidden - Sites Blocking Bot Access (6 feeds)
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

## Malformed/Invalid XML RSS Feeds (9 feeds)
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

## Rate Limiting / HTTP 429 (1 feed)
Site is rate-limiting requests

- [ ] HashiCorp Blog (hashicorp.com/blog)
  - Status: 429 Too Many Requests
  - Solution: Add request throttling, backoff strategy, or cache longer

---

## SSL/Certificate Errors (1 feed)
SSL verification failures

- [ ] Netflix Tech Blog (netflixtechblog.com)
  - Error: "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
  - Solution: Verify SSL cert chain; may need custom CA bundle or disable verification

---

## HTTP 406 Not Acceptable (1 feed)
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
