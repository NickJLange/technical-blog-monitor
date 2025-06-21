"""
Atom feed processor for the technical blog monitor.

This module provides functionality for fetching and parsing Atom feeds,
extracting blog posts, and handling various Atom formats and edge cases.
It implements the FeedProcessor interface for Atom feeds.
"""
import asyncio
import datetime
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
import structlog
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitor.config import FeedConfig
from monitor.feeds.base import FeedProcessor, parse_feed_entries
from monitor.models.blog_post import BlogPost

# Set up structured logger
logger = structlog.get_logger()


class AtomFeedProcessor(FeedProcessor):
    """
    Atom feed processor implementation.
    
    This processor handles fetching and parsing Atom feeds, extracting blog posts,
    and handling various Atom formats and edge cases.
    """
    
    def __init__(self, config: FeedConfig):
        """
        Initialize the Atom feed processor.
        
        Args:
            config: Feed configuration
        """
        super().__init__(config)
    
    async def fetch_feed(self, client: httpx.AsyncClient) -> bytes:
        """
        Fetch the Atom feed content from the source.
        
        Args:
            client: HTTP client to use for the request
            
        Returns:
            bytes: Raw feed content
            
        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        logger.debug("Fetching Atom feed", url=self.url)
        
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
        if not content.strip().startswith(b'<?xml') and not content.strip().startswith(b'<feed'):
            # Try to find Atom feed URL in HTML
            try:
                soup = BeautifulSoup(content, 'html.parser')
                atom_link = soup.find('link', rel='alternate', type='application/atom+xml')
                
                if atom_link and atom_link.get('href'):
                    atom_url = atom_link['href']
                    # Handle relative URLs
                    if not atom_url.startswith(('http://', 'https://')):
                        base_url = str(self.url)
                        atom_url = urljoin(base_url, atom_url)
                    
                    logger.info(
                        "Found Atom feed link in HTML, fetching actual feed",
                        original_url=self.url,
                        atom_url=atom_url,
                    )
                    
                    # Fetch the actual Atom feed
                    response = await client.get(
                        atom_url,
                        headers=self.headers,
                        follow_redirects=True,
                    )
                    response.raise_for_status()
                    content = response.content
            except Exception as e:
                logger.warning(
                    "Error trying to find Atom feed URL in HTML",
                    url=self.url,
                    error=str(e),
                )
        
        logger.debug(
            "Atom feed fetched successfully",
            url=self.url,
            content_length=len(content),
        )
        
        return content
    
    async def parse_feed(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Parse the Atom feed content into a list of entry dictionaries.
        
        Args:
            content: Raw feed content
            
        Returns:
            List[Dict[str, Any]]: List of feed entries as dictionaries
            
        Raises:
            ValueError: If the feed content cannot be parsed
        """
        logger.debug("Parsing Atom feed content")
        
        # Parse the feed using feedparser
        # This is CPU-bound, so we run it in a thread pool
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(
            None,
            lambda: feedparser.parse(content)
        )
        
        # Check for parsing errors
        if hasattr(feed, 'bozo') and feed.bozo and hasattr(feed, 'bozo_exception'):
            # Log the error but continue with what we could parse
            logger.warning(
                "Atom feed parsing error",
                url=self.url,
                error=str(feed.bozo_exception),
            )
        
        # Extract entries
        entries = feed.entries if hasattr(feed, 'entries') else []
        
        logger.debug(
            "Atom feed parsed successfully",
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
            "Extracting blog posts from Atom feed entries",
            url=self.url,
            entry_count=len(entries),
        )
        
        # Use the common parser from base.py
        posts = await parse_feed_entries(
            entries,
            self.name,
            str(self.url),
        )
        
        # Post-process to handle Atom-specific fields
        for i, post in enumerate(posts):
            # Try to extract additional data from the original entry
            if i < len(entries):
                entry = entries[i]
                
                # Handle Atom-specific fields
                
                # Extract published date (Atom uses 'published' instead of 'pubDate')
                if 'published' in entry and not post.publish_date:
                    try:
                        published_date = date_parser.parse(entry['published'])
                        post.publish_date = published_date
                    except Exception as e:
                        logger.warning(
                            "Error parsing published date",
                            url=post.url,
                            date=entry['published'],
                            error=str(e),
                        )
                
                # Extract updated date
                if 'updated' in entry and not post.updated_date:
                    try:
                        updated_date = date_parser.parse(entry['updated'])
                        post.updated_date = updated_date
                    except Exception as e:
                        logger.warning(
                            "Error parsing updated date",
                            url=post.url,
                            date=entry['updated'],
                            error=str(e),
                        )
                
                # Extract author information (Atom has more structured author data)
                if 'author_detail' in entry and not post.author:
                    author_detail = entry['author_detail']
                    if 'name' in author_detail:
                        post.author = author_detail['name']
                    elif 'email' in author_detail:
                        post.author = author_detail['email']
                
                # Extract content
                if 'content' in entry:
                    for content_item in entry['content']:
                        if 'value' in content_item:
                            # Store the full content in metadata
                            post.metadata['full_content'] = content_item['value']
                            
                            # If no summary, create one from content
                            if not post.summary:
                                text = self.clean_html(content_item['value'])
                                if text:
                                    # Limit summary to 200 characters
                                    post.summary = text[:197] + '...' if len(text) > 200 else text
                            break
                
                # Extract categories/tags
                if 'tags' in entry:
                    tags = []
                    for tag in entry['tags']:
                        if 'term' in tag:
                            tags.append(tag['term'].strip())
                        elif 'label' in tag:
                            tags.append(tag['label'].strip())
                    
                    if tags:
                        post.tags = list(set(post.tags + tags))
        
        logger.debug(
            "Extracted blog posts from Atom feed",
            url=self.url,
            post_count=len(posts),
        )
        
        return posts
    
    async def get_feed_fingerprint(self, content: bytes) -> str:
        """
        Generate a fingerprint for the feed content to detect changes.
        
        For Atom feeds, we parse the feed and use the most recent entry's
        ID or link as the fingerprint, as this is more reliable than
        hashing the entire feed content (which might contain timestamps).
        
        Args:
            content: Raw feed content
            
        Returns:
            str: Feed fingerprint
        """
        try:
            # Parse the feed
            loop = asyncio.get_running_loop()
            feed = await loop.run_in_executor(
                None,
                lambda: feedparser.parse(content)
            )
            
            # Get entries
            entries = feed.entries if hasattr(feed, 'entries') else []
            
            if entries:
                # Use the most recent entry's ID or link as the fingerprint
                most_recent = entries[0]
                
                # Try to get a stable identifier
                if hasattr(most_recent, 'id'):
                    return f"id:{most_recent.id}"
                elif hasattr(most_recent, 'link'):
                    return f"link:{most_recent.link}"
                elif hasattr(most_recent, 'title'):
                    return f"title:{most_recent.title}"
            
            # Fall back to feed-level info
            if hasattr(feed, 'feed'):
                if hasattr(feed.feed, 'updated'):
                    return f"updated:{feed.feed.updated}"
                elif hasattr(feed.feed, 'id'):
                    return f"feed_id:{feed.feed.id}"
            
            # Fall back to default implementation
            return await super().get_feed_fingerprint(content)
        
        except Exception as e:
            logger.warning(
                "Error generating Atom feed fingerprint, falling back to default",
                url=self.url,
                error=str(e),
            )
            return await super().get_feed_fingerprint(content)

    @staticmethod
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
