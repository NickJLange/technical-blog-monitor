"""
Redis-based cache implementation for the technical blog monitor.

This module provides a Redis cache client with connection pooling,
serialization, and error handling. It supports TTL-based expiration,
atomic operations, and efficient storage of various data types.
"""
import asyncio
import json
import pickle
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set, Tuple, Union

import structlog
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError

from monitor.cache import BaseCacheClient
from monitor.config import CacheConfig
from monitor.models.cache_entry import CacheEntry, ValueType

# Set up structured logger
logger = structlog.get_logger()


class RedisCacheClient(BaseCacheClient):
    """
    Redis cache client implementation.
    
    This cache client stores data in Redis with connection pooling,
    serialization, and error handling. It supports TTL-based expiration
    and atomic operations.
    """
    
    def __init__(
        self,
        config: CacheConfig,
        redis_client: Redis,
        connection_pool: ConnectionPool,
    ):
        """
        Initialize the Redis cache client.
        
        Args:
            config: Cache configuration
            redis_client: Redis client instance
            connection_pool: Redis connection pool
        """
        super().__init__(config)
        self.redis = redis_client
        self.connection_pool = connection_pool
        self.prefix = "tbm:"  # Technical Blog Monitor prefix for keys
        self._closed = False
    
    @classmethod
    async def create(cls, config: CacheConfig) -> "RedisCacheClient":
        """
        Create a new Redis cache client.
        
        This factory method creates a Redis client with connection pooling
        and returns a configured RedisCacheClient instance.
        
        Args:
            config: Cache configuration
            
        Returns:
            RedisCacheClient: Configured Redis cache client
            
        Raises:
            ValueError: If the Redis URL is invalid
        """
        if not config.redis_url:
            raise ValueError("Redis URL is required")
        
        # Create connection pool
        connection_kwargs = {}
        if config.redis_password:
            connection_kwargs["password"] = config.redis_password.get_secret_value()
        
        try:
            connection_pool = ConnectionPool.from_url(
                config.redis_url,
                **connection_kwargs
            )
            
            # Create Redis client
            redis_client = Redis(connection_pool=connection_pool)
            
            # Test connection
            await redis_client.ping()
            
            return cls(config, redis_client, connection_pool)
        
        except RedisError as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise ValueError(f"Failed to connect to Redis: {str(e)}") from e
    
    def _prefix_key(self, key: str) -> str:
        """
        Add prefix to a key.
        
        Args:
            key: Original key
            
        Returns:
            str: Prefixed key
        """
        return f"{self.prefix}{key}"
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            Any: Cached value if found, None otherwise
        """
        prefixed_key = self._prefix_key(key)
        
        try:
            # Get value from Redis
            value = await self.redis.get(prefixed_key)
            
            if value is None:
                return None
            
            # Try to deserialize the value
            return await self._deserialize(value)
        
        except RedisError as e:
            logger.error("Redis error in get operation", key=key, error=str(e))
            return None
        except Exception as e:
            logger.error("Error deserializing cached value", key=key, error=str(e))
            return None
    
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
        prefixed_key = self._prefix_key(key)
        
        try:
            # Serialize the value
            serialized_value = await self._serialize(value)
            
            # Determine TTL
            if ttl is None and self.ttl > 0:
                ttl = self.ttl
            
            # Set value in Redis
            if ttl:
                await self.redis.setex(prefixed_key, ttl, serialized_value)
            else:
                await self.redis.set(prefixed_key, serialized_value)
            
            return True
        
        except RedisError as e:
            logger.error("Redis error in set operation", key=key, error=str(e))
            return False
        except Exception as e:
            logger.error("Error serializing value for cache", key=key, error=str(e))
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
        
        try:
            # Delete key from Redis
            result = await self.redis.delete(prefixed_key)
            return result > 0
        
        except RedisError as e:
            logger.error("Redis error in delete operation", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if the key exists, False otherwise
        """
        prefixed_key = self._prefix_key(key)
        
        try:
            # Check if key exists in Redis
            return await self.redis.exists(prefixed_key) > 0
        
        except RedisError as e:
            logger.error("Redis error in exists operation", key=key, error=str(e))
            return False
    
    async def clear(self) -> bool:
        """
        Clear all values from the cache with the current prefix.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Find all keys with the current prefix
            pattern = f"{self.prefix}*"
            cursor = b"0"
            keys_to_delete = []
            
            # Scan for keys in batches
            while cursor:
                cursor, keys = await self.redis.scan(
                    cursor=cursor, 
                    match=pattern,
                    count=1000
                )
                
                if keys:
                    keys_to_delete.extend(keys)
                
                # Convert string cursor to bytes if needed
                if isinstance(cursor, str):
                    cursor = cursor.encode()
                
                # Exit if we've reached the end
                if cursor == b"0":
                    break
            
            # Delete all found keys
            if keys_to_delete:
                await self.redis.delete(*keys_to_delete)
            
            return True
        
        except RedisError as e:
            logger.error("Redis error in clear operation", error=str(e))
            return False
    
    async def close(self) -> None:
        """Close the Redis client and release resources."""
        if self._closed:
            return
        
        self._closed = True
        
        try:
            # Close Redis client
            await self.redis.close()
            
            # Close connection pool
            self.connection_pool.disconnect()
            
            logger.debug("Redis cache client closed")
        
        except RedisError as e:
            logger.error("Error closing Redis client", error=str(e))
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter in the cache.
        
        Args:
            key: Cache key
            amount: Amount to increment by
            
        Returns:
            Optional[int]: New value if successful, None otherwise
        """
        prefixed_key = self._prefix_key(key)
        
        try:
            # Use Redis INCRBY for atomic increment
            value = await self.redis.incrby(prefixed_key, amount)
            
            # Apply TTL if not already set
            if not await self.redis.ttl(prefixed_key) > 0 and self.ttl > 0:
                await self.redis.expire(prefixed_key, self.ttl)
            
            return value
        
        except RedisError as e:
            logger.error("Redis error in increment operation", key=key, error=str(e))
            return None
    
    async def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Decrement a counter in the cache.
        
        Args:
            key: Cache key
            amount: Amount to decrement by
            
        Returns:
            Optional[int]: New value if successful, None otherwise
        """
        prefixed_key = self._prefix_key(key)
        
        try:
            # Use Redis DECRBY for atomic decrement
            value = await self.redis.decrby(prefixed_key, amount)
            
            # Ensure value is not negative
            if value < 0:
                await self.redis.set(prefixed_key, 0)
                value = 0
            
            # Apply TTL if not already set
            if not await self.redis.ttl(prefixed_key) > 0 and self.ttl > 0:
                await self.redis.expire(prefixed_key, self.ttl)
            
            return value
        
        except RedisError as e:
            logger.error("Redis error in decrement operation", key=key, error=str(e))
            return None
    
    async def set_entry(self, entry: CacheEntry) -> bool:
        """
        Set a cache entry.
        
        Args:
            entry: Cache entry to set
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Serialize the entry
        try:
            serialized_entry = entry.serialize()
            
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
            
            # Set in Redis
            prefixed_key = self._prefix_key(entry.key)
            
            if ttl:
                await self.redis.setex(prefixed_key, ttl, serialized_entry)
            else:
                await self.redis.set(prefixed_key, serialized_entry)
            
            return True
        
        except Exception as e:
            logger.error("Error setting cache entry", key=entry.key, error=str(e))
            return False
    
    async def get_entry(self, key: str) -> Optional[CacheEntry]:
        """
        Get a cache entry.
        
        Args:
            key: Cache key
            
        Returns:
            Optional[CacheEntry]: Cache entry if found, None otherwise
        """
        prefixed_key = self._prefix_key(key)
        
        try:
            # Get from Redis
            data = await self.redis.get(prefixed_key)
            if not data:
                return None
            
            # Deserialize the entry
            return CacheEntry.deserialize(data)
        
        except Exception as e:
            logger.error("Error getting cache entry", key=key, error=str(e))
            return None
    
    async def _serialize(self, value: Any) -> bytes:
        """
        Serialize a value for storage in Redis.
        
        Args:
            value: Value to serialize
            
        Returns:
            bytes: Serialized value
            
        Raises:
            ValueError: If the value cannot be serialized
        """
        if value is None:
            return b"null"
        
        if isinstance(value, (str, int, float, bool)):
            # Simple types can be JSON serialized
            return json.dumps(value).encode("utf-8")
        
        if isinstance(value, bytes):
            # Binary data
            return value
        
        if isinstance(value, (dict, list)):
            # Complex types can be JSON serialized
            try:
                return json.dumps(value).encode("utf-8")
            except (TypeError, ValueError):
                # Fall back to pickle for non-JSON serializable objects
                return pickle.dumps(value)
        
        # Use pickle for other types
        return pickle.dumps(value)
    
    async def _deserialize(self, data: bytes) -> Any:
        """
        Deserialize a value from Redis storage.
        
        Args:
            data: Serialized value
            
        Returns:
            Any: Deserialized value
            
        Raises:
            ValueError: If the value cannot be deserialized
        """
        if not data:
            return None
        
        if data == b"null":
            return None
        
        # Try JSON first
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            # Not JSON, try pickle
            try:
                return pickle.loads(data)  # nosec B301: trusted internal cache
            except pickle.PickleError:
                # Not pickle, return as bytes
                return data
    
    async def get_ttl(self, key: str) -> Optional[int]:
        """
        Get the remaining TTL for a key.
        
        Args:
            key: Cache key
            
        Returns:
            Optional[int]: Remaining TTL in seconds, -1 if no TTL, None if key doesn't exist
        """
        prefixed_key = self._prefix_key(key)
        
        try:
            ttl = await self.redis.ttl(prefixed_key)
            return ttl if ttl != -2 else None  # -2 means key doesn't exist
        
        except RedisError as e:
            logger.error("Redis error in get_ttl operation", key=key, error=str(e))
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
        
        try:
            # Check if key exists
            if not await self.redis.exists(prefixed_key):
                return False
            
            # Set TTL
            return await self.redis.expire(prefixed_key, ttl)
        
        except RedisError as e:
            logger.error("Redis error in set_ttl operation", key=key, error=str(e))
            return False
    
    async def get_multiple(self, keys: list[str]) -> Dict[str, Any]:
        """
        Get multiple values from the cache.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Dict[str, Any]: Dictionary of key-value pairs for found keys
        """
        if not keys:
            return {}
        
        # Prefix all keys
        prefixed_keys = [self._prefix_key(key) for key in keys]
        
        try:
            # Use Redis MGET for efficient multi-get
            values = await self.redis.mget(prefixed_keys)
            
            # Create result dictionary
            result = {}
            for i, value in enumerate(values):
                if value is not None:
                    # Deserialize the value
                    try:
                        deserialized = await self._deserialize(value)
                        result[keys[i]] = deserialized
                    except Exception as e:
                        logger.error(
                            "Error deserializing cached value",
                            key=keys[i],
                            error=str(e)
                        )
            
            return result
        
        except RedisError as e:
            logger.error("Redis error in get_multiple operation", error=str(e))
            return {}
    
    async def set_multiple(
        self,
        items: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set multiple values in the cache.
        
        Args:
            items: Dictionary of key-value pairs to cache
            ttl: Optional time to live in seconds
            
        Returns:
            bool: True if all operations were successful, False otherwise
        """
        if not items:
            return True
        
        # Determine TTL
        if ttl is None and self.ttl > 0:
            ttl = self.ttl
        
        try:
            # Serialize all values and prepare for Redis
            pipeline = self.redis.pipeline()
            
            for key, value in items.items():
                prefixed_key = self._prefix_key(key)
                try:
                    serialized = await self._serialize(value)
                    
                    if ttl:
                        pipeline.setex(prefixed_key, ttl, serialized)
                    else:
                        pipeline.set(prefixed_key, serialized)
                
                except Exception as e:
                    logger.error(
                        "Error serializing value for cache",
                        key=key,
                        error=str(e)
                    )
                    return False
            
            # Execute all commands in the pipeline
            await pipeline.execute()
            return True
        
        except RedisError as e:
            logger.error("Redis error in set_multiple operation", error=str(e))
            return False
    
    async def delete_multiple(self, keys: list[str]) -> int:
        """
        Delete multiple values from the cache.
        
        Args:
            keys: List of cache keys to delete
            
        Returns:
            int: Number of keys that were deleted
        """
        if not keys:
            return 0
        
        # Prefix all keys
        prefixed_keys = [self._prefix_key(key) for key in keys]
        
        try:
            # Use Redis DEL for efficient multi-delete
            return await self.redis.delete(*prefixed_keys)
        
        except RedisError as e:
            logger.error("Redis error in delete_multiple operation", error=str(e))
            return 0
