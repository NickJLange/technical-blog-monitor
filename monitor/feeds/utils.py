"""
Utility functions for feed processing.
"""
import asyncio
import hashlib
import re
from typing import Any, Optional
from urllib.parse import urljoin

import feedparser
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger()

def clean_html(html_content: str) -> str:
    """
    Clean HTML content by removing tags and normalizing whitespace.
    
    Args:
        html_content: HTML content to clean
        
    Returns:
        str: Cleaned text
    """
    if not html_content:
        return ""

    try:
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract text
        text = soup.get_text(separator=' ', strip=True)

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    except Exception:
        # Fall back to simple regex-based cleaning
        text = re.sub(r'<[^>]+>', '', html_content)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

def find_alternate_feed_link(
    html_content: bytes,
    base_url: str,
    feed_type: str = "rss"
) -> Optional[str]:
    """
    Find an alternate feed link in HTML content.
    
    Args:
        html_content: Raw HTML content
        base_url: Base URL for resolving relative URLs
        feed_type: Type of feed to look for ("rss" or "atom")
        
    Returns:
        Optional[str]: URL of the feed if found, None otherwise
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        link_type = 'application/rss+xml' if feed_type.lower() == 'rss' else 'application/atom+xml'
        link = soup.find('link', rel='alternate', type=link_type)

        if link and link.get('href'):
            feed_url = link['href']
            # Handle relative URLs
            if not feed_url.startswith(('http://', 'https://')):
                feed_url = urljoin(base_url, feed_url)
            return feed_url

    except Exception as e:
        logger.warning(
            "Error searching for alternate feed link",
            base_url=base_url,
            feed_type=feed_type,
            error=str(e),
        )

    return None

async def parse_feed_content(content: bytes) -> Any:
    """
    Parse feed content using feedparser in a thread pool.
    
    Args:
        content: Raw feed content
        
    Returns:
        Any: Parsed feed object
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: feedparser.parse(content)
    )

async def generate_feed_fingerprint(
    content: bytes,
    feed_obj: Optional[Any] = None
) -> str:
    """
    Generate a fingerprint for feed content.
    
    Args:
        content: Raw feed content
        feed_obj: Optional already-parsed feed object. If None, content will be parsed.
        
    Returns:
        str: Fingerprint string
    """
    try:
        if feed_obj is None:
            feed_obj = await parse_feed_content(content)

        entries = feed_obj.entries if hasattr(feed_obj, 'entries') else []

        if entries:
            # Use the most recent entry's ID or link as the fingerprint
            most_recent = entries[0]

            if hasattr(most_recent, 'id'):
                return f"id:{most_recent.id}"
            elif hasattr(most_recent, 'link'):
                return f"link:{most_recent.link}"
            elif hasattr(most_recent, 'title'):
                return f"title:{most_recent.title}"

        # Fall back to feed-level info
        if hasattr(feed_obj, 'feed'):
            if hasattr(feed_obj.feed, 'updated'):
                return f"updated:{feed_obj.feed.updated}"
            elif hasattr(feed_obj.feed, 'id'):
                return f"feed_id:{feed_obj.feed.id}"

    except Exception:
        pass

    # Fallback to content hash
    return hashlib.sha256(content).hexdigest()
