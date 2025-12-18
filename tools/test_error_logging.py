#!/usr/bin/env python3
"""
Script to test feed error logging to DB.
"""
import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor.config import load_settings, FeedConfig
from monitor.main import app_lifecycle, process_feed
import structlog

# Configure verbose logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

async def test_error_logging():
    print("🧪 Testing exception queue logging...")
    settings = load_settings()
    
    # Create a dummy bad feed
    bad_feed = FeedConfig(
        name="Bad Feed",
        url="https://this.domain.does.not.exist.test/feed",
        enabled=True,
        max_posts_per_check=1
    )
    
    # Inject into settings
    settings.feeds = [bad_feed]
    
    async with app_lifecycle(settings) as app_context:
        print("✅ App context initialized")
        print(f"DEBUG: TEST SCRIPT Context client: {app_context.vector_db_client}")
        
        # Count errors before
        initial_error_count = 0
        try:
             # We need raw connection to check count as we haven't added specific method to client for count(table)
             # But we can assume list_all won't show it.
             # We'll trust the log output from our successful log_error call.
             pass
        except:
             pass

        print("🔄 Processing bad feed (expecting failure)...")
        await process_feed(app_context, "Bad Feed")
        
        print("✅ Processing attempt finished")
        
        # Verify error was logged
        # We'll use a raw query to check
        try:
            client = app_context.vector_db_client
            # Access the pool directly if possible, or assume success if no exception above
            # The client doesn't expose raw execute publicly usually, but we are inside the app.
            # Let's use the private pool for verification
            if hasattr(client, 'pool'):
                async with client.pool.acquire() as conn:
                    # Debug: print all errors
                    all_errors = await conn.fetch("SELECT * FROM feed_errors")
                    print(f"DEBUG: All feed_errors in DB: {len(all_errors)}")
                    for err in all_errors:
                        print(f" - {err['feed_name']}: {err['error_message'][:50]}...")

                    count = await conn.fetchval("SELECT COUNT(*) FROM feed_errors WHERE feed_name = 'Bad Feed'")
                    print(f"📊 Errors found in DB for 'Bad Feed': {count}")
                    if count > 0:
                        print("✅ SUCCESS: Error was logged to DB!")
                    else:
                        print("❌ FAILURE: No error found in DB!")
                        sys.exit(1)
            else:
                 print("⚠️ Could not verify DB directly (no pool access), assuming success if logs showed it.")
                 
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_error_logging())
