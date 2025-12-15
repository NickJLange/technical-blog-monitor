#!/usr/bin/env python3
"""
Script to reset the vector database.
"""
import asyncio
import sys
from pathlib import Path
import asyncpg

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor.config import load_settings
from monitor.vectordb import get_vector_db_client
from monitor.cache import get_cache_client

async def reset_db():
    settings = load_settings()
    print(f"DEBUG: VECTOR_DB__TEXT_VECTOR_DIMENSION from settings: {settings.vector_db.text_vector_dimension}")
    print(f"Connecting to components...")
    
    try:
        # DROP TABLE explicitly to handle dimension changes
        print(f"Dropping table blog_posts_{settings.vector_db.collection_name} to ensure schema update...")
        try:
            conn = await asyncpg.connect(settings.vector_db.connection_string)
            await conn.execute(f"DROP TABLE IF EXISTS blog_posts_{settings.vector_db.collection_name}")
            await conn.close()
            print("✅ Table dropped.")
        except Exception as e:
            print(f"⚠️ Failed to drop table directly: {e}")

        # Clear Vector DB (Initialize will recreate table)
        vdb_client = await get_vector_db_client(settings.vector_db)
        print(f"Initializing Vector DB collection '{settings.vector_db.collection_name}'...")
        # initialize() is called in factory
        await vdb_client.close() # We just wanted to init/recreate table
        print("✅ Vector DB re-initialized.")

        # Clear Cache
        cache_client = await get_cache_client(settings.cache, settings.vector_db)
        print("Clearing Cache...")
        await cache_client.clear()
        await cache_client.close()
        print("✅ Cache cleared.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(reset_db())