#!/usr/bin/env python3
"""Clear all feed-related cache entries."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings
from monitor.cache import get_cache_client

async def main():
    settings = load_settings()
    cache = await get_cache_client(settings.cache)
    
    print(f"Cache backend: {type(cache).__name__}")
    
    # We need to identify what cache keys exist. For PostgreSQL cache,
    # we'd need to query the database directly.
    # For now, let's just clear patterns that we know about:
    
    from monitor.feeds.base import POST_CACHE_PREFIX
    
    print(f"Post cache prefix: {POST_CACHE_PREFIX}")
    
    # This would require iterating through all keys, which isn't efficient for DB cache
    # Instead, let's use raw SQL to clear the cache table
    
    if hasattr(cache, 'dsn'):
        print(f"Using PostgreSQL cache: {cache.dsn}")
        # For PostgreSQL, we can directly delete from the cache table
        import asyncpg
        
        dsn = cache.dsn
        pool = await asyncpg.create_pool(dsn)
        
        try:
            async with pool.acquire() as conn:
                # Clear the cache_entries table
                result = await conn.execute('DELETE FROM cache_entries')
                print(f"Cleared cache_entries table")
                
                # Count remaining entries
                count = await conn.fetchval('SELECT COUNT(*) FROM cache_entries')
                print(f"Remaining cache entries: {count}")
        finally:
            await pool.close()
    else:
        print("Cannot clear database cache without connection details")

if __name__ == "__main__":
    asyncio.run(main())
