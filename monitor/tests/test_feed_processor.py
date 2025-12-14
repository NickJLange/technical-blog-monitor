
import pytest

from monitor.config import FeedConfig
from monitor.feeds.base import FeedProcessor, get_feed_processor
from monitor.models.blog_post import BlogPost


class MockFeedProcessor(FeedProcessor):
    async def fetch_feed(self, client):
        return b"mock content"

    async def parse_feed(self, content):
        return [{"title": "Test Post", "link": "http://example.com/post"}]

    async def extract_posts(self, entries):
        return [BlogPost(
            id="test-id",
            url="http://example.com/post",
            title="Test Post",
            source="Test Feed"
        )]

@pytest.mark.asyncio
async def test_get_feed_processor_rss():
    config = FeedConfig(name="Test Feed", url="http://example.com/rss")
    processor = await get_feed_processor(config)
    assert processor.__class__.__name__ == "RSSFeedProcessor"

@pytest.mark.asyncio
async def test_get_feed_processor_atom():
    config = FeedConfig(name="Test Feed", url="http://example.com/atom")
    processor = await get_feed_processor(config)
    assert processor.__class__.__name__ == "AtomFeedProcessor"

@pytest.mark.asyncio
async def test_get_feed_processor_json():
    config = FeedConfig(name="Test Feed", url="http://example.com/feed.json")
    processor = await get_feed_processor(config)
    assert processor.__class__.__name__ == "JSONFeedProcessor"

@pytest.mark.asyncio
async def test_feed_processor_fingerprint():
    config = FeedConfig(name="Test Feed", url="http://example.com/rss")
    processor = MockFeedProcessor(config)
    fingerprint = await processor.get_feed_fingerprint(b"test content")
    assert isinstance(fingerprint, str)
    assert len(fingerprint) > 0
