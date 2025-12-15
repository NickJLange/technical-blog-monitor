"""
Base feed processing module for the technical blog monitor.

This module provides the core functionality for discovering, parsing, and processing
blog feeds from various sources. It defines the base classes and interfaces for
feed processors, as well as utility functions for feed handling.

The main entry point is the `process_feed_posts` function, which orchestrates
the entire feed processing pipeline from discovery to post extraction.
"""
import abc
import asyncio
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple, Type, Union
from urllib.parse import urljoin, urlparse

import httpx
import structlog
import bleach
from bs4 import BeautifulSoup
from pydantic import HttpUrl
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitor.config import FeedConfig
from monitor.models.blog_post import BlogPost
from monitor.models.cache_entry import CacheEntry, ValueType
# New imports for full-content capture
from concurrent.futures import ThreadPoolExecutor
from monitor.extractor.article_parser import extract_article_content
from monitor.config import ArticleProcessingConfig

# Set up structured logger
logger = structlog.get_logger()

# Constants
# Use a more realistic User-Agent that mimics a browser to avoid bot detection
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
]
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_CACHE_TTL = 3600  # 1 hour in seconds
FEED_CACHE_PREFIX = "feed:"
POST_CACHE_PREFIX = "post:"

# More realistic headers to reduce bot detection
DEFAULT_HEADERS = {
    "Accept": "application/rss+xml,application/atom+xml,application/xml;q=0.9,text/html;q=0.8,*/*;q=0.1",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class FeedProcessor(abc.ABC):
    """
    Abstract base class for feed processors.
    
    This class defines the interface that all feed processors must implement.
    Feed processors are responsible for fetching and parsing feeds from various
    sources (RSS, Atom, JSON, etc.) and extracting blog posts from them.
    """
    
    def __init__(self, config: FeedConfig):
        """
        Initialize the feed processor with a configuration.
        
        Args:
            config: Feed configuration
        """
        self.config = config
        self.name = config.name
        self.url = config.url
        # Merge default headers with config headers, then add User-Agent
        self.headers = {
            **DEFAULT_HEADERS,
            **config.headers,
            "User-Agent": DEFAULT_USER_AGENT,
        }
    
    @abc.abstractmethod
    async def fetch_feed(self, client: httpx.AsyncClient) -> bytes:
        """
        Fetch the feed content from the source.
        
        Args:
            client: HTTP client to use for the request
            
        Returns:
            bytes: Raw feed content
            
        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        pass
    
    @abc.abstractmethod
    async def parse_feed(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Parse the feed content into a list of entry dictionaries.
        
        Args:
            content: Raw feed content
            
        Returns:
            List[Dict[str, Any]]: List of feed entries as dictionaries
            
        Raises:
            ValueError: If the feed content cannot be parsed
        """
        pass
    
    @abc.abstractmethod
    async def extract_posts(self, entries: List[Dict[str, Any]]) -> List[BlogPost]:
        """
        Extract blog posts from feed entries.
        
        Args:
            entries: List of feed entries as dictionaries
            
        Returns:
            List[BlogPost]: List of blog posts
        """
        pass
    
    async def get_feed_fingerprint(self, content: bytes) -> str:
        """
        Generate a fingerprint for the feed content to detect changes.
        
        Args:
            content: Raw feed content
            
        Returns:
            str: Feed fingerprint
        """
        # Default implementation uses a stable hash of the content (not for security)
        return hashlib.sha256(content).hexdigest()
    
    def get_cache_key(self) -> str:
        """
        Get the cache key for this feed.
        
        Returns:
            str: Cache key
        """
        feed_url = str(self.url)
        return f"{FEED_CACHE_PREFIX}{hashlib.sha256(feed_url.encode()).hexdigest()}"


class CacheClient(Protocol):
    """Protocol defining the interface for cache clients."""
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache."""
        ...
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in the cache with an optional TTL."""
        ...
    
    async def delete(self, key: str) -> bool:
        """Delete a value from the cache."""
        ...
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        ...


class BrowserPool(Protocol):
    """Protocol defining the interface for browser pools."""
    
    async def render_and_screenshot(self, url: str) -> Optional[str]:
        """Render a page and take a screenshot."""
        ...


def _should_retry_429(exception: Exception) -> bool:
    """
    Check if we should retry on a 429 (Too Many Requests) error.
    """
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code == 429
    return False


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException, httpx.HTTPStatusError)),
    stop=stop_after_attempt(5),  # More attempts for rate limiting
    wait=wait_exponential(multiplier=2, min=1, max=30),  # Exponential backoff with longer max
)
async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    """
    Fetch a URL with retry logic for transient errors and rate limiting.
    
    Retries on:
    - HTTP 429 (Too Many Requests) with exponential backoff
    - Timeout errors
    - Connection errors
    
    Args:
        client: HTTP client to use for the request
        url: URL to fetch
        headers: Optional headers to include in the request
        timeout: Request timeout in seconds
        
    Returns:
        httpx.Response: HTTP response
        
    Raises:
        httpx.HTTPError: If the HTTP request fails after all retries
    """
    logger.debug("Fetching URL", url=url)
    response = await client.get(
        url,
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    )
    
    # Check for 429 rate limiting and include in retry logic
    if response.status_code == 429:
        # Try to respect Retry-After header
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            logger.warning(
                "Rate limited, respecting Retry-After header",
                url=url,
                retry_after=retry_after,
            )
        logger.debug(
            "Got 429 rate limit, will retry with backoff",
            url=url,
        )
    
    response.raise_for_status()
    return response


async def get_feed_processor(config: FeedConfig, browser_pool: Optional[BrowserPool] = None) -> FeedProcessor:
    """
    Get the appropriate feed processor for a feed configuration.
    
    This function determines the feed type based on the URL or content type
    and returns the appropriate processor instance.
    
    Args:
        config: Feed configuration
        browser_pool: Optional BrowserPool for processors that need browser rendering
        
    Returns:
        FeedProcessor: Feed processor instance
        
    Raises:
        ValueError: If the feed type cannot be determined
    """
    # Import specific processors here to avoid circular imports
    from monitor.feeds.atom import AtomFeedProcessor
    from monitor.feeds.json import JSONFeedProcessor
    from monitor.feeds.rss import RSSFeedProcessor
    from monitor.feeds.medium import MediumFeedProcessor
    
    # Check URL patterns first
    url = str(config.url).lower()
    
    # Check for Medium blogs first - they need special handling
    if 'medium.com' in url:
        logger.debug("Using Medium processor for Medium blog", feed_name=config.name)
        return MediumFeedProcessor(config, browser_pool=browser_pool)
    
    if any(pattern in url for pattern in ['/json', '/feed.json', '.json']):
        logger.debug("Using JSON processor based on URL pattern", feed_name=config.name)
        return JSONFeedProcessor(config)

    if any(pattern in url for pattern in ['/rss', '/rss.xml', '/feed', '.rss']):
        logger.debug("Using RSS processor based on URL pattern", feed_name=config.name)
        return RSSFeedProcessor(config)
    
    if any(pattern in url for pattern in ['/atom', '/atom.xml', '.atom']):
        logger.debug("Using Atom processor based on URL pattern", feed_name=config.name)
        return AtomFeedProcessor(config)
    
    # If URL pattern doesn't help, try to fetch the feed and check content
    try:
        async with httpx.AsyncClient() as client:
            # Use default headers to improve compatibility
            headers = {**DEFAULT_HEADERS, "User-Agent": DEFAULT_USER_AGENT}
            
            try:
                response = await fetch_with_retry(
                    client,
                    url,
                    headers=headers,
                    timeout=DEFAULT_TIMEOUT,
                )
            except httpx.HTTPStatusError as e:
                # If we get 406, retry with simpler Accept header
                if e.response.status_code == 406:
                    logger.info(
                        "Got 406 Not Acceptable, retrying with generic Accept header",
                        feed_name=config.name,
                    )
                    headers["Accept"] = "*/*"
                    response = await fetch_with_retry(
                        client,
                        url,
                        headers=headers,
                        timeout=DEFAULT_TIMEOUT,
                    )
                else:
                    raise
            
            content_type = response.headers.get('content-type', '').lower()
            
            if 'application/rss+xml' in content_type or 'application/xml' in content_type:
                logger.debug("Using RSS processor based on content type", feed_name=config.name)
                return RSSFeedProcessor(config)
            
            if 'application/atom+xml' in content_type:
                logger.debug("Using Atom processor based on content type", feed_name=config.name)
                return AtomFeedProcessor(config)
            
            if 'application/json' in content_type:
                logger.debug("Using JSON processor based on content type", feed_name=config.name)
                return JSONFeedProcessor(config)
            
            # If content type doesn't help, try to parse the content
            content = response.content
            
            # Check for RSS/Atom XML patterns
            if b'<rss' in content or b'<channel>' in content:
                logger.debug("Using RSS processor based on content", feed_name=config.name)
                return RSSFeedProcessor(config)
            
            if b'<feed' in content and b'xmlns="http://www.w3.org/2005/Atom"' in content:
                logger.debug("Using Atom processor based on content", feed_name=config.name)
                return AtomFeedProcessor(config)
            
            # Check if it's valid JSON
            try:
                response.json()
                logger.debug("Using JSON processor based on content", feed_name=config.name)
                return JSONFeedProcessor(config)
            except ValueError:
                pass
    
    except Exception as e:
        logger.warning(
            "Error determining feed type, defaulting to RSS",
            feed_name=config.name,
            error=str(e),
        )
    
    # Default to RSS if we can't determine the type
    logger.debug("Defaulting to RSS processor", feed_name=config.name)
    return RSSFeedProcessor(config)


async def discover_new_posts(
    processor: FeedProcessor,
    cache_client: CacheClient,
    max_posts: int = 10,
) -> List[BlogPost]:
    """
    Discover new posts from a feed that haven't been processed before.
    
    This function fetches the feed, compares it with cached data, and returns
    only new or updated posts.
    
    Args:
        processor: Feed processor to use
        cache_client: Cache client for storing and retrieving feed data
        max_posts: Maximum number of posts to return
        
    Returns:
        List[BlogPost]: List of new blog posts
    """
    logger.debug("Discovering new posts", feed_name=processor.name)
    
    # Determine if SSL verification should be disabled for this feed
    # (e.g., for sites with certificate issues)
    verify_ssl = True
    if "netflixtechblog.com" in str(processor.url).lower():
        logger.warning(
            "Disabling SSL verification for known problematic site",
            feed_name=processor.name,
        )
        verify_ssl = False
    
    # Create HTTP client with appropriate SSL settings
    async with httpx.AsyncClient(verify=verify_ssl) as client:
        try:
            # Fetch feed content
            content = await processor.fetch_feed(client)
            
            # Generate fingerprint for change detection
            fingerprint = await processor.get_feed_fingerprint(content)
            
            # Check if feed has changed
            cache_key = processor.get_cache_key()
            cached_fingerprint = await cache_client.get(f"{cache_key}:fingerprint")
            
            if cached_fingerprint == fingerprint:
                logger.debug(
                    "Feed unchanged since last check",
                    feed_name=processor.name,
                    fingerprint=fingerprint,
                )
                return []
            
            # Parse feed entries
            entries = await processor.parse_feed(content)
            
            # Extract posts from entries
            all_posts = await processor.extract_posts(entries)
            
            # Sort posts by publication date (newest first)
            all_posts.sort(
                key=lambda p: p.publish_date or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            
            # Limit number of posts to process
            posts = all_posts[:max_posts]
            
            # Filter out posts that have already been processed
            new_posts = []
            for post in posts:
                post_cache_key = f"{POST_CACHE_PREFIX}{post.id}"
                exists = await cache_client.exists(post_cache_key)
                
                if not exists:
                    new_posts.append(post)
                    # Cache post ID to avoid reprocessing
                    await cache_client.set(
                        post_cache_key,
                        "1",
                        ttl=DEFAULT_CACHE_TTL * 24 * 7,  # 1 week
                    )
            
            # Update feed fingerprint in cache
            await cache_client.set(
                f"{cache_key}:fingerprint",
                fingerprint,
                ttl=DEFAULT_CACHE_TTL,
            )
            
            # Also cache the last check time
            await cache_client.set(
                f"{cache_key}:last_check",
                datetime.now(timezone.utc).isoformat(),
                ttl=DEFAULT_CACHE_TTL * 24 * 30,  # 30 days
            )
            
            logger.info(
                "Discovered new posts",
                feed_name=processor.name,
                new_posts_count=len(new_posts),
                total_posts_count=len(all_posts),
            )
            
            return new_posts
        
        except httpx.HTTPError as e:
            # Extract status code if available (some errors like ConnectError don't have response)
            status_code = None
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
            
            logger.error(
                "HTTP error fetching feed",
                feed_name=processor.name,
                url=processor.url,
                status_code=status_code,
                error=str(e),
            )
            return []
        
        except Exception as e:
            logger.exception(
                "Error discovering new posts",
                feed_name=processor.name,
                error=str(e),
            )
            return []


async def parse_feed_entries(
    entries: List[Dict[str, Any]],
    feed_name: str,
    feed_url: str,
) -> List[BlogPost]:
    """
    Parse feed entries into BlogPost objects.
    
    This is a helper function for feed processors to convert raw feed entries
    into structured BlogPost objects.
    
    Args:
        entries: List of feed entries as dictionaries
        feed_name: Name of the feed
        feed_url: URL of the feed
        
    Returns:
        List[BlogPost]: List of blog posts
    """
    posts = []
    
    for entry in entries:
        try:
            # Extract basic fields
            title = entry.get('title', '').strip()
            url = entry.get('link') or entry.get('url')
            
            # Skip entries without title or URL
            if not title or not url:
                continue
            
            # Generate a unique ID
            entry_id = entry.get('id') or entry.get('guid') or url
            post_id = hashlib.sha256(f"{feed_name}:{entry_id}".encode()).hexdigest()
            
            # Parse dates
            publish_date = None
            updated_date = None
            
            # Try different date fields
            date_fields = [
                'published', 'pubDate', 'date', 'created', 'issued',
                'updated', 'modified', 'lastModified',
            ]
            
            for field in date_fields:
                if field in entry:
                    try:
                        # Parse date string to datetime
                        date_str = entry[field]
                        if isinstance(date_str, (int, float)):
                            # Unix timestamp
                            dt = datetime.fromtimestamp(date_str, tz=timezone.utc)
                        else:
                            # Various date formats
                            from dateutil import parser
                            dt = parser.parse(date_str)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                        
                        if field in ['updated', 'modified', 'lastModified']:
                            updated_date = dt
                        else:
                            publish_date = dt
                    except Exception:
                        continue
            
            # Extract author
            author = entry.get('author') or entry.get('creator') or entry.get('dc:creator')
            if isinstance(author, dict):
                author = author.get('name')
            
            # Extract summary/description
            summary = entry.get('summary') or entry.get('description') or entry.get('content')
            if isinstance(summary, dict):
                summary = summary.get('value') or summary.get('text')
            
            # Clean up HTML in summary
            if summary and '<' in summary:
                try:
                    # Use bleach to sanitize and strip tags
                    summary = bleach.clean(summary, tags=[], strip=True)
                except Exception:
                    # Fallback if bleach fails (unlikely)
                    summary = re.sub(r'<[^>]+>', '', summary)
            
            # Limit summary length
            if summary and len(summary) > 500:
                summary = summary[:497] + '...'
            
            # Extract tags/categories
            tags = []
            categories = entry.get('categories') or entry.get('tags') or []
            if isinstance(categories, list):
                for category in categories:
                    if isinstance(category, dict):
                        tag = category.get('term') or category.get('label')
                    else:
                        tag = category
                    if tag and isinstance(tag, str):
                        tags.append(tag.strip())
            
            # Create BlogPost object
            post = BlogPost(
                id=post_id,
                url=url,
                title=title,
                source=feed_name,
                author=author,
                publish_date=publish_date,
                updated_date=updated_date,
                summary=summary,
                tags=tags,
                metadata={
                    'feed_url': feed_url,
                    'original_id': entry_id,
                }
            )
            
            posts.append(post)
        
        except Exception as e:
            logger.warning(
                "Error parsing feed entry",
                feed_name=feed_name,
                error=str(e),
                entry=entry,
            )
    
    return posts


async def process_feed_posts(
    feed_config: FeedConfig,
    cache_client: CacheClient,
    browser_pool: Optional[BrowserPool] = None,
    max_posts: int = 10,
) -> List[BlogPost]:
    """
    Process a feed to discover and extract new posts.
    
    This is the main entry point for feed processing. It handles the entire
    pipeline from feed discovery to post extraction.
    
    Args:
        feed_config: Feed configuration
        cache_client: Cache client for storing and retrieving feed data
        browser_pool: Optional browser pool for rendering pages
        max_posts: Maximum number of posts to return
        
    Returns:
        List[BlogPost]: List of new blog posts
    """
    logger.info("Processing feed", feed_name=feed_config.name, url=feed_config.url)
    
    try:
        # Get the appropriate feed processor (pass browser pool for Medium blogs)
        processor = await get_feed_processor(feed_config, browser_pool=browser_pool)
        
        # Discover new posts
        new_posts = await discover_new_posts(
            processor,
            cache_client,
            max_posts=max_posts,
        )
        
        if not new_posts:
            logger.info("No new posts found", feed_name=feed_config.name)
            return []
        
        logger.info(
            "Found new posts",
            feed_name=feed_config.name,
            count=len(new_posts),
        )
        
        # If browser pool is available, we could pre-render the pages here
        # to check if they're valid before further processing
        if browser_pool and new_posts:
            valid_posts = []
            for post in new_posts:
                try:
                    # Try to render the page to validate the URL
                    # This is optional and can be skipped if performance is a concern
                    logger.debug(
                        "Validating post URL with browser",
                        feed_name=feed_config.name,
                        post_url=post.url,
                    )
                    
                    # Just check if the page renders, don't need the screenshot yet
                    await browser_pool.render_and_screenshot(str(post.url))
                    valid_posts.append(post)
                
                except Exception as e:
                    logger.warning(
                        "Failed to validate post URL",
                        feed_name=feed_config.name,
                        post_url=post.url,
                        error=str(e),
                    )
            
            return valid_posts
        
        return new_posts
    
    except Exception as e:
        logger.exception(
            "Error processing feed",
            feed_name=feed_config.name,
            error=str(e),
        )
        return []

# --------------------------------------------------------------------------- #
# New helper for full-article capture
# --------------------------------------------------------------------------- #

async def process_individual_article(
    post: BlogPost,
    cache_client: CacheClient,
    browser_pool: BrowserPool,
) -> BlogPost:
    """
    Render the individual article page, capture screenshots, and extract the
    full cleaned article content.  The resulting information is attached to
    the BlogPost.metadata for downstream processing (embedding, storage…).
    """
    logger.debug("Processing individual article", url=post.url)

    screenshot_path: Optional[str] = None
    try:
        # 1. Render & screenshot
        screenshot_path = await browser_pool.render_and_screenshot(str(post.url))

        # 2. Extract clean content (cpu-bound → thread pool)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="extractor") as pool:
            article_content = await extract_article_content(
                str(post.url),
                cache_client,
                pool,
            )

        # 3. Attach to post metadata
        post.metadata["article_text"] = article_content.text
        post.metadata["article_word_count"] = article_content.word_count
        post.metadata["article_summary"] = article_content.summary
        post.metadata["article_screenshot"] = screenshot_path
        post.metadata["article_processed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info("Full article captured", url=post.url, words=article_content.word_count)
        return post

    except Exception as exc:
        logger.warning(
            "Failed to capture full article",
            url=post.url,
            error=str(exc),
        )
        return post
