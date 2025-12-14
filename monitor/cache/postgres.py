"""
PostgreSQL-based cache implementation for the technical blog monitor.

This module provides a PostgreSQL cache client that can share a connection pool
with the pgvector database client, enabling unified PostgreSQL storage for both
caching and vector embeddings.
"""
import json
import pickle
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg
import structlog

from monitor.cache import BaseCacheClient
from monitor.config import CacheConfig
from monitor.db.postgres_pool import get_pool
from monitor.models.cache_entry import CacheEntry, ValueType

logger = structlog.get_logger()


class PostgresCacheClient(BaseCacheClient):
    """
    PostgreSQL cache client implementation.

    This cache client stores data in PostgreSQL with TTL support via
    an expires_at timestamp. It shares the connection pool with the
    pgvector client when both use the same DSN.
    """

    def __init__(self, config: CacheConfig, dsn: str):
        """
        Initialize the PostgreSQL cache client.

        Args:
            config: Cache configuration
            dsn: PostgreSQL connection string
        """
        super().__init__(config)
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None
        self.prefix = "tbm:"
        self._closed = False

    @classmethod
    async def create(cls, config: CacheConfig, dsn: str) -> "PostgresCacheClient":
        """
        Create a new PostgreSQL cache client.

        This factory method gets a shared connection pool and ensures
        the cache table exists.

        Args:
            config: Cache configuration
            dsn: PostgreSQL connection string

        Returns:
            PostgresCacheClient: Configured PostgreSQL cache client
        """
        client = cls(config, dsn)
        client.pool = await get_pool(
            dsn,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )

        async with client.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key         TEXT PRIMARY KEY,
                    value       BYTEA NOT NULL,
                    expires_at  TIMESTAMPTZ NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS cache_entries_expires_at_idx
                ON cache_entries (expires_at)
                WHERE expires_at IS NOT NULL
            """)

        safe_dsn = dsn.split("@")[-1] if "@" in dsn else dsn
        logger.info("PostgreSQL cache client initialized", dsn=safe_dsn)
        return client

    def _prefix_key(self, key: str) -> str:
        """Add prefix to a key for namespacing."""
        return f"{self.prefix}{key}"

    async def close(self) -> None:
        """Close the cache client (pool is shared, so we don't close it)."""
        self._closed = True

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Any: Cached value if found and not expired, None otherwise
        """
        prefixed_key = self._prefix_key(key)
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT value
                    FROM cache_entries
                    WHERE key = $1
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    prefixed_key,
                )

            if not row:
                return None

            return await self._deserialize(row["value"])

        except Exception as e:
            logger.error("PostgreSQL cache get failed", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
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
        prefixed_key = self._prefix_key(key)
        if not self.pool:
            return False

        try:
            serialized_value = await self._serialize(value)

            if ttl is None and self.ttl > 0:
                ttl = self.ttl

            expires_at = None
            if ttl and ttl > 0:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cache_entries (key, value, expires_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = NOW()
                    """,
                    prefixed_key,
                    serialized_value,
                    expires_at,
                )

            return True

        except Exception as e:
            logger.error("PostgreSQL cache set failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            bool: True if the key existed and was deleted, False otherwise
        """
        prefixed_key = self._prefix_key(key)
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM cache_entries WHERE key = $1",
                    prefixed_key,
                )
            deleted = int(result.split()[-1])
            return deleted > 0

        except Exception as e:
            logger.error("PostgreSQL cache delete failed", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache.

        Args:
            key: Cache key

        Returns:
            bool: True if the key exists and is not expired, False otherwise
        """
        prefixed_key = self._prefix_key(key)
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT 1
                    FROM cache_entries
                    WHERE key = $1
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    prefixed_key,
                )
            return row is not None

        except Exception as e:
            logger.error("PostgreSQL cache exists failed", key=key, error=str(e))
            return False

    async def clear(self) -> bool:
        """
        Clear all values from the cache with the current prefix.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM cache_entries WHERE key LIKE $1",
                    f"{self.prefix}%",
                )
            return True

        except Exception as e:
            logger.error("PostgreSQL cache clear failed", error=str(e))
            return False

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter in the cache.

        Uses non-atomic get+set for simplicity. For strict atomicity,
        consider using a separate counters table.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            Optional[int]: New value if successful, None otherwise
        """
        return await super().increment(key, amount)

    async def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Decrement a counter in the cache.

        Args:
            key: Cache key
            amount: Amount to decrement by

        Returns:
            Optional[int]: New value if successful, None otherwise
        """
        return await super().decrement(key, amount)

    async def get_ttl(self, key: str) -> Optional[int]:
        """
        Get the remaining TTL for a key.

        Args:
            key: Cache key

        Returns:
            Optional[int]: Remaining TTL in seconds, -1 if no TTL, None if key doesn't exist
        """
        prefixed_key = self._prefix_key(key)
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT expires_at
                    FROM cache_entries
                    WHERE key = $1
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    prefixed_key,
                )

            if not row:
                return None

            if row["expires_at"] is None:
                return -1

            remaining = (row["expires_at"] - datetime.now(timezone.utc)).total_seconds()
            return max(0, int(remaining))

        except Exception as e:
            logger.error("PostgreSQL cache get_ttl failed", key=key, error=str(e))
            return None

    async def set_ttl(self, key: str, ttl: int) -> bool:
        """
        Set the TTL for a key.

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            bool: True if successful, False otherwise
        """
        prefixed_key = self._prefix_key(key)
        if not self.pool:
            return False

        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE cache_entries
                    SET expires_at = $2, updated_at = NOW()
                    WHERE key = $1
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    prefixed_key,
                    expires_at,
                )

            updated = int(result.split()[-1])
            return updated > 0

        except Exception as e:
            logger.error("PostgreSQL cache set_ttl failed", key=key, error=str(e))
            return False

    async def get_multiple(self, keys: List[str]) -> Dict[str, Any]:
        """
        Get multiple values from the cache.

        Args:
            keys: List of cache keys

        Returns:
            Dict[str, Any]: Dictionary of key-value pairs for found keys
        """
        if not keys or not self.pool:
            return {}

        prefixed_keys = [self._prefix_key(key) for key in keys]

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT key, value
                    FROM cache_entries
                    WHERE key = ANY($1)
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    prefixed_keys,
                )

            result = {}
            prefix_len = len(self.prefix)
            for row in rows:
                original_key = row["key"][prefix_len:]
                try:
                    result[original_key] = await self._deserialize(row["value"])
                except Exception as e:
                    logger.error(
                        "Error deserializing cached value",
                        key=original_key,
                        error=str(e),
                    )

            return result

        except Exception as e:
            logger.error("PostgreSQL cache get_multiple failed", error=str(e))
            return {}

    async def set_multiple(
        self,
        items: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set multiple values in the cache.

        Args:
            items: Dictionary of key-value pairs to cache
            ttl: Optional time to live in seconds

        Returns:
            bool: True if all operations were successful, False otherwise
        """
        if not items or not self.pool:
            return True if not items else False

        if ttl is None and self.ttl > 0:
            ttl = self.ttl

        expires_at = None
        if ttl and ttl > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        try:
            values = []
            for key, value in items.items():
                prefixed_key = self._prefix_key(key)
                serialized = await self._serialize(value)
                values.append((prefixed_key, serialized, expires_at))

            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO cache_entries (key, value, expires_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = NOW()
                    """,
                    values,
                )

            return True

        except Exception as e:
            logger.error("PostgreSQL cache set_multiple failed", error=str(e))
            return False

    async def delete_multiple(self, keys: List[str]) -> int:
        """
        Delete multiple values from the cache.

        Args:
            keys: List of cache keys to delete

        Returns:
            int: Number of keys that were deleted
        """
        if not keys or not self.pool:
            return 0

        prefixed_keys = [self._prefix_key(key) for key in keys]

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM cache_entries WHERE key = ANY($1)",
                    prefixed_keys,
                )

            return int(result.split()[-1])

        except Exception as e:
            logger.error("PostgreSQL cache delete_multiple failed", error=str(e))
            return 0

    async def set_entry(self, entry: CacheEntry) -> bool:
        """
        Set a cache entry.

        Args:
            entry: Cache entry to set

        Returns:
            bool: True if successful, False otherwise
        """
        ttl = None
        if entry.expires_at:
            now = datetime.now(timezone.utc)
            if entry.expires_at > now:
                ttl = int((entry.expires_at - now).total_seconds())
            else:
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
        prefixed_key = self._prefix_key(key)
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT value, expires_at
                    FROM cache_entries
                    WHERE key = $1
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    prefixed_key,
                )

            if not row:
                return None

            value = await self._deserialize(row["value"])

            value_type = ValueType.STRING
            if isinstance(value, dict):
                value_type = ValueType.JSON
            elif isinstance(value, bytes):
                value_type = ValueType.BYTES

            return CacheEntry(
                key=key,
                value_type=value_type,
                value=value,
                expires_at=row["expires_at"],
            )

        except Exception as e:
            logger.error("PostgreSQL cache get_entry failed", key=key, error=str(e))
            return None

    async def cleanup_expired(self) -> int:
        """
        Remove expired entries from the cache.

        This should be called periodically to keep the table size bounded.

        Returns:
            int: Number of entries removed
        """
        if not self.pool:
            return 0

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM cache_entries
                    WHERE expires_at IS NOT NULL
                      AND expires_at <= NOW()
                    """
                )

            deleted = int(result.split()[-1])
            if deleted > 0:
                logger.info("Cleaned up expired cache entries", count=deleted)
            return deleted

        except Exception as e:
            logger.error("PostgreSQL cache cleanup failed", error=str(e))
            return 0

    async def _serialize(self, value: Any) -> bytes:
        """
        Serialize a value for storage.

        Args:
            value: Value to serialize

        Returns:
            bytes: Serialized value
        """
        if value is None:
            return b"null"

        if isinstance(value, (str, int, float, bool)):
            return json.dumps(value).encode("utf-8")

        if isinstance(value, bytes):
            return value

        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value).encode("utf-8")
            except (TypeError, ValueError):
                return pickle.dumps(value)

        return pickle.dumps(value)

    async def _deserialize(self, data: bytes) -> Any:
        """
        Deserialize a value from storage.

        Args:
            data: Serialized value

        Returns:
            Any: Deserialized value
        """
        if not data:
            return None

        if data == b"null":
            return None

        try:
            return json.loads(data)
        except json.JSONDecodeError:
            try:
                return pickle.loads(data)  # nosec B301: trusted internal cache
            except pickle.PickleError:
                return data
