"""
Browser pool module for the technical blog monitor.

This module provides a pool of headless browsers using Playwright for
rendering web pages and capturing screenshots. It handles concurrent
browser instances, resource management, and provides an async context
manager interface for efficient browser usage.
"""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import structlog
from playwright.async_api import (
    Browser,
    BrowserContext as PlaywrightBrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from monitor.config import BrowserConfig

# Set up structured logger
logger = structlog.get_logger()


class BrowserContext:
    """
    Represents a browser context for rendering pages.
    
    This class wraps a Playwright browser context and provides methods
    for rendering pages, taking screenshots, and extracting content.
    """
    
    def __init__(
        self,
        browser: Browser,
        context: PlaywrightBrowserContext,
        config: BrowserConfig,
    ):
        """
        Initialize a browser context.
        
        Args:
            browser: Playwright browser instance
            context: Playwright browser context
            config: Browser configuration
        """
        self.browser = browser
        self.context = context
        self.config = config
        self.pages: Set[Page] = set()
        self.in_use = False
        self.last_used = time.time()
    
    async def new_page(self) -> Page:
        """
        Create a new page in this browser context.
        
        Returns:
            Page: Playwright page object
        """
        page = await self.context.new_page()
        self.pages.add(page)
        
        # Set viewport size
        await page.set_viewport_size({
            "width": self.config.viewport_width,
            "height": self.config.viewport_height,
        })
        
        # Apply stealth mode if enabled
        if self.config.stealth_mode:
            await self._apply_stealth_mode(page)
        
        # Block ads if enabled
        if self.config.block_ads:
            await self._setup_ad_blocking(page)
        
        return page
    
    async def _apply_stealth_mode(self, page: Page) -> None:
        """
        Apply stealth mode to avoid bot detection.
        
        Args:
            page: Playwright page object
        """
        # Override user agent if specified
        if self.config.user_agent:
            await page.set_extra_http_headers({"User-Agent": self.config.user_agent})
        
        # Mask WebDriver
        await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });
        """)
        
        # Add language
        await page.add_init_script("""
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        """)
        
        # Mask automation
        await page.add_init_script("""
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        """)
    
    async def _setup_ad_blocking(self, page: Page) -> None:
        """
        Set up ad blocking for a page.
        
        Args:
            page: Playwright page object
        """
        # Block common ad domains
        ad_domains = [
            'googlesyndication.com',
            'googleadservices.com',
            'doubleclick.net',
            'adservice.google.com',
            'advertising.com',
        ]
        
        await page.route('**/*', lambda route, request: 
            route.abort() if any(ad in request.url for ad in ad_domains) else route.continue_()
        )
    
    async def close_page(self, page: Page) -> None:
        """
        Close a page and remove it from the set of pages.
        
        Args:
            page: Playwright page object to close
        """
        if page in self.pages:
            try:
                await page.close()
            except Exception as e:
                logger.warning("Error closing page", error=str(e))
            finally:
                self.pages.remove(page)
    
    async def close(self) -> None:
        """Close all pages and the browser context."""
        # Close all pages
        for page in list(self.pages):
            await self.close_page(page)
        
        # Close the context
        try:
            await self.context.close()
        except Exception as e:
            logger.warning("Error closing browser context", error=str(e))
    
    def mark_as_used(self) -> None:
        """Mark this context as in use and update the last used time."""
        self.in_use = True
        self.last_used = time.time()
    
    def mark_as_free(self) -> None:
        """Mark this context as free and update the last used time."""
        self.in_use = False
        self.last_used = time.time()
    
    def is_idle(self, idle_timeout: float = 300) -> bool:
        """
        Check if this context has been idle for longer than the timeout.
        
        Args:
            idle_timeout: Idle timeout in seconds
            
        Returns:
            bool: True if the context has been idle for longer than the timeout
        """
        return not self.in_use and (time.time() - self.last_used) > idle_timeout


class BrowserPool:
    """
    Pool of browser instances for rendering pages.
    
    This class manages a pool of browser instances and contexts, providing
    an efficient way to render multiple pages concurrently while limiting
    resource usage.
    """
    
    def __init__(self, config: BrowserConfig):
        """
        Initialize the browser pool.
        
        Args:
            config: Browser configuration
        """
        self.config = config
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.contexts: List[BrowserContext] = []
        self.semaphore = asyncio.Semaphore(config.max_concurrent_browsers)
        self._shutdown = False
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def __aenter__(self) -> "BrowserPool":
        """Initialize the browser pool when entering the context manager."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up resources when exiting the context manager."""
        await self.shutdown()
    
    async def initialize(self) -> None:
        """Initialize the browser pool."""
        if self.playwright is not None:
            return
        
        logger.info("Initializing browser pool", browser_type=self.config.browser_type)
        
        # Start Playwright
        self.playwright = await async_playwright().start()
        
        # Launch browser
        browser_type = getattr(self.playwright, self.config.browser_type)
        self.browser = await browser_type.launch(headless=self.config.headless)
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        logger.info("Browser pool initialized", browser_type=self.config.browser_type)
    
    async def shutdown(self) -> None:
        """Shut down the browser pool and release all resources."""
        if self._shutdown:
            return
        
        logger.info("Shutting down browser pool")
        self._shutdown = True
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all contexts
        for context in list(self.contexts):
            await context.close()
        self.contexts.clear()
        
        # Close browser
        if self.browser:
            await self.browser.close()
            self.browser = None
        
        # Stop Playwright
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        
        logger.info("Browser pool shut down")
    
    async def close(self) -> None:
        """Alias for shutdown() for compatibility with context manager patterns."""
        await self.shutdown()
    
    async def _periodic_cleanup(self) -> None:
        """Periodically clean up idle browser contexts."""
        try:
            while not self._shutdown:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_idle_contexts()
        except asyncio.CancelledError:
            logger.debug("Cleanup task cancelled")
        except Exception as e:
            logger.error("Error in cleanup task", error=str(e))
    
    async def _cleanup_idle_contexts(self, idle_timeout: float = 300) -> None:
        """
        Clean up browser contexts that have been idle for too long.
        
        Args:
            idle_timeout: Idle timeout in seconds
        """
        contexts_to_remove = []
        
        for context in self.contexts:
            if context.is_idle(idle_timeout):
                logger.debug("Cleaning up idle browser context")
                await context.close()
                contexts_to_remove.append(context)
        
        # Remove closed contexts from the list
        for context in contexts_to_remove:
            self.contexts.remove(context)
    
    async def _create_context(self) -> BrowserContext:
        """
        Create a new browser context.
        
        Returns:
            BrowserContext: New browser context
        """
        if not self.browser:
            await self.initialize()
        
        # Create a new browser context
        playwright_context = await self.browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            user_agent=self.config.user_agent,
            java_script_enabled=not self.config.disable_javascript,
        )
        
        # Create our wrapper context
        context = BrowserContext(self.browser, playwright_context, self.config)
        self.contexts.append(context)
        
        return context
    
    async def _get_free_context(self) -> BrowserContext:
        """
        Get a free browser context from the pool or create a new one.
        
        Returns:
            BrowserContext: Free browser context
        """
        # First, try to find an existing free context
        for context in self.contexts:
            if not context.in_use:
                context.mark_as_used()
                return context
        
        # If no free context is available, create a new one
        context = await self._create_context()
        context.mark_as_used()
        return context
    
    @asynccontextmanager
    async def get_context(self) -> BrowserContext:
        """
        Get a browser context from the pool.
        
        This is a context manager that automatically returns the context
        to the pool when the context block exits.
        
        Yields:
            BrowserContext: Browser context from the pool
        """
        async with self.semaphore:
            context = await self._get_free_context()
            try:
                yield context
            finally:
                context.mark_as_free()
    
    async def render_page(
        self,
        url: str,
        wait_until: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[Page, Dict[str, Any]]:
        """
        Render a page in a browser.
        
        Args:
            url: URL to render
            wait_until: When to consider the page loaded
                (load, domcontentloaded, networkidle)
            timeout: Page load timeout in seconds
            
        Returns:
            Tuple[Page, Dict[str, Any]]: Playwright page and page info
        """
        wait_until = wait_until or self.config.wait_until
        timeout = timeout or self.config.timeout_seconds * 1000  # Convert to ms
        
        async with self.get_context() as context:
            # Create a new page
            page = await context.new_page()
            
            try:
                # Navigate to the URL
                start_time = time.time()
                url_str = str(url)
                response = await page.goto(
                    url_str,
                    wait_until=wait_until,
                    timeout=timeout,
                )
                load_time = time.time() - start_time
                
                # Get page info
                title = await page.title()
                
                # Get page metrics
                metrics = await page.evaluate("""() => {
                    return {
                        jsHeapSize: performance.memory ? performance.memory.usedJSHeapSize : 0,
                        domNodes: document.querySelectorAll('*').length,
                        resources: performance.getEntriesByType('resource').length
                    }
                }""")
                
                # Collect page info
                page_info = {
                    "title": title,
                    "url": page.url,
                    "status": response.status if response else None,
                    "content_type": response.headers.get("content-type") if response else None,
                    "load_time_seconds": load_time,
                    "metrics": metrics,
                }
                
                return page, page_info
            
            except Exception as e:
                await context.close_page(page)
                raise RuntimeError(f"Error rendering page {url}: {str(e)}") from e
    
    async def take_screenshot(
        self,
        page: Page,
        path: Optional[Union[str, Path]] = None,
        full_page: Optional[bool] = None,
        format: Optional[str] = None,
    ) -> str:
        """
        Take a screenshot of a page.
        
        Args:
            page: Playwright page object
            path: Path to save the screenshot (if None, a default path is used)
            full_page: Whether to take a full-page screenshot
            format: Screenshot format (png or jpeg)
            
        Returns:
            str: Path to the saved screenshot
        """
        full_page = full_page if full_page is not None else self.config.screenshot_full_page
        format = format or self.config.screenshot_format
        
        # Create a default path if none is provided
        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.{format}"
            base_dir = self.config.screenshot_dir or (Path.cwd() / "data" / "screenshots")
            base_dir.mkdir(parents=True, exist_ok=True)
            path = base_dir / filename
        else:
            path = Path(path)
        
        # Ensure the directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Take the screenshot
        await page.screenshot(
            path=str(path),
            full_page=full_page,
            type=format,
        )
        
        return str(path)
    
    async def render_and_screenshot(
        self,
        url: str,
        screenshot_path: Optional[Union[str, Path]] = None,
        wait_until: Optional[str] = None,
        timeout: Optional[float] = None,
        full_page: Optional[bool] = None,
        format: Optional[str] = None,
    ) -> str:
        """
        Render a page and take a screenshot.
        
        This is a convenience method that combines rendering a page and
        taking a screenshot in a single operation.
        
        Args:
            url: URL to render
            screenshot_path: Path to save the screenshot
            wait_until: When to consider the page loaded
            timeout: Page load timeout in seconds
            full_page: Whether to take a full-page screenshot
            format: Screenshot format
            
        Returns:
            str: Path to the saved screenshot
        """
        try:
            page, page_info = await self.render_page(url, wait_until, timeout)
            
            try:
                screenshot_path = await self.take_screenshot(
                    page,
                    screenshot_path,
                    full_page,
                    format,
                )
                
                logger.info(
                    "Rendered page and took screenshot",
                    url=url,
                    title=page_info["title"],
                    load_time=page_info["load_time_seconds"],
                    screenshot_path=screenshot_path,
                )
                
                return screenshot_path
            
            finally:
                # Find the context that owns this page
                for context in self.contexts:
                    if page in context.pages:
                        await context.close_page(page)
                        break
        
        except Exception as e:
            logger.error(
                "Error rendering page and taking screenshot",
                url=url,
                error=str(e),
            )
            raise


async def render_page(
    url: str,
    config: BrowserConfig,
    wait_until: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Render a page using a temporary browser instance.
    
    This is a standalone function for one-off page rendering without
    managing a browser pool.
    
    Args:
        url: URL to render
        config: Browser configuration
        wait_until: When to consider the page loaded
        timeout: Page load timeout in seconds
        
    Returns:
        Dict[str, Any]: Page information
    """
    async with async_playwright() as playwright:
        # Launch browser
        browser_type = getattr(playwright, config.browser_type)
        browser = await browser_type.launch(headless=config.headless)
        
        try:
            # Create context
            context = await browser.new_context(
                viewport={
                    "width": config.viewport_width,
                    "height": config.viewport_height,
                },
                user_agent=config.user_agent,
                java_script_enabled=not config.disable_javascript,
            )
            
            try:
                # Create page
                page = await context.new_page()
                
                try:
                    # Navigate to URL
                    wait_until = wait_until or config.wait_until
                    timeout = timeout or config.timeout_seconds * 1000  # Convert to ms
                    
                    start_time = time.time()
                    response = await page.goto(
                        url,
                        wait_until=wait_until,
                        timeout=timeout,
                    )
                    load_time = time.time() - start_time
                    
                    # Get page info
                    title = await page.title()
                    
                    # Return page info
                    return {
                        "title": title,
                        "url": page.url,
                        "status": response.status if response else None,
                        "content_type": response.headers.get("content-type") if response else None,
                        "load_time_seconds": load_time,
                    }
                
                finally:
                    await page.close()
            
            finally:
                await context.close()
        
        finally:
            await browser.close()


async def take_screenshot(
    url: str,
    path: Union[str, Path],
    config: BrowserConfig,
    wait_until: Optional[str] = None,
    timeout: Optional[float] = None,
    full_page: Optional[bool] = None,
    format: Optional[str] = None,
) -> str:
    """
    Take a screenshot of a page using a temporary browser instance.
    
    This is a standalone function for one-off screenshots without
    managing a browser pool.
    
    Args:
        url: URL to render
        path: Path to save the screenshot
        config: Browser configuration
        wait_until: When to consider the page loaded
        timeout: Page load timeout in seconds
        full_page: Whether to take a full-page screenshot
        format: Screenshot format
        
    Returns:
        str: Path to the saved screenshot
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as playwright:
        # Launch browser
        browser_type = getattr(playwright, config.browser_type)
        browser = await browser_type.launch(headless=config.headless)
        
        try:
            # Create context
            context = await browser.new_context(
                viewport={
                    "width": config.viewport_width,
                    "height": config.viewport_height,
                },
                user_agent=config.user_agent,
                java_script_enabled=not config.disable_javascript,
            )
            
            try:
                # Create page
                page = await context.new_page()
                
                try:
                    # Navigate to URL
                    wait_until = wait_until or config.wait_until
                    timeout = timeout or config.timeout_seconds * 1000  # Convert to ms
                    
                    await page.goto(
                        url,
                        wait_until=wait_until,
                        timeout=timeout,
                    )
                    
                    # Take screenshot
                    full_page = full_page if full_page is not None else config.screenshot_full_page
                    format = format or config.screenshot_format
                    
                    await page.screenshot(
                        path=str(path),
                        full_page=full_page,
                        type=format,
                    )
                    
                    return str(path)
                
                finally:
                    await page.close()
            
            finally:
                await context.close()
        
        finally:
            await browser.close()
