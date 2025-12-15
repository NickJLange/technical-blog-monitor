# Next Thread - Immediate Action Items

## PRIORITY 1: Fix Stripe Entry Count (1 → 20+)

**File:** `monitor/feeds/rss.py` lines 237-254 in `_parse_html_as_feed()`

**Current Code Problem:**
```python
# Strategy 1: Look for <article> elements
for article in soup.find_all('article'):
    link = article.find('a', href=True)  # ❌ ONLY GETS FIRST LINK
    if link:
        # ... extract this one link
```

**What Stripe Actually Has:**
- 20 `<article>` tags
- Each article likely has structure: `<article> > <h2/h3> > <a href="...">`
- But also has other links (breadcrumbs, etc.)

**Fix Approach:**
1. Look for the main article link more intelligently
2. Try: `article.find('h2') > find('a')` or `article.find('h3') > find('a')`
3. Or: Find the link with the longest text (likely the title)
4. Test locally first before deploying

**Test Command:**
```bash
cd /Users/njl/dev/src/mkai/technical-blog-monitor
uv run python3 << 'EOF'
# Use the debug script from earlier to verify fix works
# Should see 20 entries from Stripe instead of 1
EOF
```

---

## PRIORITY 2: Handle Spotify (JavaScript SPA)

**Issue:** Spotify Engineering uses Next.js - content loaded client-side, not in initial HTML

**Options:**
1. **Easy:** Create `SpotifyFeedProcessor` that uses browser pool (like Medium)
2. **Medium:** Auto-detect Next.js sites and route to browser processor
3. **Hard:** Try to find Spotify's actual API/RSS feed

**Recommended:** Option 1 - Create `SpotifyFeedProcessor`
- Copy `MediumFeedProcessor` as template
- Adjust for Spotify-specific HTML structure
- Add to `get_feed_processor()` detection

**File:** Create `monitor/feeds/spotify.py`

---

## PRIORITY 3: Improve Zero-Entry Sites

After Stripe/Spotify fixed, these need HTML extraction tuning:

### By difficulty:
1. **Slack Engineering** (12KB HTML)
   - Likely simple structure, check for `h2` or `h3` links
   
2. **Anthropic** (43KB malformed HTML)
   - Complex structure, may need BeautifulSoup lenient parsing
   
3. **GitLab Blog** (32KB HTML)
   - Known for complex markup
   
4. **Uber Engineering** (malformed RSS)
   - Has actual RSS feed but malformed XML
   - May need different parser or XML repair
   
5. **HashiCorp Blog** (35KB HTML)
   - Rate limiting works, but HTML structure unknown

**Approach:** For each site:
1. Save actual HTML response
2. Inspect structure in local environment
3. Add site-specific extraction logic or expand patterns
4. Test with feed-specific debug script

---

## PRIORITY 4: Fix Medium Browser Pool Integration

**Current Issue:**
- `MediumFeedProcessor` created but browser_pool not being passed
- Arises: `RuntimeError: Browser pool required for Medium blog`

**Files to Update:**
1. `monitor/main.py` - Pass browser_pool through call chain
2. `monitor/feeds/base.py` - ensure browser_pool passed to get_feed_processor()
3. `monitor/feeds/medium.py` - actually use browser_pool.render_and_screenshot()

**Affected Feeds:** Airbnb, Lyft, Netflix (Medium), + any others hosted on Medium

---

## Git Status
- Branch: `fix/feed-failures`
- 4 commits ready (including this session's work)
- All backward compatible
- No new dependencies

---

## Testing Command (After Fixes)

```bash
# Quick test specific feed
uv run python3 << 'EOF'
import asyncio
import httpx
from monitor.feeds.base import get_feed_processor
from monitor.config import FeedConfig
from pydantic import HttpUrl

async def test():
    config = FeedConfig(name="Stripe", url=HttpUrl("https://stripe.com/blog/engineering"))
    processor = await get_feed_processor(config)
    async with httpx.AsyncClient() as client:
        content = await processor.fetch_feed(client)
        entries = await processor.parse_feed(content)
        print(f"✅ {len(entries)} entries found")
        for e in entries[:3]:
            print(f"  - {e['title'][:50]}")

asyncio.run(test())
EOF
```

---

## Notes for Next Developer

- **Stripe fix is quick win:** Just improve article link detection in `_parse_html_as_feed()`
- **Spotify requires browser:** Will be similar to Medium processor pattern
- **Medium still broken:** browser_pool parameter passing incomplete
- **Remaining 403 errors:** Likely need browser rendering too (OpenAI, DoorDash, Docker, Twitter, Meta)
- **Success rate goal:** Get to 20+/30 feeds (67%+) before Phase 4 work

---

## Session Summary (Context)
- Started: ~37% success rate (11/30 feeds)
- Now: ~57% success rate (11/19 tested)
- Implemented: User-Agent spoofing, rate limiting, SSL fixes, HTTP 406 handling, HTML fallback parsing
- Created: Medium processor (not integrated), comprehensive feed status report
- Identified: Stripe/Spotify specific issues with root causes and fixes
