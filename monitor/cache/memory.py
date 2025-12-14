"""
Memory-based cache implementation for the technical blog monitor.

This module provides an in-memory cache client for testing and simple deployments.
It supports TTL-based expiration and periodic cleanup of expired entries.
"""
import asyncio
import time
from typing import Any, Dict, Optional, Set, Tuple

import structlog

from monitor.cache import BaseCacheClient
from monitor.config import CacheConfig

# Set up structured logger
logger = structlog.get_logger()


class MemoryCacheClient(BaseCacheClient):
    """
    In-memory cache client implementation.
    
    This cache client stores data in memory with optional TTL support.
    It periodically cleans up expired entries to prevent memory leaks.
    """

    def __init__(self, config: CacheConfig):
        """
        Initialize the memory cache client.
        
        Args:
            config: Cache configuration
        """
        super().__init__(config)
        # Storage format: {key: (value, expiration_timestamp or None)}
        self._storage: Dict[str, Tuple[Any, Optional[float]]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._closed = False

        # Start cleanup task
        self._start_cleanup_task()

    def _start_cleanup_task(self) -> None:
        """Start the periodic cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            # Ensure the task is properly managed
            self._cleanup_task.add_done_callback(self._cleanup_task_done)

    def _cleanup_task_done(self, task: asyncio.Task) -> None:
        """Handle cleanup task completion."""
        if task.cancelled():
            logger.debug("Memory cache cleanup task cancelled")
        elif task.exception():
            logger.error(
                "Memory cache cleanup task failed with exception",
                error=str(task.exception()),
            )
        else:
            logger.debug("Memory cache cleanup task completed")

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired entries."""
        try:
            while not self._closed:
                # Run cleanup
                await self._cleanup_expired()

                # Wait for next cleanup (every minute)
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass
        except Exception as e:
            logger.exception("Error in memory cache cleanup loop", error=str(e))

    async def _cleanup_expired(self) -> None:
        """Clean up expired entries from the cache."""
        now = time.time()
        keys_to_delete: Set[str] = set()

        # Find expired keys
        async with self._lock:
            for key, (_, expiration) in self._storage.items():
                if expiration is not None and expiration <= now:
                    keys_to_delete.add(key)

            # Delete expired keys
            for key in keys_to_delete:
                del self._storage[key]

        if keys_to_delete:
            logger.debug("Cleaned up expired cache entries", count=len(keys_to_delete))

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            Any: Cached value if found and not expired, None otherwise
        """
        async with self._lock:
            if key not in self._storage:
                return None

            value, expiration = self._storage[key]

            # Check if expired
            if expiration is not None and expiration <= time.time():
                # Remove expired entry
                del self._storage[key]
                return None

            return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a value in the cache with an optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional time to live in seconds
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Calculate expiration timestamp
        expiration = None
        if ttl is not None:
            expiration = time.time() + ttl
        elif self.ttl > 0:
            # Use default TTL if not specified
            expiration = time.time() + self.ttl

        # Store value with expiration
        async with self._lock:
            self._storage[key] = (value, expiration)

        return True

    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if the key existed and was deleted, False otherwise
        """
        async with self._lock:
            if key in self._storage:
                del self._storage[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache and is not expired.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if the key exists and is not expired, False otherwise
        """
        async with self._lock:
            if key not in self._storage:
                return False

            _, expiration = self._storage[key]

            # Check if expired
            if expiration is not None and expiration <= time.time():
                # Remove expired entry
                del self._storage[key]
                return False

            return True

    async def clear(self) -> bool:
        """
        Clear all values from the cache.
        
        Returns:
            bool: True if successful, False otherwise
        """
        async with self._lock:
            self._storage.clear()

        return True

    async def close(self) -> None:
        """Close the cache client and release resources."""
        self._closed = True

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        # Clear storage
        async with self._lock:
            self._storage.clear()

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter in the cache.
        
        Args:
            key: Cache key
            amount: Amount to increment by
            
        Returns:
            Optional[int]: New value if successful, None otherwise
        """
        async with self._lock:
            if key in self._storage:
                value, expiration = self._storage[key]

                # Check if expired
                if expiration is not None and expiration <= time.time():
                    # Remove expired entry
                    del self._storage[key]
                    # Start with 0
                    value = 0

                # Ensure value is a number
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = 0
            else:
                value = 0
                expiration = None

            # Increment value
            value += amount

            # Store updated value
            self._storage[key] = (value, expiration)

            return value

    async def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Decrement a counter in the cache.
        
        Args:
            key: Cache key
            amount: Amount to decrement by
            
        Returns:
            Optional[int]: New value if successful, None otherwise
        """
        async with self._lock:
            if key in self._storage:
                value, expiration = self._storage[key]

                # Check if expired
                if expiration is not None and expiration <= time.time():
                    # Remove expired entry
                    del self._storage[key]
                    # Start with 0
                    value = 0

                # Ensure value is a number
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = 0
            else:
                value = 0
                expiration = None

            # Decrement value (never below 0)
            value = max(0, value - amount)

            # Store updated value
            self._storage[key] = (value, expiration)

            return value

    def __len__(self) -> int:
        """
        Get the number of items in the cache.
        
        Returns:
            int: Number of items in the cache
        """
        return len(self._storage)
