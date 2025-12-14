#!/usr/bin/env python3
"""
Test script for feed parsing functionality of the technical blog monitor.

This script tests the feed parsing capabilities for both the Uber Engineering blog
and the AI META blog without requiring heavy dependencies like Playwright.
It focuses on:
1. Feed discovery and format detection
2. Post extraction and parsing
3. Basic metadata extraction

Run this script to verify that the feed parsing components are working correctly.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path if needed
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import necessary modules
# Configure logging
import structlog

from monitor.cache import MemoryCacheClient
from monitor.cache.memory import MemoryCacheClient
from monitor.config import CacheConfig, FeedConfig
from monitor.feeds.base import get_feed_processor, process_feed_posts

logger = structlog.get_logger()
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
)

# Test configurations for the blogs
BLOG_CONFIGS = [
    {
        "name": "Uber Engineering Blog",
        "url": "https://www.uber.com/en-US/blog/engineering/",
        "check_interval_minutes": 60,
        "max_posts_per_check": 5,
        "enabled": True
    },
    {
        "name": "AI META Blog",
        "url": "https://ai.facebook.com/blog/",
        "check_interval_minutes": 60,
        "max_posts_per_check": 5,
        "enabled": True
    }
]


class DummyBrowserPool:
    """Dummy browser pool that does nothing but satisfies the interface."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def render_and_screenshot(self, url: str) -> str:
        """Dummy implementation that just returns a fake path."""
        return f"dummy_screenshot_{hash(url) % 1000}.png"


async def test_feed_parsing(feed_config: FeedConfig) -> None:
    """
    Test feed parsing for a given feed configuration.
    
    Args:
        feed_config: Feed configuration to test
    """
    print(f"\n{'=' * 50}")
    print(f"Testing feed: {feed_config.name} ({feed_config.url})")
    print(f"{'=' * 50}")

    # Create a memory cache client
    cache_config = CacheConfig(enabled=True)
    cache_client = MemoryCacheClient(cache_config)

    # Create a dummy browser pool (not actually used for feed parsing)
    browser_pool = DummyBrowserPool()

    try:
        # Get the feed processor
        feed_processor = await get_feed_processor(feed_config)
        print(f"Feed processor type: {type(feed_processor).__name__}")

        # Process the feed
        print("Processing feed...")
        posts = await process_feed_posts(
            feed_config,
            cache_client,
            browser_pool,
            max_posts=feed_config.max_posts_per_check
        )

        # Display results
        if not posts:
            print("No posts found or all posts already processed.")
        else:
            print(f"Found {len(posts)} posts:")
            for i, post in enumerate(posts):
                print(f"\n--- Post {i+1} ---")
                print(f"Title: {post.title}")
                print(f"URL: {post.url}")
                print(f"Author: {post.author or 'Unknown'}")
                print(f"Published: {post.publish_date or 'Unknown'}")
                print(f"Tags: {', '.join(post.tags) if post.tags else 'None'}")
                if post.summary:
                    print(f"Summary: {post.summary[:150]}...")

    except Exception as e:
        print(f"Error processing feed: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Clean up
        await cache_client.close()


async def main() -> None:
    """Run tests for all configured blogs."""
    print("Technical Blog Monitor - Feed Parsing Test")
    print(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Testing {len(BLOG_CONFIGS)} feeds")

    # Test each feed
    for config_dict in BLOG_CONFIGS:
        feed_config = FeedConfig(**config_dict)
        await test_feed_parsing(feed_config)

    print("\nAll feed tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
