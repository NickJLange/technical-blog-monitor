"""
Medium blog feed processor using browser rendering.

This module provides a feed processor for Medium-hosted blogs that require
JavaScript rendering and bot detection evasion. It uses Playwright with
stealth mode to fetch and parse Medium blog feeds.
"""
import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
import structlog
from bs4 import BeautifulSoup

from monitor.config import FeedConfig
from monitor.feeds.base import FeedProcessor, parse_feed_entries
from monitor.models.blog_post import BlogPost

logger = structlog.get_logger()


class MediumFeedProcessor(FeedProcessor):
    """
    Medium blog feed processor that uses browser rendering.
    
    Medium blocks direct HTTP requests and requires JavaScript execution.
    This processor uses Playwright with stealth mode to fetch content.
    """
    
    def __init__(self, config: FeedConfig, browser_pool: Optional[Any] = None):
        """
        Initialize the Medium feed processor.
        
        Args:
            config: Feed configuration
            browser_pool: Optional BrowserPool for rendering pages
        """
        super().__init__(config)
        self.browser_pool = browser_pool
    
    async def fetch_feed(self, client: httpx.AsyncClient) -> bytes:
        """
        Fetch the Medium blog feed using browser rendering.
        
        Args:
            client: HTTP client (not used for Medium, but required by interface)
            
        Returns:
            bytes: Raw HTML content of the blog page
            
        Raises:
            RuntimeError: If browser pool is not available
        """
        if not self.browser_pool:
            raise RuntimeError(
                f"Browser pool required for Medium blog: {self.url}. "
                "Ensure browser pool is initialized in app context."
            )
        
        logger.info("Fetching Medium blog using browser", url=self.url)
        
        try:
            # Render the page using the browser pool to get actual content
            page, page_info = await self.browser_pool.render_page(str(self.url))
            
            try:
                # Get the rendered HTML from the page
                content = await page.content()
                logger.debug(
                    "Page rendered successfully via browser",
                    url=self.url,
                    content_length=len(content),
                    page_title=page_info.get("title")
                )
                return content.encode('utf-8')
            finally:
                # Make sure to close the page
                await page.close()
            
        except Exception as e:
            logger.error(
                "Failed to fetch Medium blog via browser",
                url=self.url,
                error=str(e),
            )
            raise
    
    async def parse_feed(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Parse Medium blog HTML to extract article links.
        
        Args:
            content: Raw HTML content
            
        Returns:
            List[Dict[str, Any]]: List of feed entries as dictionaries
        """
        logger.debug("Parsing Medium blog content")
        
        try:
            loop = asyncio.get_running_loop()
            
            def parse_html():
                soup = BeautifulSoup(content, 'html.parser')
                entries = []
                
                # Medium uses article links with specific patterns
                # Look for article links in the feed
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    
                    # Skip non-article links
                    if not href or href.startswith('#') or 'medium.com' not in href.lower():
                        continue
                    
                    # Extract title
                    title = link.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    
                    # Try to get publication date
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
                
                return unique_entries[:20]
            
            entries = await loop.run_in_executor(None, parse_html)
            logger.info(
                "Parsed Medium blog entries",
                url=self.url,
                entry_count=len(entries),
            )
            return entries
            
        except Exception as e:
            logger.error(
                "Failed to parse Medium blog",
                url=self.url,
                error=str(e),
            )
            return []
    
    async def extract_posts(self, entries: List[Dict[str, Any]]) -> List[BlogPost]:
        """
        Extract blog posts from Medium feed entries.
        
        Args:
            entries: List of feed entries as dictionaries
            
        Returns:
            List[BlogPost]: List of blog posts
        """
        logger.debug(
            "Extracting blog posts from Medium feed entries",
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
            "Extracted blog posts from Medium feed",
            url=self.url,
            post_count=len(posts),
        )
        
        return posts
