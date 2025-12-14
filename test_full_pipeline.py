#!/usr/bin/env python3
"""
Simple test script to verify the full monitor pipeline.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings
from monitor.main import app_lifecycle, process_feed

async def test_full_pipeline():
    """Test the full monitoring pipeline."""
    print("=== Testing Full Monitor Pipeline ===\n")
    
    # Load settings
    settings = load_settings()
    print(f"Loaded {len(settings.feeds)} feeds:")
    for feed in settings.feeds:
        print(f"  - {feed.name}: {feed.url}")
    print()
    
    # Run the pipeline
    async with app_lifecycle(settings) as app_context:
        print("App context initialized successfully\n")
        
        # Process each feed
        for feed in settings.feeds:
            if feed.enabled:
                print(f"Processing feed: {feed.name}")
                print("=" * 50)
                try:
                    await process_feed(app_context, feed.name)
                    print(f"✓ Successfully processed {feed.name}\n")
                except Exception as e:
                    print(f"✗ Error processing {feed.name}: {e}\n")
    
    print("=== Pipeline Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
