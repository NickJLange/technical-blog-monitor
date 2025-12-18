import asyncio
import httpx
from monitor.config import FeedConfig, load_settings
from monitor.feeds.base import get_feed_processor

async def test_feed(feed_config: FeedConfig):
    try:
        processor = await get_feed_processor(feed_config, browser_pool=None)
        async with httpx.AsyncClient() as client:
            try:
                content = await processor.fetch_feed(client)
                entries = await processor.parse_feed(content)
                posts = await processor.extract_posts(entries)
                print(f"✓ {feed_config.name:30s} - {len(posts):2d} articles")
                return len(posts) > 0
            except Exception as e:
                print(f"✗ {feed_config.name:30s} - {str(e)[:60]}")
                return False
    except Exception as e:
        print(f"✗ {feed_config.name:30s} - {str(e)[:60]}")
        return False

async def main():
    settings = load_settings()
    enabled_feeds = [f for f in settings.feeds if f.enabled]
    
    print(f"\nTesting {len(enabled_feeds)} feeds...\n")
    
    results = []
    for feed in enabled_feeds:
        result = await test_feed(feed)
        results.append((feed.name, result))
    
    print(f"\n\nSummary:")
    working = sum(1 for _, r in results if r)
    print(f"Working: {working}/{len(results)}")

asyncio.run(main())
