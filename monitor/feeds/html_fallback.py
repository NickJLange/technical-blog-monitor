"""
HTML fallback feed processor for blogs that serve HTML instead of RSS/Atom.

This module provides a feed processor that extracts article links directly
from blog HTML pages when RSS/Atom feeds are unavailable.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
import structlog

from monitor.config import FeedConfig
from monitor.feeds.base import FeedProcessor
from monitor.models.blog_post import BlogPost

logger = structlog.get_logger()


class HTMLFallbackFeedProcessor(FeedProcessor):
    """
    Feed processor that extracts articles directly from blog HTML pages.

    This processor is used when blogs serve HTML instead of RSS/Atom feeds.
    It uses Playwright to render the page and extract article links.
    """

    def __init__(self, config: FeedConfig, browser_pool: Optional[Any] = None):
        """
        Initialize the HTML fallback feed processor.

        Args:
            config: Feed configuration
            browser_pool: Optional BrowserPool for rendering
        """
        super().__init__(config)
        self.browser_pool = browser_pool

    async def fetch_feed(self, client: httpx.AsyncClient) -> bytes:
        """
        Fetch the HTML page using browser rendering.

        Args:
            client: HTTP client (unused, we use browser_pool instead)

        Returns:
            bytes: HTML content from rendered page

        Raises:
            RuntimeError: If browser pool is not available
        """
        if not self.browser_pool:
            raise RuntimeError("Browser pool required for HTML fallback processor")

        logger.info("Fetching blog page with browser rendering", url=self.url)

        try:
            # Render the page using Playwright
            page, page_info = await self.browser_pool.render_page(str(self.url))

            try:
                content = await page.content()
                logger.debug(
                    "Browser rendering successful",
                    url=self.url,
                    content_length=len(content),
                )
                return content.encode("utf-8")
            finally:
                await page.close()

        except Exception as e:
            logger.error("Browser rendering failed", url=self.url, error=str(e))
            raise

    async def parse_feed(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Parse HTML content and extract article links.

        This method uses BeautifulSoup to parse the HTML and extract
        links that look like article URLs.

        Args:
            content: Raw HTML content

        Returns:
            List[Dict[str, Any]]: List of article entries with URL and title

        Raises:
            ValueError: If HTML cannot be parsed
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("BeautifulSoup4 not available for HTML parsing")
            raise ValueError("BeautifulSoup4 is required for HTML fallback parsing")

        try:
            html_str = content.decode("utf-8")
            soup = BeautifulSoup(html_str, "html.parser")

            entries = []
            seen_urls = set()

            # Look for article links based on common patterns
            # Pattern: links within blog sections that contain blog in the href
            selectors = [
                "a[href*='/blog/']",  # Links to blog articles
                "article a",  # Links within article tags
                "h2 a, h3 a",  # Article titles in headings
            ]

            all_links = []
            for selector in selectors:
                all_links.extend(soup.select(selector))

            for link in all_links:
                href = link.get("href")
                text = link.get_text(strip=True)

                if not href or not text or len(text) < 5:
                    continue

                # Make absolute URL
                full_url = urljoin(str(self.url), href)

                # Skip if we've already seen this URL
                if full_url in seen_urls:
                    continue

                # Skip if it doesn't look like an article (too generic)
                if full_url == str(self.url) or full_url.endswith("/blog"):
                    continue

                seen_urls.add(full_url)

                entries.append(
                    {
                        "url": full_url,
                        "title": text[:200],  # Limit title length
                        "published": datetime.now(timezone.utc).isoformat(),
                        "content": text,  # Use link text as placeholder
                    }
                )

            logger.info(
                "Extracted articles from HTML",
                url=self.url,
                article_count=len(entries),
            )
            return entries

        except Exception as e:
            logger.error(
                "Failed to parse HTML content",
                url=self.url,
                error=str(e),
            )
            raise ValueError(f"Failed to parse HTML content: {str(e)}")

    async def extract_posts(self, entries: List[Dict[str, Any]]) -> List[BlogPost]:
        """
        Extract blog posts from HTML entries.

        Args:
            entries: List of entry dictionaries from parse_feed()

        Returns:
            List[BlogPost]: List of blog posts
        """
        import hashlib
        
        posts = []

        for entry in entries:
            try:
                # Parse the publish_date string if it's a string
                publish_date = entry.get("published")
                if isinstance(publish_date, str):
                    # Parse ISO format datetime
                    from datetime import datetime as dt
                    publish_date = dt.fromisoformat(publish_date.replace("Z", "+00:00"))
                
                url = entry.get("url", "")
                # Generate a stable ID from the URL
                post_id = hashlib.sha256(url.encode()).hexdigest()
                
                post = BlogPost(
                    id=post_id,
                    url=url,
                    title=entry.get("title", "Untitled"),
                    author=None,
                    publish_date=publish_date,
                    source=self.name,
                    summary=entry.get("content", ""),
                )
                posts.append(post)
            except Exception as e:
                logger.warning(
                    "Failed to extract post from entry",
                    entry=entry,
                    error=str(e),
                )
                continue

        return posts
