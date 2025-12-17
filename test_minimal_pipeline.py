#!/usr/bin/env python3
"""Minimal pipeline test to trace where records get lost."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings
from monitor.vectordb import get_vector_db_client
from monitor.embeddings import get_embedding_client
from monitor.models import EmbeddingRecord
from datetime import datetime, timezone

async def main():
    settings = load_settings()
    
    # Initialize clients
    vdb = await get_vector_db_client(settings.vector_db)
    embed_client = await get_embedding_client(settings.embedding)
    
    print(f"Vector DB type: {type(vdb).__name__}")
    print(f"Embedding client type: {type(embed_client).__name__}")
    
    # Create a test record with proper embedding dimensions
    text = "This is a test article about Python and machine learning frameworks."
    embedding = await embed_client.embed_text(text)
    
    print(f"Embedding dimension: {len(embedding)}")
    
    record = EmbeddingRecord(
        id="test-001",
        url="https://example.com/test",
        title="Test Article",
        publish_date=datetime.now(timezone.utc),
        text_embedding=embedding,
        summary="Test summary",
        author="Test Author",
        source="Test Source",
    )
    
    print(f"\nCreated record: {record.title}")
    print(f"Record ID: {record.id}")
    
    # Try to upsert
    try:
        print("\nAttempting upsert...")
        await vdb.upsert(record)
        print("✓ Upsert successful")
    except Exception as e:
        print(f"✗ Upsert failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Check count
    try:
        count = await vdb.count()
        print(f"\nTotal records in DB: {count}")
    except Exception as e:
        print(f"Error counting: {e}")

if __name__ == "__main__":
    asyncio.run(main())
