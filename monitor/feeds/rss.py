"""
RSS feed processor for the technical blog monitor.

This module provides functionality for fetching and parsing RSS feeds,
extracting blog posts, and handling various RSS formats and edge cases.
It implements the FeedProcessor interface for RSS feeds.
"""
from typing import Any, Dict, List

import httpx
import structlog
from bs4 import BeautifulSoup

from monitor.config import FeedConfig
from monitor.feeds.base import FeedProcessor, parse_feed_entries
from monitor.feeds.utils import (
    find_alternate_feed_link,
    generate_feed_fingerprint,
    parse_feed_content,
)
from monitor.models.blog_post import BlogPost

# Set up structured logger
logger = structlog.get_logger()


class RSSFeedProcessor(FeedProcessor):
    """
    RSS feed processor implementation.
    
    This processor handles fetching and parsing RSS feeds, extracting blog posts,
    and handling various RSS formats and edge cases.
    """

    def __init__(self, config: FeedConfig):
        """
        Initialize the RSS feed processor.
        
        Args:
            config: Feed configuration
        """
        super().__init__(config)

    async def fetch_feed(self, client: httpx.AsyncClient) -> bytes:
        """
        Fetch the RSS feed content from the source.
        
        Args:
            client: HTTP client to use for the request
            
        Returns:
            bytes: Raw feed content
            
        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        logger.debug("Fetching RSS feed", url=self.url)

        # Make the request
        response = await client.get(
            str(self.url),
            headers=self.headers,
            follow_redirects=True,
        )
        response.raise_for_status()

        # Get the content
        content = response.content

        # Check if the content is valid XML
        if not content.strip().startswith(b'<?xml') and not content.strip().startswith(b'<rss'):
            # Try to find RSS feed URL in HTML
            rss_url = find_alternate_feed_link(content, str(self.url), "rss")

            if rss_url:
                logger.info(
                    "Found RSS feed link in HTML, fetching actual feed",
                    original_url=self.url,
                    rss_url=rss_url,
                )

                # Fetch the actual RSS feed
                response = await client.get(
                    rss_url,
                    headers=self.headers,
                    follow_redirects=True,
                )
                response.raise_for_status()
                content = response.content

        logger.debug(
            "RSS feed fetched successfully",
            url=self.url,
            content_length=len(content),
        )

        return content

    async def parse_feed(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Parse the RSS feed content into a list of entry dictionaries.
        
        Args:
            content: Raw feed content
            
        Returns:
            List[Dict[str, Any]]: List of feed entries as dictionaries
            
        Raises:
            ValueError: If the feed content cannot be parsed
        """
        logger.debug("Parsing RSS feed content")

        # Parse the feed using common utility
        feed = await parse_feed_content(content)

        # Check for parsing errors
        if hasattr(feed, 'bozo') and feed.bozo and hasattr(feed, 'bozo_exception'):
            # Log the error but continue with what we could parse
            logger.warning(
                "RSS feed parsing error",
                url=self.url,
                error=str(feed.bozo_exception),
            )

        # Extract entries
        entries = feed.entries if hasattr(feed, 'entries') else []

        logger.debug(
            "RSS feed parsed successfully",
            url=self.url,
            entry_count=len(entries),
        )

        # Convert feedparser entries to dictionaries
        result = []
        for entry in entries:
            # Convert entry to a regular dictionary
            entry_dict = {}
            for key, value in entry.items():
                entry_dict[key] = value
            result.append(entry_dict)

        return result

    async def extract_posts(self, entries: List[Dict[str, Any]]) -> List[BlogPost]:
        """
        Extract blog posts from feed entries.
        
        Args:
            entries: List of feed entries as dictionaries
            
        Returns:
            List[BlogPost]: List of blog posts
        """
        logger.debug(
            "Extracting blog posts from RSS feed entries",
            url=self.url,
            entry_count=len(entries),
        )

        # Use the common parser from base.py
        posts = await parse_feed_entries(
            entries,
            self.name,
            str(self.url),
        )

        # Post-process to handle RSS-specific fields
        for i, post in enumerate(posts):
            # Try to extract categories/tags from the original entry
            if i < len(entries):
                entry = entries[i]
                tags = []

                # Extract categories
                if 'categories' in entry:
                    for category in entry['categories']:
                        if category and isinstance(category, str):
                            tags.append(category.strip())

                # Extract tags from content
                if 'content' in entry and entry['content']:
                    for content_item in entry['content']:
                        if 'value' in content_item:
                            # Try to extract tags from HTML content
                            try:
                                soup = BeautifulSoup(content_item['value'], 'html.parser')
                                meta_tags = soup.find_all('meta', property='article:tag')
                                for tag in meta_tags:
                                    if 'content' in tag.attrs:
                                        tags.append(tag['content'].strip())
                            except Exception:
                                pass

                # Update post tags
                if tags:
                    post.tags = list(set(post.tags + tags))

                # Extract full content if available
                if 'content' in entry and entry['content']:
                    for content_item in entry['content']:
                        if 'value' in content_item:
                            post.metadata['full_content'] = content_item['value']
                            break

        logger.debug(
            "Extracted blog posts from RSS feed",
            url=self.url,
            post_count=len(posts),
        )

        return posts

    async def get_feed_fingerprint(self, content: bytes) -> str:
        """
        Generate a fingerprint for the feed content to detect changes.
        
        Args:
            content: Raw feed content
            
        Returns:
            str: Feed fingerprint
        """
        try:
            return await generate_feed_fingerprint(content)
        except Exception as e:
            logger.warning(
                "Error generating RSS feed fingerprint, falling back to default",
                url=self.url,
                error=str(e),
            )
            # Fall back to base implementation
            return await super().get_feed_fingerprint(content)
