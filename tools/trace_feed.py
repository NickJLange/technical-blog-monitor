#!/usr/bin/env python3
"""
Script to trace a single feed execution.
"""
import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor.config import load_settings
from monitor.main import app_lifecycle, process_feed
import structlog

# Configure verbose logging for this script
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

async def trace_feed(feed_name: str):
    print(f"🚀 Tracing feed: {feed_name}")
    settings = load_settings()
    
    # Filter config to only this feed
    target_feed = settings.get_feed_by_name(feed_name)
    if not target_feed:
        print(f"❌ Feed '{feed_name}' not found!")
        return
        
    settings.feeds = [target_feed]
    
    async with app_lifecycle(settings) as app_context:
        print("✅ App context initialized")
        
        try:
            await process_feed(app_context, feed_name)
            print("✅ Feed processing completed")
            
            # Verify results in DB
            count = await app_context.vector_db_client.count()
            print(f"📊 Total records in DB: {count}")
            
            # Check for errors
            # We can't easily check feed_errors table generically without a raw SQL query method or extending client
            # But the logs should show it.
            
        except Exception as e:
            print(f"❌ Trace failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run tools/trace_feed.py 'AWS Blog'")
        sys.exit(1)
        
    asyncio.run(trace_feed(sys.argv[1]))
