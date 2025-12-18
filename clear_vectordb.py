#!/usr/bin/env python3
"""Clear all records from vector database."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings
from monitor.vectordb import get_vector_db_client

async def main():
    settings = load_settings()
    vdb = await get_vector_db_client(settings.vector_db)
    
    # Count before
    count_before = await vdb.count()
    print(f'Records before: {count_before}')
    
    if count_before > 0:
        # Delete via bulk delete - iterate and delete
        records = await vdb.list_all(limit=1000)
        for record in records:
            await vdb.delete(record.id)
        print(f'Deleted {len(records)} records')
    
    # Count after
    count_after = await vdb.count()
    print(f'Records after: {count_after}')

if __name__ == "__main__":
    asyncio.run(main())
