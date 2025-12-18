#!/usr/bin/env python3
"""Simple test to verify one feed processes."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings, FeedConfig
from monitor.main import app_lifecycle, process_feed

async def main():
    settings = load_settings()
    
    # Just use the first enabled feed
    feed = next((f for f in settings.feeds if f.enabled), None)
    if not feed:
        print("No enabled feeds found")
        return
    
    print(f"Testing feed: {feed.name}")
    print(f"URL: {feed.url}")
    
    async with app_lifecycle(settings) as app_context:
        try:
            await process_feed(app_context, feed.name)
            print("✓ Feed processed")
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
