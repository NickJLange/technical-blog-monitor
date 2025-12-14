
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from monitor.models.embedding import EmbeddingRecord
from monitor.vectordb import InMemoryVectorDBClient
from monitor.config import VectorDBConfig, LLMConfig, LLMProvider
from monitor.llm import get_generation_client, OllamaGenerationClient

async def test_retention_logic():
    print("\n=== Testing Knowledge Retention Logic ===")
    
    # Setup Vector DB
    config = VectorDBConfig(db_type="qdrant", connection_string="http://mem", collection_name="test")
    client = InMemoryVectorDBClient(config)
    await client.initialize()
    
    # Create a record
    record = EmbeddingRecord(
        id="test-1",
        url="http://example.com/1",
        title="Test Post",
        text_embedding=[0.1]*1536,
        metadata={"source": "test"}
    )
    await client.upsert(record)
    
    # 1. Mark as read
    print("Marking post as read...")
    now = datetime.now(timezone.utc)
    next_review = now - timedelta(minutes=1) # Due immediately for testing
    
    record.metadata.update({
        "read_status": "read",
        "read_at": now.isoformat(),
        "next_review_at": next_review.isoformat(),
        "review_stage": 1
    })
    await client.upsert(record)
    
    # 2. Check review queue
    print("Checking review queue...")
    reviews = await client.get_due_reviews()
    assert len(reviews) == 1
    assert reviews[0].id == "test-1"
    print("✓ Review item found")
    
    # 3. Test future review
    record.metadata["next_review_at"] = (now + timedelta(days=30)).isoformat()
    await client.upsert(record)
    reviews = await client.get_due_reviews()
    assert len(reviews) == 0
    print("✓ Future review item hidden")

async def test_generation_client():
    print("\n=== Testing Generation Client Factory ===")
    
    # Test OpenAI config
    config = LLMConfig(provider=LLMProvider.OPENAI, api_key="sk-test") # Mock key
    try:
        client = get_generation_client(config)
        print("✓ OpenAI client created")
    except ImportError:
        print("⚠ OpenAI package not installed (expected in some envs)")
        
    # Test Ollama config
    config = LLMConfig(provider=LLMProvider.OLLAMA)
    client = get_generation_client(config)
    assert isinstance(client, OllamaGenerationClient)
    print("✓ Ollama client created")

if __name__ == "__main__":
    asyncio.run(test_retention_logic())
    asyncio.run(test_generation_client())
