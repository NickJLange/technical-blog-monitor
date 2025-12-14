#!/usr/bin/env python3
"""Direct test of feed processing to generate sample data for web view."""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from monitor.cache import get_cache_client
from monitor.config import load_settings
from monitor.feeds.base import process_feed_posts
from monitor.fetcher.browser import BrowserPool


async def main():
    print("=" * 80)
    print("Feed Processing Test - Generating Web View Data")
    print("=" * 80)

    settings = load_settings()
    print("\nConfiguration loaded")
    print(f"  Feeds: {len(settings.feeds)}")
    print(f"  Cache backend: {settings.cache.backend.value}")

    # Initialize cache
    cache_client = await get_cache_client(settings.cache, settings.vector_db)
    print(f"\nCache initialized: {type(cache_client).__name__}")

    # Initialize browser pool
    browser_pool = BrowserPool(settings.browser)
    print("Browser pool initialized")

    try:
        # Process first feed
        if settings.feeds:
            feed = settings.feeds[0]
            print(f"\n{'='*80}")
            print(f"Processing feed: {feed.name}")
            print(f"URL: {feed.url}")
            print(f"{'='*80}\n")

            posts = await process_feed_posts(
                feed,
                cache_client,
                browser_pool,
                max_posts=feed.max_posts_per_check
            )

            print(f"\n{'='*80}")
            print(f"Results: {len(posts)} new posts found")
            print(f"{'='*80}\n")

            if posts:
                for i, post in enumerate(posts, 1):
                    print(f"{i}. {post.title}")
                    print(f"   URL: {post.url}")
                    print(f"   Published: {post.publish_date}")
                    print()

            # Create mock cache entries for web view generation
            print("\nGenerating cache entries for web view...")
            for i, post in enumerate(posts):
                cache_entry = {
                    "title": post.title,
                    "url": str(post.url),
                    "source": feed.name,
                    "publish_date": post.publish_date.isoformat() if post.publish_date else datetime.now().isoformat(),
                    "summary": f"Technical article from {feed.name}",
                    "content": f"Article content: {post.title}",
                }
                await cache_client.set(f"article_content:{i}", cache_entry)

            print(f"✓ Created {len(posts)} cache entries")

    finally:
        await browser_pool.close()
        await cache_client.close()

    print("\n" + "=" * 80)
    print("Feed processing complete")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
