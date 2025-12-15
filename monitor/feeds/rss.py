"""
RSS feed processor for the technical blog monitor.

This module provides functionality for fetching and parsing RSS feeds,
extracting blog posts, and handling various RSS formats and edge cases.
It implements the FeedProcessor interface for RSS feeds.
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
        
        # Prepare headers - use a copy to avoid modifying the shared headers
        headers = dict(self.headers)
        
        # Some sites reject specific Accept headers (e.g., Uber)
        # If we get a 406, we'll retry with a more general Accept header
        url_str = str(self.url)
        
        # Make the request
        try:
            response = await client.get(
                url_str,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # If we get 406 Not Acceptable, retry with simpler Accept header
            if e.response.status_code == 406:
                logger.info(
                    "Got 406 Not Acceptable, retrying with generic Accept header",
                    url=self.url,
                )
                headers["Accept"] = "*/*"
                headers["Accept-Encoding"] = "gzip"
                response = await client.get(
                    url_str,
                    headers=headers,
                    follow_redirects=True,
                )
                response.raise_for_status()
            elif e.response.status_code == 403 and "medium.com" in url_str.lower():
                # Medium blocks direct HTTP requests - need browser rendering
                logger.info(
                    "Medium blog detected with 403, would need browser rendering",
                    url=self.url,
                    note="Requires Playwright browser pool for Medium blogs"
                )
                raise
            else:
                raise
        
        # Get the content
        content = response.content
        
        # Handle various compression formats if httpx didn't auto-decompress
        if content.startswith(b'\x1f\x8b'):  # gzip magic number
            import gzip
            try:
                content = gzip.decompress(content)
                logger.debug("Decompressed gzip content", url=self.url)
            except Exception as e:
                logger.warning("Failed to decompress gzip content", url=self.url, error=str(e))
        elif content.startswith(b'\x28\xb5\x2f\xfd'):  # zstd magic number
            import zstandard
            try:
                dctx = zstandard.ZstdDecompressor()
                content = dctx.decompress(content)
                logger.debug("Decompressed zstd content", url=self.url)
            except Exception as e:
                logger.warning("Failed to decompress zstd content", url=self.url, error=str(e))
        else:
            # Try brotli as fallback for unknown compression
            try:
                import brotli
                decompressed = brotli.decompress(content)
                # Only use if it produces valid content (check for HTML markers)
                if b'<' in decompressed and b'>' in decompressed:
                    content = decompressed
                    logger.debug("Decompressed brotli content", url=self.url)
            except Exception:
                # Not brotli, or decompression failed - use original content
                pass
        
        # Check if the content is valid XML
        if not content.strip().startswith(b'<?xml') and not content.strip().startswith(b'<rss'):
            # Try to find RSS feed URL in HTML
            try:
                soup = BeautifulSoup(content, 'html.parser')
                rss_link = soup.find('link', rel='alternate', type='application/rss+xml')
                
                if rss_link and rss_link.get('href'):
                    rss_url = rss_link['href']
                    # Handle relative URLs
                    if not rss_url.startswith(('http://', 'https://')):
                        base_url = str(self.url)
                        rss_url = urljoin(base_url, rss_url)
                    
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
            except Exception as e:
                logger.warning(
                    "Error trying to find RSS feed URL in HTML",
                    url=self.url,
                    error=str(e),
                )
        
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
        
        # First check if content is HTML (likely HTML page instead of RSS)
        if content.strip().startswith(b'<!DOCTYPE') or b'<html' in content[:500]:
            logger.warning(
                "Feed URL returned HTML instead of RSS/XML",
                url=self.url,
            )
            # Try to extract articles from HTML using BeautifulSoup
            return await self._parse_html_as_feed(content)
        
        # Parse the feed using feedparser
        # This is CPU-bound, so we run it in a thread pool
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(
            None,
            lambda: feedparser.parse(content)
        )
        
        # Check for parsing errors
        if hasattr(feed, 'bozo') and feed.bozo and hasattr(feed, 'bozo_exception'):
            logger.warning(
                "RSS feed parsing error",
                url=self.url,
                error=str(feed.bozo_exception),
            )
            
            # If parsing failed severely, try to recover with HTML parsing
            if not hasattr(feed, 'entries') or not feed.entries:
                logger.info(
                    "Attempting fallback HTML parsing for malformed RSS",
                    url=self.url,
                )
                return await self._parse_html_as_feed(content)
        
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
    
    async def _parse_html_as_feed(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Attempt to parse an HTML page as a feed by extracting article links.
        This is a fallback for sites that serve HTML instead of RSS feeds.
        
        Args:
            content: Raw HTML content
            
        Returns:
            List[Dict[str, Any]]: List of extracted entries
        """
        try:
            loop = asyncio.get_running_loop()
            base_url = str(self.url)
            
            def parse_html():
                soup = BeautifulSoup(content, 'html.parser')
                entries = []
                
                # Look for article elements and links within them
                # Priority order: article > h1/h2 links > post containers > generic links
                
                # Strategy 1: Look for <article> elements
                for article in soup.find_all('article'):
                    # Find the main article link by selecting the longest text link
                    # (article titles are usually longer than breadcrumbs/author names)
                    link = None
                    
                    links_in_article = article.find_all('a', href=True)
                    if links_in_article:
                        # Sort by text length descending, prefer longer titles (article titles are longer)
                        sorted_links = sorted(
                            links_in_article,
                            key=lambda l: len(l.get_text(strip=True)),
                            reverse=True
                        )
                        # Find first link with substantial text (skip breadcrumbs, author names, etc.)
                        for candidate in sorted_links:
                            text_len = len(candidate.get_text(strip=True))
                            if text_len > 10:  # Article titles are typically > 10 chars
                                link = candidate
                                break
                        
                        # Fallback: if no link with > 10 chars, use first link with > 5 chars
                        if not link:
                            for candidate in sorted_links:
                                if len(candidate.get_text(strip=True)) > 5:
                                    link = candidate
                                    break
                    
                    if link:
                        href = link.get('href', '')
                        title = link.get_text(strip=True)
                        
                        if href and title and len(title) > 5:
                            # Resolve relative URLs
                            if not href.startswith(('http://', 'https://')):
                                href = urljoin(base_url, href)
                            
                            # Look for date in article
                            published = None
                            time_elem = article.find('time')
                            if time_elem:
                                published = time_elem.get_text(strip=True)
                            
                            entries.append({
                                'title': title,
                                'link': href,
                                'published': published,
                            })
                
                # Strategy 2: Look for heading links (h1, h2, h3) in post containers
                if not entries:
                    for container in soup.find_all(['div', 'section'], class_=lambda x: x and any(
                        keyword in (x or '').lower() for keyword in ['post', 'article', 'item', 'entry']
                    )):
                        for heading in container.find_all(['h1', 'h2', 'h3']):
                            link = heading.find('a', href=True)
                            if link:
                                href = link.get('href', '')
                                title = link.get_text(strip=True)
                                
                                if href and title and len(title) > 5:
                                    if not href.startswith(('http://', 'https://')):
                                        href = urljoin(base_url, href)
                                    
                                    published = None
                                    time_elem = container.find('time')
                                    if time_elem:
                                        published = time_elem.get_text(strip=True)
                                    
                                    entries.append({
                                        'title': title,
                                        'link': href,
                                        'published': published,
                                    })
                
                # Strategy 3: Look for links that look like article URLs
                if not entries:
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '')
                        
                        # Skip non-article links
                        if not href or href.startswith('#') or href.startswith('javascript'):
                            continue
                        
                        # Check if URL looks like an article (common blog patterns)
                        url_lower = href.lower()
                        article_patterns = [
                            '/blog/', '/post/', '/article/', '/news/', '/stories/',
                            '/engineering/', '/tech/', '/research/', '-2024', '-2025'
                        ]
                        # Add year patterns
                        article_patterns.extend(f'/20{year % 100:02d}' for year in range(2020, 2026))
                        is_article_like = any(pattern in url_lower for pattern in article_patterns)
                        
                        if not is_article_like:
                            continue
                        
                        # Resolve relative URLs
                        if not href.startswith(('http://', 'https://')):
                            href = urljoin(base_url, href)
                        
                        # Extract potential title
                        title = link.get_text(strip=True)
                        if not title or len(title) < 5:
                            continue
                        
                        # Skip navigation and common non-article links
                        skip_keywords = ['home', 'menu', 'cart', 'account', 'login', 'sign up', 
                                       'about us', 'contact', 'privacy', 'terms', 'subscribe',
                                       'newsletter', 'email', 'download']
                        if any(keyword in title.lower() for keyword in skip_keywords):
                            continue
                        
                        # Try to get publication date from nearby time elements
                        time_elem = link.find_next('time')
                        published = None
                        if time_elem:
                            published = time_elem.get_text(strip=True)
                        
                        entries.append({
                            'title': title,
                            'link': href,
                            'published': published,
                        })
                
                # Deduplicate by URL
                seen = set()
                unique_entries = []
                for entry in entries:
                    url = entry.get('link', '')
                    if url and url not in seen:
                        seen.add(url)
                        unique_entries.append(entry)
                
                return unique_entries[:20]  # Return top 20 entries
            
            entries = await loop.run_in_executor(None, parse_html)
            logger.info(
                "Extracted entries from HTML feed",
                url=self.url,
                entry_count=len(entries),
            )
            return entries
        
        except Exception as e:
            logger.error(
                "Failed to parse HTML as feed",
                url=self.url,
                error=str(e),
            )
            return []
    
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
        
        For RSS feeds, we parse the feed and use the most recent entry's
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
            if hasattr(feed, 'feed') and hasattr(feed.feed, 'updated'):
                return f"updated:{feed.feed.updated}"
            
            # Fall back to default implementation
            return await super().get_feed_fingerprint(content)
        
        except Exception as e:
            logger.warning(
                "Error generating RSS feed fingerprint, falling back to default",
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
