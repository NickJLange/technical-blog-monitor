# JustHTML Migration State

**Last Updated:** 2025-12-15
**Previous Threads:** T-019b2075-cf63-7505-8603-1611fe6558c8, T-019b2067-b976-70fa-9170

## Summary

Migration of HTML parsing from BeautifulSoup to justhtml (Task 7 from session improvements). Partially complete with known issues.

## JustHTML Library Characteristics

- Pure Python HTML5 parser (100% spec compliant, passes all 9k+ html5lib tests)
- Zero C dependencies
- CSS selector support via `query()` method
- **READ-ONLY** - cannot modify the parsed DOM
- Uses `to_text()` instead of `get_text()`
- Uses `query()` instead of `select()`
- Does NOT support:
  - `decompose()` - cannot remove elements from tree
  - `extract()` - cannot extract elements from tree
  - `Comment` class for finding HTML comments
  - `NavigableString` for text nodes

## Files Changed

### Created
- `monitor/parser/html_parser.py` - Wrapper providing BeautifulSoup-like API over justhtml
- `monitor/parser/__init__.py` - Exports `HTMLParser` and `parse_html`

### Migrated to justhtml
- `monitor/extractor/image_extractor.py` - ✅ Complete
- `monitor/extractor/metadata.py` - ✅ Complete
- `monitor/feeds/rss.py` - ✅ Complete (lines 21, 145, 268, 391, 544)
- `monitor/feeds/browser_fallback.py` - Uses parse_html (line 17)

### Kept on BeautifulSoup (intentional)
- `monitor/extractor/article_parser.py` - Requires `decompose()` for removing noise elements (scripts, styles, comments)
  - Fixed missing import: `from bs4 import BeautifulSoup, Comment, NavigableString`

## HTMLParser Wrapper API

The wrapper (`monitor/parser/html_parser.py`) provides:

### HTMLParser class
- `find(name, **kwargs)` - Find first matching element
- `find_all(name, **kwargs)` - Find all matching elements
- `select(selector)` - CSS selector query
- `select_one(selector)` - First match for CSS selector
- `get_text()` - Extract all text content

### HTMLElement class
- `name` property - Tag name
- `attrs` property - Attributes dict
- `get(key, default)` - Get attribute value
- `find()` / `find_all()` - Search within element
- `get_text(separator, strip)` - Text content
- `parent` / `next_sibling` properties

### Supported attribute selectors in `_build_selector()`
- `class` - CSS class (string or list)
- `id` - Element ID
- `rel` - Link relation
- `type` - Element type (for `<script type="...">`)
- `property` - Meta property (for `og:*` Open Graph tags)
- `name` - Meta name (for `twitter:*` tags)
- `itemprop` - Schema.org markup
- `content` - Content attribute
- `attrs` dict - BeautifulSoup compatibility wrapper

## Known Issues

### 1. HTML-as-feed parsing not fully working
**Location:** `monitor/feeds/rss.py` `_parse_html_as_feed()` method (lines 252-500)

**Symptom:** Many feeds return HTML instead of RSS/XML. The fallback parser attempts to extract articles from HTML but fails to find entries for many sites.

**Affected feeds (return HTML, not RSS):**
- Slack Engineering
- Kafka
- Anthropic
- Google Cloud
- Stripe
- GitLab
- HashiCorp
- Redis
- Docker
- OpenAI
- Twitter/X
- LinkedIn

**Root cause options:**
1. Justhtml wrapper may not be returning correct types for chained operations
2. CSS selectors may not match the expected elements
3. Some sites need browser rendering to bypass bot detection

### 2. Fixed naming conflict
**Location:** `monitor/feeds/rss.py` line 267

**Problem:** Local function was named `parse_html()` which shadowed the imported `parse_html` from monitor.parser.

**Fix applied:** Renamed to `extract_entries_from_html()` and updated call at line 486.

### 3. Many feeds blocked (403/400 errors)
Sites with aggressive bot detection block HTTP requests. The `BrowserFallbackFeedProcessor` exists but may not be used for all affected feeds.

## Test Status

- All 20 unit tests pass
- Runtime feed processing has issues (see Known Issues above)

## Next Steps to Complete Migration

1. **Debug `_parse_html_as_feed`:**
   - Add more logging to trace why entries aren't being extracted
   - Check if `parser.find_all('article')` returns elements correctly
   - Verify `HTMLElement.find_all()` works for nested queries
   - Test with actual HTML from failing feeds

2. **Verify wrapper completeness:**
   - Check if `get_text(strip=True)` works correctly
   - Ensure `find_all(class_='author')` returns proper elements
   - Test chained operations like `article.find('time').get_text()`

3. **Consider browser fallback:**
   - Enable `BrowserFallbackFeedProcessor` for sites that return 403
   - Some sites (Medium, LinkedIn) require browser rendering

4. **Integration testing:**
   - Run monitor with `--once --log-level DEBUG` on specific feeds
   - Example: `uv run monitor --feed "Simon Willison" --once --log-level DEBUG`

## Commands for Debugging

```bash
# Run tests
uv run pytest -q

# Run with debug logging on specific feed
uv run monitor --feed "Simon Willison" --once --log-level DEBUG

# Check for BeautifulSoup remnants
grep -r "from bs4 import\|BeautifulSoup" monitor/ --include="*.py"

# Check justhtml usage
grep -r "parse_html\|from monitor.parser" monitor/ --include="*.py"
```

## Files to Review

```
monitor/parser/html_parser.py    # Main wrapper - check API correctness
monitor/feeds/rss.py             # Lines 252-500 (_parse_html_as_feed)
monitor/feeds/browser_fallback.py # For 403 handling
```
