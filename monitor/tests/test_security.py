import pytest
import bleach
from monitor.feeds.base import parse_feed_entries

@pytest.mark.asyncio
async def test_xss_sanitization():
    # Malicious entry
    entries = [{
        "title": "Malicious Post",
        "link": "http://example.com/malicious",
        "summary": "This is a <script>alert('XSS')</script> test."
    }]
    
    posts = await parse_feed_entries(entries, "Test Feed", "http://example.com/feed")
    
    assert len(posts) == 1
    # Script tag should be removed
    assert "<script>" not in posts[0].summary
    assert "alert('XSS')" in posts[0].summary or "alert" in posts[0].summary # bleach might keep content but strip tags
    
    # Verify bleach behavior explicitly
    cleaned = bleach.clean("This is a <script>alert('XSS')</script> test.", tags=[], strip=True)
    assert cleaned == "This is a alert('XSS') test."

@pytest.mark.asyncio
async def test_large_payload_handling():
    # Create a very large summary
    large_summary = "A" * 100000
    entries = [{
        "title": "Large Post",
        "link": "http://example.com/large",
        "summary": large_summary
    }]
    
    posts = await parse_feed_entries(entries, "Test Feed", "http://example.com/feed")
    
    assert len(posts) == 1
    # Summary should be truncated (default limit is 500 chars in parse_feed_entries)
    assert len(posts[0].summary) <= 500
