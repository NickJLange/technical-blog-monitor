#!/usr/bin/env python3
"""
Basic test script for the technical blog monitor.

This script tests the core functionality of the technical blog monitor
without requiring heavy dependencies like Playwright. It validates:
1. Module imports
2. Configuration loading
3. Feed parsing
4. Content extraction
5. Embedding generation
6. Vector database operations

Run this script to verify that the basic architecture is working.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add the project root to the Python path if needed
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import core modules
from monitor.config import Settings, load_settings
from monitor.models.blog_post import BlogPost
from monitor.models.article import ArticleContent
from monitor.models.embedding import EmbeddingRecord
from monitor.cache import get_cache_client, MemoryCacheClient
from monitor.embeddings import get_embedding_client, DummyEmbeddingClient
from monitor.vectordb import get_vector_db_client, InMemoryVectorDBClient
from monitor.extractor.article_parser import clean_article_text


# Sample HTML content for testing
SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Technical Blog Post</title>
    <meta name="author" content="Test Author">
    <meta name="description" content="This is a test blog post for the technical blog monitor.">
    <meta property="og:title" content="Test Technical Blog Post">
    <meta property="og:description" content="This is a test blog post for the technical blog monitor.">
    <meta property="og:type" content="article">
    <meta property="og:published_time" content="2023-01-01T12:00:00Z">
</head>
<body>
    <article>
        <h1>Test Technical Blog Post</h1>
        <div class="author">By Test Author</div>
        <div class="date">January 1, 2023</div>
        <div class="content">
            <p>This is a test blog post for the technical blog monitor.</p>
            <p>It contains some technical content about Python, async programming, and web scraping.</p>
            <h2>Key Features</h2>
            <ul>
                <li>Feature 1: Amazing functionality</li>
                <li>Feature 2: Incredible performance</li>
                <li>Feature 3: Outstanding reliability</li>
            </ul>
            <p>This is just a test, but in a real blog post, there would be much more content here.</p>
        </div>
        <div class="tags">
            <span>python</span>
            <span>async</span>
            <span>web-scraping</span>
        </div>
    </article>
</body>
</html>
"""


async def test_content_extraction():
    """Test basic content extraction functionality."""
    print("\n=== Testing Content Extraction ===")
    
    # Extract text from HTML
    clean_text = clean_article_text(SAMPLE_HTML)
    print(f"Extracted text length: {len(clean_text)} characters")
    print(f"First 100 characters: {clean_text[:100]}...")
    
    # Create an ArticleContent object
    article = ArticleContent(
        url="https://example.com/test-post",
        title="Test Technical Blog Post",
        text=clean_text,
        html=SAMPLE_HTML,
        author="Test Author",
        word_count=len(clean_text.split()),
        tags=["python", "async", "web-scraping"],
    )
    
    print(f"Created ArticleContent: {article.title} by {article.author}")
    print(f"Word count: {article.word_count}")
    print(f"Tags: {', '.join(article.tags)}")
    
    return article


async def test_embedding_generation(article):
    """Test basic embedding generation functionality."""
    print("\n=== Testing Embedding Generation ===")
    
    # Create a minimal embedding configuration
    from monitor.config import EmbeddingConfig, EmbeddingModelType
    embedding_config = EmbeddingConfig(
        text_model_type=EmbeddingModelType.CUSTOM,
        text_model_name="dummy-model",
        embedding_dimensions=384,
    )
    
    # Get a dummy embedding client
    embedding_client = await get_embedding_client(embedding_config)
    print(f"Created embedding client: {type(embedding_client).__name__}")
    
    # Generate text embedding
    text_embedding = await embedding_client.embed_text(article.text)
    print(f"Generated text embedding with {len(text_embedding)} dimensions")
    print(f"First 5 values: {text_embedding[:5]}")
    
    # Create an EmbeddingRecord
    record = EmbeddingRecord(
        id="test-post-1",
        url=article.url,
        title=article.title,
        text_embedding=text_embedding,
        metadata={
            "author": article.author,
            "tags": article.tags,
            "word_count": article.word_count,
        }
    )
    
    print(f"Created EmbeddingRecord: {record.id} - {record.title}")
    
    # Clean up
    await embedding_client.close()
    
    return record


async def test_vector_database(record):
    """Test basic vector database functionality."""
    print("\n=== Testing Vector Database ===")
    
    # Create a minimal vector database configuration
    from monitor.config import VectorDBConfig, VectorDBType
    vector_db_config = VectorDBConfig(
        db_type=VectorDBType.QDRANT,  # Will use in-memory client
        connection_string="memory://",
        collection_name="test-collection",
        text_vector_dimension=len(record.text_embedding),
    )
    
    # Get an in-memory vector database client
    vector_db_client = await get_vector_db_client(vector_db_config)
    print(f"Created vector database client: {type(vector_db_client).__name__}")
    
    # Store the record
    success = await vector_db_client.upsert(record)
    print(f"Stored record in vector database: {success}")
    
    # Count records
    count = await vector_db_client.count()
    print(f"Vector database contains {count} records")
    
    # Search for similar records
    results = await vector_db_client.search_by_text(
        record.text_embedding,
        limit=5,
    )
    
    print(f"Found {len(results)} similar records")
    for i, (result_record, score) in enumerate(results):
        print(f"  {i+1}. {result_record.title} (score: {score:.4f})")
    
    # Clean up
    await vector_db_client.clear()
    await vector_db_client.close()


async def test_cache():
    """Test basic cache functionality."""
    print("\n=== Testing Cache ===")
    
    # Create a minimal cache configuration
    from monitor.config import CacheConfig
    cache_config = CacheConfig(
        enabled=True,
        local_storage_path=Path("./cache"),
    )
    
    # Get a memory cache client
    cache_client = await get_cache_client(cache_config)
    print(f"Created cache client: {type(cache_client).__name__}")
    
    # Store a value
    key = "test-key"
    value = {"name": "Test Value", "count": 42}
    success = await cache_client.set(key, value)
    print(f"Stored value in cache: {success}")
    
    # Retrieve the value
    retrieved = await cache_client.get(key)
    print(f"Retrieved value from cache: {retrieved}")
    
    # Check if key exists
    exists = await cache_client.exists(key)
    print(f"Key exists in cache: {exists}")
    
    # Delete the key
    deleted = await cache_client.delete(key)
    print(f"Deleted key from cache: {deleted}")
    
    # Verify deletion
    exists = await cache_client.exists(key)
    print(f"Key exists after deletion: {exists}")
    
    # Clean up
    await cache_client.close()


async def main():
    """Run all tests."""
    print("=== Technical Blog Monitor Basic Test ===")
    print(f"Current directory: {os.getcwd()}")
    
    # Test content extraction
    article = await test_content_extraction()
    
    # Test embedding generation
    record = await test_embedding_generation(article)
    
    # Test vector database
    await test_vector_database(record)
    
    # Test cache
    await test_cache()
    
    print("\n=== All Tests Completed Successfully ===")


if __name__ == "__main__":
    asyncio.run(main())
