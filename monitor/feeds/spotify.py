"""
Spotify Engineering blog feed processor using browser rendering.

This module provides a feed processor for Spotify's engineering blog which
uses Next.js client-side rendering. It requires JavaScript execution via
Playwright to extract content.
"""
import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
import structlog

from monitor.config import FeedConfig
from monitor.feeds.base import FeedProcessor, parse_feed_entries
from monitor.models.blog_post import BlogPost
from monitor.parser import parse_html

logger = structlog.get_logger()


class SpotifyFeedProcessor(FeedProcessor):
    """
    Spotify Engineering blog feed processor that uses browser rendering.
    
    Spotify's engineering blog is built with Next.js and loads content
    client-side with JavaScript. This processor uses Playwright to render
    the page and extract articles from the rendered HTML.
    """
    
    def __init__(self, config: FeedConfig, browser_pool: Optional[Any] = None):
        """
        Initialize the Spotify feed processor.
        
        Args:
            config: Feed configuration
            browser_pool: Optional BrowserPool for rendering pages
        """
        super().__init__(config)
        self.browser_pool = browser_pool
    
    async def fetch_feed(self, client: httpx.AsyncClient) -> bytes:
        """
        Fetch the Spotify blog feed using HTTP with browser-like headers.
        Falls back to browser rendering if HTTP request fails.
        
        Args:
            client: HTTP client for the request
            
        Returns:
            bytes: Raw HTML content of the blog page
        """
        logger.info("Fetching Spotify Engineering blog", url=self.url)
        
        try:
            # Try direct HTTP request with browser-like headers first
            headers = dict(self.headers)
            headers["Referer"] = str(self.url)
            headers["Sec-Fetch-Mode"] = "navigate"
            headers["Sec-Fetch-Dest"] = "document"
            
            response = await client.get(
                str(self.url),
                headers=headers,
                follow_redirects=True,
                timeout=30.0,
            )
            response.raise_for_status()
            logger.debug("Fetched Spotify blog via HTTP", url=self.url)
            return response.content
            
        except Exception as http_error:
            # Fall back to browser rendering if HTTP fails
            if self.browser_pool:
                logger.info(
                    "HTTP fetch failed, falling back to browser rendering",
                    url=self.url,
                    error=str(http_error),
                )
                try:
                    # Render the page using the browser pool
                    screenshot_path = await self.browser_pool.render_and_screenshot(str(self.url))
                    logger.debug("Page rendered successfully with browser", url=self.url)
                    
                    # Try HTTP fetch again after rendering
                    headers = dict(self.headers)
                    response = await client.get(
                        str(self.url),
                        headers=headers,
                        follow_redirects=True,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    return response.content
                except Exception as e:
                    logger.error(
                        "Failed to fetch Spotify blog with browser rendering",
                        url=self.url,
                        error=str(e),
                    )
                    raise
            else:
                logger.error(
                    "Failed to fetch Spotify blog and browser pool not available",
                    url=self.url,
                    error=str(http_error),
                )
                raise
    
    async def parse_feed(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Parse Spotify blog HTML to extract article links.
        
        Args:
            content: Raw HTML content
            
        Returns:
            List[Dict[str, Any]]: List of feed entries as dictionaries
        """
        logger.debug("Parsing Spotify blog content")
        
        try:
            loop = asyncio.get_running_loop()
            
            def parse_spotify_content():
                parser = parse_html(content)
                entries = []
                
                # Spotify uses article links with format: /YYYY/MM/article-slug
                # Look for article links on the page
                for link in parser.find_all('a', href=True):
                    href = link.get('href')
                    
                    # Skip non-article links
                    if not href or href.startswith('#'):
                        continue
                    
                    # Spotify articles follow the pattern /YYYY/MM/... (e.g., /2025/12/feedback-loops-...)
                    import re
                    if not re.match(r'^/\d{4}/\d{2}/', href):
                        continue
                    
                    # Extract title
                    title = link.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    
                    # Resolve relative URLs to absolute URLs
                    if not href.startswith(('http://', 'https://')):
                        href = urljoin('https://engineering.atspotify.com', href)
                    
                    # Try to get publication date from nearby time elements or extract from URL
                    published = None
                    parent = link.parent
                    while parent:
                        time_elem = parent.find('time')
                        if time_elem:
                            published = time_elem.get_text(strip=True)
                            break
                        parent = parent.parent
                    
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
                
                return unique_entries[:50]  # Return up to 50 entries
            
            entries = await loop.run_in_executor(None, parse_spotify_content)
            logger.info(
                "Parsed Spotify blog entries",
                url=self.url,
                entry_count=len(entries),
            )
            return entries
            
        except Exception as e:
            logger.error(
                "Failed to parse Spotify blog",
                url=self.url,
                error=str(e),
            )
            return []
    
    async def extract_posts(self, entries: List[Dict[str, Any]]) -> List[BlogPost]:
        """
        Extract blog posts from Spotify feed entries.
        
        Args:
            entries: List of feed entries as dictionaries
            
        Returns:
            List[BlogPost]: List of blog posts
        """
        logger.debug(
            "Extracting blog posts from Spotify feed entries",
            url=self.url,
            entry_count=len(entries),
        )
        
        # Use the common parser from base.py
        posts = await parse_feed_entries(
            entries,
            self.name,
            str(self.url),
        )
        
        logger.debug(
            "Extracted blog posts from Spotify feed",
            url=self.url,
            post_count=len(posts),
        )
        
        return posts
