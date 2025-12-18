#!/usr/bin/env python3
"""
Script to check database connectivity.
"""
import sys
import asyncio
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor.config import load_settings
from monitor.vectordb import get_vector_db_client

async def check_connection():
    try:
        print("Loading settings...")
        settings = load_settings()
        
        print(f"Checking connection to {settings.vector_db.db_type} at {settings.vector_db.connection_string}...")
        
        # This will attempt to connect
        client = await get_vector_db_client(settings.vector_db)
        
        print("✅ Client initialized successfully.")
        
        # Try a simple operation
        try:
            count = await client.count()
            print(f"✅ Connection verified! Total records in DB: {count}")
            return 0
        except Exception as e:
            print(f"❌ Connection successful but failed to count records: {e}")
            return 1
            
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(check_connection()))
