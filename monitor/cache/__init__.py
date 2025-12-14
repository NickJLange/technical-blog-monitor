"""
Cache package for the technical blog monitor.

This package provides caching functionality for storing and retrieving data,
with support for different cache backends (PostgreSQL, Memory).
It handles serialization, TTL management, and provides a consistent interface
for all cache operations.
"""
import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Type, Union

import structlog

from monitor.config import CacheBackend, CacheConfig, VectorDBConfig, VectorDBType
from monitor.models.cache_entry import CacheEntry, ValueType

# Set up structured logger
logger = structlog.get_logger()


class CacheClient(Protocol):
    """Protocol defining the interface for cache clients."""

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Any: Cached value if found, None otherwise
        """
        ...

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
        ...

    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            bool: True if successful, False otherwise
        """
        ...

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache.

        Args:
            key: Cache key

        Returns:
            bool: True if the key exists, False otherwise
        """
        ...

    async def clear(self) -> bool:
        """
        Clear all values from the cache.

        Returns:
            bool: True if successful, False otherwise
        """
        ...

    async def close(self) -> None:
        """Close the cache client and release resources."""
        ...

    async def __aenter__(self) -> "CacheClient":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        await self.close()


class BaseCacheClient(CacheClient):
    """
    Base class for cache clients.

    This class provides common functionality for all cache clients,
    including serialization, TTL management, and a consistent interface.
    """

    def __init__(self, config: CacheConfig):
        """
        Initialize the base cache client.

        Args:
            config: Cache configuration
        """
        self.config = config
        self.ttl = config.cache_ttl_hours * 3600  # Convert hours to seconds

    async def get(self, key: str) -> Optional[Any]:
        """Get value - to be implemented by subclasses."""
        raise NotImplementedError

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value - to be implemented by subclasses."""
        raise NotImplementedError

    async def delete(self, key: str) -> bool:
        """Delete value - to be implemented by subclasses."""
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        """Check existence - to be implemented by subclasses."""
        raise NotImplementedError

    async def clear(self) -> bool:
        """Clear cache - to be implemented by subclasses."""
        raise NotImplementedError

    async def __aenter__(self) -> "BaseCacheClient":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        await self.close()

    async def close(self) -> None:
        """Close the cache client and release resources."""
        pass

    async def get_string(self, key: str) -> Optional[str]:
        """
        Get a string value from the cache.

        Args:
            key: Cache key

        Returns:
            Optional[str]: String value if found, None otherwise
        """
        value = await self.get(key)
        if isinstance(value, str):
            return value
        return None

    async def get_int(self, key: str) -> Optional[int]:
        """
        Get an integer value from the cache.

        Args:
            key: Cache key

        Returns:
            Optional[int]: Integer value if found, None otherwise
        """
        value = await self.get(key)
        if value is not None:
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        return None

    async def get_float(self, key: str) -> Optional[float]:
        """
        Get a float value from the cache.

        Args:
            key: Cache key

        Returns:
            Optional[float]: Float value if found, None otherwise
        """
        value = await self.get(key)
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return None

    async def get_bool(self, key: str) -> Optional[bool]:
        """
        Get a boolean value from the cache.

        Args:
            key: Cache key

        Returns:
            Optional[bool]: Boolean value if found, None otherwise
        """
        value = await self.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "y", "t")
        return None

    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a JSON value from the cache.

        Args:
            key: Cache key

        Returns:
            Optional[Dict[str, Any]]: JSON value if found, None otherwise
        """
        value = await self.get(key)
        if isinstance(value, dict):
            return value
        return None

    async def get_bytes(self, key: str) -> Optional[bytes]:
        """
        Get a binary value from the cache.

        Args:
            key: Cache key

        Returns:
            Optional[bytes]: Binary value if found, None otherwise
        """
        value = await self.get(key)
        if isinstance(value, bytes):
            return value
        return None

    async def set_json(
        self,
        key: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a JSON value in the cache.

        Args:
            key: Cache key
            value: JSON value to cache
            ttl: Optional time to live in seconds

        Returns:
            bool: True if successful, False otherwise
        """
        return await self.set(key, value, ttl)

    async def set_bytes(
        self,
        key: str,
        value: bytes,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a binary value in the cache.

        Args:
            key: Cache key
            value: Binary value to cache
            ttl: Optional time to live in seconds

        Returns:
            bool: True if successful, False otherwise
        """
        return await self.set(key, value, ttl)

    async def set_entry(self, entry: CacheEntry) -> bool:
        """
        Set a cache entry.

        Args:
            entry: Cache entry to set

        Returns:
            bool: True if successful, False otherwise
        """
        # Calculate TTL if expires_at is set
        ttl = None
        if entry.expires_at:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            if entry.expires_at > now:
                ttl = int((entry.expires_at - now).total_seconds())
            else:
                # Already expired
                return False

        return await self.set(entry.key, entry.value, ttl)

    async def get_entry(self, key: str) -> Optional[CacheEntry]:
        """
        Get a cache entry.

        Args:
            key: Cache key

        Returns:
            Optional[CacheEntry]: Cache entry if found, None otherwise
        """
        value = await self.get(key)
        if value is None:
            return None

        # Determine value type
        value_type = ValueType.STRING
        if isinstance(value, dict):
            value_type = ValueType.JSON
        elif isinstance(value, bytes):
            value_type = ValueType.BYTES

        # Create cache entry
        return CacheEntry(
            key=key,
            value_type=value_type,
            value=value,
        )

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter in the cache.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            Optional[int]: New value if successful, None otherwise
        """
        # Default implementation for clients that don't support atomic increment
        value = await self.get_int(key)
        if value is None:
            value = 0

        new_value = value + amount
        success = await self.set(key, new_value)

        return new_value if success else None

    async def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Decrement a counter in the cache.

        Args:
            key: Cache key
            amount: Amount to decrement by

        Returns:
            Optional[int]: New value if successful, None otherwise
        """
        # Default implementation for clients that don't support atomic decrement
        value = await self.get_int(key)
        if value is None:
            value = 0

        new_value = max(0, value - amount)
        success = await self.set(key, new_value)

        return new_value if success else None


async def get_cache_client(
    config: CacheConfig,
    vector_db_config: Optional[VectorDBConfig] = None,
) -> CacheClient:
    """
    Get a cache client based on configuration.

    This factory function creates the appropriate cache client based on
    the provided configuration. When using PostgreSQL for both cache and
    vector storage, they share the same connection pool.

    Args:
        config: Cache configuration
        vector_db_config: Optional vector database configuration. When provided
            and using POSTGRES backend without explicit DSN, falls back to
            the vector DB connection string.

    Returns:
        CacheClient: Configured cache client

    Raises:
        ValueError: If the cache configuration is invalid
    """
    if not config.enabled:
        from monitor.cache.memory import MemoryCacheClient
        logger.info("Using memory cache (caching disabled)")
        return MemoryCacheClient(config)

    if config.backend == CacheBackend.POSTGRES:
        from monitor.cache.postgres import PostgresCacheClient

        dsn = config.postgres_dsn
        if not dsn and vector_db_config and vector_db_config.db_type == VectorDBType.PGVECTOR:
            dsn = vector_db_config.connection_string

        if not dsn:
            raise ValueError(
                "PostgreSQL cache backend requires postgres_dsn or PGVECTOR vector_db config"
            )

        logger.info("Using PostgreSQL cache", dsn=dsn.split("@")[-1] if "@" in dsn else dsn)
        return await PostgresCacheClient.create(config, dsn=dsn)

    if config.backend == CacheBackend.MEMORY:
        from monitor.cache.memory import MemoryCacheClient
        logger.info("Using memory cache")
        return MemoryCacheClient(config)

    # Default to memory cache if backend not recognized or supported
    logger.warning(f"Cache backend '{config.backend}' not supported, falling back to memory cache")
    from monitor.cache.memory import MemoryCacheClient
    return MemoryCacheClient(config)


# Import specific implementations to make them available
from monitor.cache.memory import MemoryCacheClient
from monitor.cache.postgres import PostgresCacheClient

__all__ = [
    "CacheClient",
    "BaseCacheClient",
    "get_cache_client",
    "MemoryCacheClient",
    "PostgresCacheClient",
]
