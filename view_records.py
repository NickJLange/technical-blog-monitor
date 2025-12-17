#!/usr/bin/env python3
"""
View cached blog post records with full details.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings
from monitor.vectordb import get_vector_db_client

async def main():
    settings = load_settings()
    vector_db = await get_vector_db_client(settings.vector_db)
    
    # Get recent records
    records = await vector_db.list_all(limit=10)
    
    if not records:
        print("No records found in vector database")
        return
    
    print(f"\n{'='*120}")
    print(f"Latest {len(records)} Records from Vector DB")
    print(f"{'='*120}\n")
    
    for i, record in enumerate(records, 1):
        print(f"\n[{i}] {record.title}")
        print(f"    {'─' * 116}")
        print(f"    URL:          {record.url}")
        print(f"    Source:       {record.source or '(none)'}")
        print(f"    Author:       {record.author or '(none)'}")
        print(f"    Published:    {record.publish_date.strftime('%Y-%m-%d %H:%M:%S') if record.publish_date else '(unknown)'}")
        print(f"    Summary:      {(record.summary[:100] + '...') if record.summary else '(none)'}")
        
        # Check for AI summary in metadata
        ai_summary = record.metadata.get('ai_summary') if record.metadata else None
        if ai_summary:
            print(f"    AI Summary:   {(ai_summary[:100] + '...') if len(ai_summary) > 100 else ai_summary}")
        else:
            print(f"    AI Summary:   ❌ Missing")
        
        print()

if __name__ == "__main__":
    asyncio.run(main())
