#!/usr/bin/env python3
"""
Test script to verify Cloudflare-protected feeds work with cloudscraper.
"""
import asyncio
import sys
from pathlib import Path

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings, FeedConfig
from monitor.feeds.base import (
    process_feed_posts,
    _is_cloudflare_protected,
)
from monitor.cache import get_cache_client
import structlog

logger = structlog.get_logger()


async def test_cloudflare_feeds():
    """Test the Cloudflare-protected feeds."""
    print("=" * 80)
    print("Testing Cloudflare-Protected Feeds with cloudscraper")
    print("=" * 80)
    
    # Load settings
    settings = load_settings()
    
    # Initialize cache
    cache_client = await get_cache_client(settings.cache, settings.vector_db)
    
    try:
        # Cloudflare feeds to test
        cf_feeds = [
            'OpenAI Blog',
            'Docker Blog',
            'Twitter Engineering',
            'DoorDash Engineering',
            'Meta AI',
        ]
        
        results = {}
        
        for feed_name in cf_feeds:
            feed_config = settings.get_feed_by_name(feed_name)
            if not feed_config:
                print(f"❌ Feed '{feed_name}' not found in configuration")
                results[feed_name] = False
                continue
            
            if not feed_config.enabled:
                print(f"⏭️  Feed '{feed_name}' is disabled")
                results[feed_name] = None
                continue
            
            print(f"\n🔍 Testing: {feed_name}")
            print(f"   URL: {feed_config.url}")
            print(f"   Cloudflare protected: {_is_cloudflare_protected(str(feed_config.url))}")
            
            try:
                posts = await process_feed_posts(
                    feed_config,
                    cache_client,
                    browser_pool=None,
                    max_posts=3,
                )
                
                if posts:
                    print(f"✅ SUCCESS: Found {len(posts)} posts")
                    for post in posts[:2]:  # Show first 2
                        print(f"   - {post.title[:60]}...")
                    results[feed_name] = True
                else:
                    print(f"⚠️  No new posts found (but feed processed successfully)")
                    results[feed_name] = True
            
            except Exception as e:
                print(f"❌ FAILED: {type(e).__name__}: {str(e)[:100]}")
                results[feed_name] = False
        
        # Summary
        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        
        success = sum(1 for v in results.values() if v is True)
        failed = sum(1 for v in results.values() if v is False)
        skipped = sum(1 for v in results.values() if v is None)
        
        for feed_name, status in results.items():
            if status is True:
                print(f"✅ {feed_name}")
            elif status is False:
                print(f"❌ {feed_name}")
            else:
                print(f"⏭️  {feed_name}")
        
        print(f"\nResults: {success} passed, {failed} failed, {skipped} skipped")
        return failed == 0
    
    finally:
        await cache_client.close() if hasattr(cache_client, 'close') else None


if __name__ == '__main__':
    try:
        success = asyncio.run(test_cloudflare_feeds())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("Test failed", error=str(e))
        sys.exit(1)
