#!/usr/bin/env python3
"""
Script to check the vector database content.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor.config import load_settings
from monitor.vectordb import get_vector_db_client

async def check_db():
    settings = load_settings()
    print(f"Connecting to {settings.vector_db.db_type}...")
    
    try:
        client = await get_vector_db_client(settings.vector_db)
        count = await client.count()
        print(f"Total records: {count}")
        
        if count > 0:
            records = await client.list_all(limit=5)
            print("\nLatest 5 records:")
            for r in records:
                summary_status = "✅ Present" if r.metadata.get("ai_summary") else "❌ Missing"
                print(f"- [{r.id[:8]}] {r.title}")
                print(f"  AI Summary: {summary_status}")
                if r.metadata.get("ai_summary"):
                    print(f"  Preview: {r.metadata['ai_summary'][:100]}...")
        
        await client.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(check_db())
