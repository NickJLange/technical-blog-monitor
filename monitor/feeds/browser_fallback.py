"""
Browser fallback feed processor for Cloudflare-protected sites.

This module provides a feed processor that attempts HTTP requests first,
then falls back to browser rendering if the site returns 403 Forbidden
or other bot-detection signals.
"""
import asyncio
from typing import Any, Dict, List, Optional

import httpx
import structlog

from monitor.config import FeedConfig
from monitor.feeds.rss import RSSFeedProcessor
from monitor.models.blog_post import BlogPost
from monitor.parser import parse_html

logger = structlog.get_logger()


class BrowserFallbackFeedProcessor(RSSFeedProcessor):
    """
    Feed processor that falls back to browser rendering for bot-protected sites.
    
    This processor extends the RSS processor and falls back to browser rendering
    if HTTP requests return 403 or other bot-detection signals.
    """
    
    def __init__(self, config: FeedConfig, browser_pool: Optional[Any] = None):
        """
        Initialize the browser fallback feed processor.
        
        Args:
            config: Feed configuration
            browser_pool: Optional BrowserPool for browser rendering
        """
        super().__init__(config)
        self.browser_pool = browser_pool
        logger.debug(
            "Initialized BrowserFallbackFeedProcessor",
            feed_name=config.name,
            has_browser_pool=browser_pool is not None,
        )
    
    async def fetch_feed(self, client: httpx.AsyncClient) -> bytes:
        """
        Fetch the feed, falling back to browser if HTTP fails.
        
        For Cloudflare-protected sites, prefer browser rendering if available
        since HTTP often returns 403 or challenge pages.
        
        Args:
            client: HTTP client to use for the request
            
        Returns:
            bytes: Raw feed content
            
        Raises:
            httpx.HTTPError: If both HTTP and browser methods fail
        """
        # For Cloudflare-protected sites, try browser rendering first if available
        if self.browser_pool:
            logger.info("Browser pool available, using browser rendering for Cloudflare-protected site", url=self.url)
            try:
                return await self._fetch_with_browser()
            except Exception as e:
                logger.warning(
                    "Browser rendering failed, falling back to HTTP",
                    url=self.url,
                    error=str(e),
                )
                # Continue to HTTP fallback below
        
        logger.debug("Attempting HTTP fetch", url=self.url)
        
        try:
            # Try HTTP
            response = await client.get(
                str(self.url),
                headers=dict(self.headers),
                follow_redirects=True,
                timeout=30,
            )
            
            # Check for bot detection signals
            if response.status_code == 403 or 'cf-mitigated' in response.headers.get('cf-mitigated', '').lower():
                # Bot detected
                logger.error(
                    "HTTP returned 403 or bot-detection header",
                    url=self.url,
                    status=response.status_code,
                )
                raise httpx.HTTPStatusError(
                    f"Bot detection ({response.status_code})",
                    request=None,
                    response=response,
                )
            
            response.raise_for_status()
            return response.content
            
        except httpx.HTTPStatusError as e:
            # HTTP request failed, try browser as fallback
            if e.response.status_code == 403 and self.browser_pool:
                logger.info(
                    "HTTP request returned 403, falling back to browser rendering",
                    url=self.url,
                )
                return await self._fetch_with_browser()
            else:
                raise
        except Exception as e:
            # Other errors, try browser as fallback
            logger.warning("HTTP fetch failed, attempting browser fallback", url=self.url, error=str(e))
            if self.browser_pool:
                try:
                    return await self._fetch_with_browser()
                except Exception as browser_error:
                    logger.error("Both HTTP and browser methods failed", url=self.url, error=str(browser_error))
                    raise
            else:
                raise
    
    async def _fetch_with_browser(self) -> bytes:
        """
        Fetch using browser rendering.
        
        Returns:
            bytes: HTML content from rendered page
            
        Raises:
            RuntimeError: If browser pool is not available
            Exception: If browser rendering fails
        """
        if not self.browser_pool:
            raise RuntimeError("Browser pool required for browser rendering")
        
        logger.info("Fetching with browser rendering", url=self.url)
        
        try:
            # Render the page to bypass bot detection
            page, page_info = await self.browser_pool.render_page(str(self.url))
            
            try:
                # Get the rendered HTML
                content = await page.content()
                logger.debug(
                    "Browser rendering successful",
                    url=self.url,
                    content_length=len(content),
                    page_title=page_info.get("title"),
                )
                return content.encode('utf-8')
            finally:
                await page.close()
                
        except Exception as e:
            logger.error("Browser rendering failed", url=self.url, error=str(e))
            raise
