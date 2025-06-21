"""
HTTP client module for the technical blog monitor.

This module provides an async HTTP client for fetching content from web sources,
with retry logic, timeout handling, and proper error handling. It uses httpx
for making HTTP requests and tenacity for retry logic.
"""
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitor.config import Settings

# Set up structured logger
logger = structlog.get_logger()

# Constants
DEFAULT_USER_AGENT = "Technical-Blog-Monitor/0.1.0 (+https://github.com/your-org/technical-blog-monitor)"
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_MIN_WAIT = 1.0  # seconds
DEFAULT_RETRY_MAX_WAIT = 10.0  # seconds
DEFAULT_RETRY_MULTIPLIER = 1.0


class AsyncHTTPClient:
    """
    Async HTTP client for fetching content from web sources.
    
    This class provides a wrapper around httpx with retry logic,
    timeout handling, and proper error handling.
    """
    
    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_min_wait: float = DEFAULT_RETRY_MIN_WAIT,
        retry_max_wait: float = DEFAULT_RETRY_MAX_WAIT,
        retry_multiplier: float = DEFAULT_RETRY_MULTIPLIER,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the HTTP client.
        
        Args:
            user_agent: User agent string to use for requests
            timeout: Request timeout in seconds
            retry_attempts: Maximum number of retry attempts
            retry_min_wait: Minimum wait time between retries in seconds
            retry_max_wait: Maximum wait time between retries in seconds
            retry_multiplier: Multiplier for exponential backoff
            default_headers: Default headers to include in all requests
        """
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait
        self.retry_multiplier = retry_multiplier
        
        # Set up default headers
        self.default_headers = default_headers or {}
        if "User-Agent" not in self.default_headers:
            self.default_headers["User-Agent"] = self.user_agent
        
        # Create HTTP client
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=self.default_headers,
        )
    
    async def __aenter__(self) -> "AsyncHTTPClient":
        """Enter the async context manager."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        await self.close()
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        follow_redirects: bool = True,
        with_retry: bool = True,
    ) -> httpx.Response:
        """
        Make a GET request to a URL.
        
        Args:
            url: URL to fetch
            headers: Optional headers to include in the request
            params: Optional query parameters
            timeout: Request timeout in seconds (overrides client default)
            follow_redirects: Whether to follow redirects
            with_retry: Whether to use retry logic
            
        Returns:
            httpx.Response: HTTP response
            
        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        # Merge headers
        request_headers = {**self.default_headers}
        if headers:
            request_headers.update(headers)
        
        # Set timeout
        request_timeout = httpx.Timeout(timeout or self.timeout)
        
        if with_retry:
            return await self._get_with_retry(
                url,
                request_headers,
                params,
                request_timeout,
                follow_redirects,
            )
        else:
            return await self.client.get(
                url,
                headers=request_headers,
                params=params,
                timeout=request_timeout,
                follow_redirects=follow_redirects,
            )
    
    async def _get_with_retry(
        self,
        url: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]],
        timeout: httpx.Timeout,
        follow_redirects: bool,
    ) -> httpx.Response:
        """
        Make a GET request with retry logic.
        
        Args:
            url: URL to fetch
            headers: Headers to include in the request
            params: Query parameters
            timeout: Request timeout
            follow_redirects: Whether to follow redirects
            
        Returns:
            httpx.Response: HTTP response
            
        Raises:
            httpx.HTTPError: If the HTTP request fails after all retries
        """
        retry_exceptions = (
            httpx.HTTPError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.WriteError,
        )
        
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.retry_attempts),
                wait=wait_exponential(
                    multiplier=self.retry_multiplier,
                    min=self.retry_min_wait,
                    max=self.retry_max_wait,
                ),
                retry=retry_if_exception_type(retry_exceptions),
                reraise=True,
            ):
                with attempt:
                    try:
                        start_time = time.time()
                        response = await self.client.get(
                            url,
                            headers=headers,
                            params=params,
                            timeout=timeout,
                            follow_redirects=follow_redirects,
                        )
                        response.raise_for_status()
                        
                        # Log successful request
                        elapsed = time.time() - start_time
                        logger.debug(
                            "HTTP request successful",
                            url=url,
                            status_code=response.status_code,
                            elapsed_seconds=elapsed,
                            attempt=attempt.retry_state.attempt_number,
                        )
                        
                        return response
                    
                    except retry_exceptions as e:
                        # Log retry attempt
                        logger.warning(
                            "HTTP request failed, retrying",
                            url=url,
                            error=str(e),
                            attempt=attempt.retry_state.attempt_number,
                            max_attempts=self.retry_attempts,
                        )
                        raise
        
        except RetryError as e:
            # Log final failure
            logger.error(
                "HTTP request failed after all retries",
                url=url,
                error=str(e.last_attempt.exception()),
                attempts=self.retry_attempts,
            )
            raise e.last_attempt.exception()
    
    async def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        follow_redirects: bool = True,
        with_retry: bool = True,
    ) -> httpx.Response:
        """
        Make a POST request to a URL.
        
        Args:
            url: URL to post to
            data: Form data to include in the request
            json: JSON data to include in the request
            headers: Optional headers to include in the request
            timeout: Request timeout in seconds (overrides client default)
            follow_redirects: Whether to follow redirects
            with_retry: Whether to use retry logic
            
        Returns:
            httpx.Response: HTTP response
            
        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        # Merge headers
        request_headers = {**self.default_headers}
        if headers:
            request_headers.update(headers)
        
        # Set timeout
        request_timeout = httpx.Timeout(timeout or self.timeout)
        
        if with_retry:
            return await self._post_with_retry(
                url,
                data,
                json,
                request_headers,
                request_timeout,
                follow_redirects,
            )
        else:
            return await self.client.post(
                url,
                data=data,
                json=json,
                headers=request_headers,
                timeout=request_timeout,
                follow_redirects=follow_redirects,
            )
    
    async def _post_with_retry(
        self,
        url: str,
        data: Optional[Dict[str, Any]],
        json: Optional[Dict[str, Any]],
        headers: Dict[str, str],
        timeout: httpx.Timeout,
        follow_redirects: bool,
    ) -> httpx.Response:
        """
        Make a POST request with retry logic.
        
        Args:
            url: URL to post to
            data: Form data to include in the request
            json: JSON data to include in the request
            headers: Headers to include in the request
            timeout: Request timeout
            follow_redirects: Whether to follow redirects
            
        Returns:
            httpx.Response: HTTP response
            
        Raises:
            httpx.HTTPError: If the HTTP request fails after all retries
        """
        retry_exceptions = (
            httpx.HTTPError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.WriteError,
        )
        
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.retry_attempts),
                wait=wait_exponential(
                    multiplier=self.retry_multiplier,
                    min=self.retry_min_wait,
                    max=self.retry_max_wait,
                ),
                retry=retry_if_exception_type(retry_exceptions),
                reraise=True,
            ):
                with attempt:
                    try:
                        start_time = time.time()
                        response = await self.client.post(
                            url,
                            data=data,
                            json=json,
                            headers=headers,
                            timeout=timeout,
                            follow_redirects=follow_redirects,
                        )
                        response.raise_for_status()
                        
                        # Log successful request
                        elapsed = time.time() - start_time
                        logger.debug(
                            "HTTP request successful",
                            url=url,
                            status_code=response.status_code,
                            elapsed_seconds=elapsed,
                            attempt=attempt.retry_state.attempt_number,
                        )
                        
                        return response
                    
                    except retry_exceptions as e:
                        # Log retry attempt
                        logger.warning(
                            "HTTP request failed, retrying",
                            url=url,
                            error=str(e),
                            attempt=attempt.retry_state.attempt_number,
                            max_attempts=self.retry_attempts,
                        )
                        raise
        
        except RetryError as e:
            # Log final failure
            logger.error(
                "HTTP request failed after all retries",
                url=url,
                error=str(e.last_attempt.exception()),
                attempts=self.retry_attempts,
            )
            raise e.last_attempt.exception()
    
    async def head(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        follow_redirects: bool = True,
        with_retry: bool = True,
    ) -> httpx.Response:
        """
        Make a HEAD request to a URL.
        
        Args:
            url: URL to fetch
            headers: Optional headers to include in the request
            params: Optional query parameters
            timeout: Request timeout in seconds (overrides client default)
            follow_redirects: Whether to follow redirects
            with_retry: Whether to use retry logic
            
        Returns:
            httpx.Response: HTTP response
            
        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        # Merge headers
        request_headers = {**self.default_headers}
        if headers:
            request_headers.update(headers)
        
        # Set timeout
        request_timeout = httpx.Timeout(timeout or self.timeout)
        
        if with_retry:
            # Use a shorter timeout for HEAD requests
            head_timeout = min(request_timeout.read, 5.0)
            request_timeout = httpx.Timeout(head_timeout)
            
            return await self._head_with_retry(
                url,
                request_headers,
                params,
                request_timeout,
                follow_redirects,
            )
        else:
            return await self.client.head(
                url,
                headers=request_headers,
                params=params,
                timeout=request_timeout,
                follow_redirects=follow_redirects,
            )
    
    async def _head_with_retry(
        self,
        url: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]],
        timeout: httpx.Timeout,
        follow_redirects: bool,
    ) -> httpx.Response:
        """
        Make a HEAD request with retry logic.
        
        Args:
            url: URL to fetch
            headers: Headers to include in the request
            params: Query parameters
            timeout: Request timeout
            follow_redirects: Whether to follow redirects
            
        Returns:
            httpx.Response: HTTP response
            
        Raises:
            httpx.HTTPError: If the HTTP request fails after all retries
        """
        retry_exceptions = (
            httpx.HTTPError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.WriteError,
        )
        
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.retry_attempts),
                wait=wait_exponential(
                    multiplier=self.retry_multiplier,
                    min=self.retry_min_wait,
                    max=self.retry_max_wait,
                ),
                retry=retry_if_exception_type(retry_exceptions),
                reraise=True,
            ):
                with attempt:
                    try:
                        start_time = time.time()
                        response = await self.client.head(
                            url,
                            headers=headers,
                            params=params,
                            timeout=timeout,
                            follow_redirects=follow_redirects,
                        )
                        response.raise_for_status()
                        
                        # Log successful request
                        elapsed = time.time() - start_time
                        logger.debug(
                            "HTTP HEAD request successful",
                            url=url,
                            status_code=response.status_code,
                            elapsed_seconds=elapsed,
                            attempt=attempt.retry_state.attempt_number,
                        )
                        
                        return response
                    
                    except retry_exceptions as e:
                        # Log retry attempt
                        logger.warning(
                            "HTTP HEAD request failed, retrying",
                            url=url,
                            error=str(e),
                            attempt=attempt.retry_state.attempt_number,
                            max_attempts=self.retry_attempts,
                        )
                        raise
        
        except RetryError as e:
            # Log final failure
            logger.error(
                "HTTP HEAD request failed after all retries",
                url=url,
                error=str(e.last_attempt.exception()),
                attempts=self.retry_attempts,
            )
            raise e.last_attempt.exception()


async def fetch_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    with_retry: bool = True,
) -> Tuple[bytes, Dict[str, str]]:
    """
    Fetch content from a URL.
    
    This is a standalone function for one-off requests without
    managing an HTTP client instance.
    
    Args:
        url: URL to fetch
        headers: Optional headers to include in the request
        timeout: Request timeout in seconds
        with_retry: Whether to use retry logic
        
    Returns:
        Tuple[bytes, Dict[str, str]]: Content and response headers
        
    Raises:
        httpx.HTTPError: If the HTTP request fails
    """
    # Set up headers
    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        request_headers.update(headers)
    
    async with AsyncHTTPClient(
        timeout=timeout,
        retry_attempts=DEFAULT_RETRY_ATTEMPTS if with_retry else 1,
        default_headers=request_headers,
    ) as client:
        response = await client.get(url, with_retry=with_retry)
        return response.content, dict(response.headers)


async def fetch_with_retry(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    retry_min_wait: float = DEFAULT_RETRY_MIN_WAIT,
    retry_max_wait: float = DEFAULT_RETRY_MAX_WAIT,
) -> httpx.Response:
    """
    Fetch a URL with retry logic for transient errors.
    
    This is a standalone function for one-off requests with retry logic
    without managing an HTTP client instance.
    
    Args:
        url: URL to fetch
        headers: Optional headers to include in the request
        timeout: Request timeout in seconds
        retry_attempts: Maximum number of retry attempts
        retry_min_wait: Minimum wait time between retries in seconds
        retry_max_wait: Maximum wait time between retries in seconds
        
    Returns:
        httpx.Response: HTTP response
        
    Raises:
        httpx.HTTPError: If the HTTP request fails after all retries
    """
    # Set up headers
    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        request_headers.update(headers)
    
    async with AsyncHTTPClient(
        timeout=timeout,
        retry_attempts=retry_attempts,
        retry_min_wait=retry_min_wait,
        retry_max_wait=retry_max_wait,
        default_headers=request_headers,
    ) as client:
        return await client.get(url)


async def check_url_exists(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
) -> bool:
    """
    Check if a URL exists by making a HEAD request.
    
    Args:
        url: URL to check
        headers: Optional headers to include in the request
        timeout: Request timeout in seconds
        
    Returns:
        bool: True if the URL exists, False otherwise
    """
    # Set up headers
    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        request_headers.update(headers)
    
    try:
        async with AsyncHTTPClient(
            timeout=timeout,
            retry_attempts=1,  # Only try once for existence check
            default_headers=request_headers,
        ) as client:
            await client.head(url, with_retry=False)
            return True
    
    except httpx.HTTPError:
        return False


async def get_url_content_type(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
) -> Optional[str]:
    """
    Get the content type of a URL by making a HEAD request.
    
    Args:
        url: URL to check
        headers: Optional headers to include in the request
        timeout: Request timeout in seconds
        
    Returns:
        Optional[str]: Content type if available, None otherwise
    """
    # Set up headers
    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        request_headers.update(headers)
    
    try:
        async with AsyncHTTPClient(
            timeout=timeout,
            retry_attempts=1,  # Only try once for content type check
            default_headers=request_headers,
        ) as client:
            response = await client.head(url, with_retry=False)
            return response.headers.get("content-type")
    
    except httpx.HTTPError:
        return None
