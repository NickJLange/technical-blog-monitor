import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from monitor.extractor.article_parser import extract_article_content
from monitor.models.article import ArticleContent

# Sample HTML for testing
SAMPLE_HTML = """
<html>
    <head><title>Test Article</title></head>
    <body>
        <article>
            <h1>Test Article Title</h1>
            <p>This is a paragraph.</p>
            <p>This is another paragraph.</p>
            <img src="image.jpg" alt="Test Image">
        </article>
    </body>
</html>
"""

@pytest.mark.asyncio
async def test_extract_article_content():
    # Mock dependencies
    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(return_value=True)
    
    from concurrent.futures import ThreadPoolExecutor
    thread_pool = ThreadPoolExecutor(max_workers=1)
    
    # Mock httpx.AsyncClient
    with patch('httpx.AsyncClient') as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()
        
        mock_client.get.return_value = mock_response
        
        # Call the function
        content = await extract_article_content(
            "http://example.com/article",
            mock_cache,
            thread_pool
        )
        
        thread_pool.shutdown()
        
        # Verify results
        assert isinstance(content, ArticleContent)
        assert content.title == "Test Article"
        assert "This is a paragraph." in content.text
        assert str(content.url) == "http://example.com/article"
