#!/usr/bin/env python3
"""Test full end-to-end pipeline."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings, FeedConfig
from monitor.feeds.base import process_feed_posts
from monitor.vectordb import get_vector_db_client
from monitor.models import EmbeddingRecord
import httpx

async def main():
    settings = load_settings()
    
    # Create NoCache to bypass dedup
    class NoCache:
        async def get(self, key): return None
        async def set(self, key, value, ttl=None): return True
        async def delete(self, key): return True
        async def exists(self, key): return False
    
    # Create feed config
    feed_config = FeedConfig(
        name="Test Feed",
        url="https://www.anthropic.com/news",
        enabled=True,
    )
    
    print("Step 1: Fetch and parse posts...")
    posts = await process_feed_posts(
        feed_config,
        NoCache(),
        browser_pool=None,
        max_posts=3
    )
    
    print(f"Step 2: Got {len(posts)} posts")
    for post in posts[:2]:
        print(f"  - {post.title}")
        print(f"    Source: {post.source}")
        print(f"    Author: {post.author}")
    
    # Now manually create embedding records and store them
    print("\nStep 3: Create embedding records and store...")
    vdb = await get_vector_db_client(settings.vector_db)
    
    # Create simple embeddings for testing
    async with httpx.AsyncClient() as client:
        for i, post in enumerate(posts[:2]):
            # Create a dummy embedding (256 dims)
            embedding = [float(i) / 256 for i in range(256)]
            
            record = EmbeddingRecord(
                id=post.id,
                url=post.url,
                title=post.title,
                source=post.source,
                author=post.author,
                summary=post.summary or "No summary",
                text_embedding=embedding,
                metadata={
                    "author": post.author,
                    "tags": post.tags,
                    "source": post.source,
                }
            )
            
            print(f"\nStoring record: {post.title[:50]}...")
            try:
                await vdb.upsert(record)
                print(f"✓ Stored successfully")
            except Exception as e:
                print(f"✗ Error: {e}")
    
    # Check what's in the DB
    print(f"\nStep 4: Verify storage...")
    count = await vdb.count()
    print(f"Total records in DB: {count}")
    
    if count > 0:
        records = await vdb.list_all(limit=5)
        for rec in records[:2]:
            print(f"\n  - {rec.title}")
            print(f"    Source: {rec.source}")
            print(f"    Author: {rec.author}")

if __name__ == "__main__":
    asyncio.run(main())
