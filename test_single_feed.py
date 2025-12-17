#!/usr/bin/env python3
"""Test a single feed processing."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings, FeedConfig
from monitor.feeds.base import process_feed_posts
from monitor.cache import get_cache_client

async def main():
    settings = load_settings()
    
    # Create a simple Anthropic feed config (should be newer)
    feed_config = FeedConfig(
        name="Anthropic",
        url="https://www.anthropic.com/news",
        enabled=True,
    )
    
    # Use the configured cache
    cache = await get_cache_client(settings.cache)
    
    print(f"Processing feed: {feed_config.name}")
    print(f"URL: {feed_config.url}")
    
    # Create a no-op cache to bypass dedup
    class NoCache:
        async def get(self, key):
            return None
        async def set(self, key, value, ttl=None):
            return True
        async def delete(self, key):
            return True
        async def exists(self, key):
            return False
    
    # Process the feed with a no-cache to get all posts
    posts = await process_feed_posts(
        feed_config,
        NoCache(),
        browser_pool=None,
        max_posts=5
    )
    
    print(f"\nFound {len(posts)} posts")
    for i, post in enumerate(posts[:3], 1):
        print(f"\n[{i}] {post.title}")
        print(f"    URL: {post.url}")
        print(f"    Source: {post.source}")
        print(f"    Author: {post.author}")
        print(f"    Tags: {post.tags}")

if __name__ == "__main__":
    asyncio.run(main())
