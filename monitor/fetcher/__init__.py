"""
Fetcher package for the technical blog monitor.

This package provides functionality for fetching content from websites,
including both simple HTTP requests and full browser rendering for
JavaScript-heavy pages. It handles concurrency, retries, and resource
management for efficient content retrieval.

The main components are:
- HTTP client for basic requests
- Browser pool for headless browser automation via Playwright
- Screenshot capture and page rendering
"""
from monitor.fetcher.browser import BrowserPool, BrowserContext, render_page, take_screenshot
from monitor.fetcher.http_client import AsyncHTTPClient, fetch_url, fetch_with_retry

__all__ = [
    "BrowserPool",
    "BrowserContext",
    "render_page",
    "take_screenshot",
    "AsyncHTTPClient",
    "fetch_url",
    "fetch_with_retry",
]
