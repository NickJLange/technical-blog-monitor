"""
Filesystem-based cache implementation for the technical blog monitor.

This module provides a filesystem cache client for simple deployments without
Redis. It stores cache entries as files on disk with TTL support and periodic
cleanup of expired entries.
"""
import asyncio
import json
import os
import pickle
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, Union
import hashlib
import aiofiles
import aiofiles.os
import structlog

from monitor.cache import BaseCacheClient
from monitor.config import CacheConfig
from monitor.models.cache_entry import CacheEntry, ValueType

# Set up structured logger
logger = structlog.get_logger()


class FilesystemCacheClient(BaseCacheClient):
    """
    Filesystem cache client implementation.
    
    This cache client stores data as files on disk with TTL support and
    periodic cleanup of expired entries. It handles serialization,
    concurrent access, and efficient storage of various data types.
    """
    
    def __init__(self, config: CacheConfig):
        """
        Initialize the filesystem cache client.
        
        Args:
            config: Cache configuration
        """
        super().__init__(config)
        
        # Set up cache directory
        self.cache_dir = Path(config.local_storage_path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up subdirectories for different types of data
        self.data_dir = self.cache_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        self.meta_dir = self.cache_dir / "meta"
        self.meta_dir.mkdir(exist_ok=True)
        
        # File locks for concurrent access
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_lock = asyncio.Lock()  # Lock for accessing the locks dict
        
        # Cleanup task
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
            logger.debug("Filesystem cache cleanup task cancelled")
        elif task.exception():
            logger.error(
                "Filesystem cache cleanup task failed with exception",
                error=str(task.exception()),
            )
        else:
            logger.debug("Filesystem cache cleanup task completed")
    
    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired entries."""
        try:
            while not self._closed:
                # Run cleanup
                await self._cleanup_expired()
                
                # Wait for next cleanup (every 10 minutes)
                await asyncio.sleep(600)
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass
        except Exception as e:
            logger.exception("Error in filesystem cache cleanup loop", error=str(e))
    
    async def _cleanup_expired(self) -> None:
        """Clean up expired entries from the cache."""
        logger.debug("Starting filesystem cache cleanup")
        start_time = time.time()
        deleted_count = 0
        
        try:
            # Scan meta directory for expired entries
            async for meta_path in self._scan_directory(self.meta_dir):
                try:
                    # Read metadata
                    async with aiofiles.open(meta_path, "r") as f:
                        meta_data = json.loads(await f.read())
                    
                    # Check if expired
                    expires_at = meta_data.get("expires_at")
                    if expires_at and expires_at <= time.time():
                        # Get the key from the filename
                        key = Path(meta_path).stem
                        
                        # Delete the entry
                        await self.delete(key)
                        deleted_count += 1
                except Exception as e:
                    logger.warning(
                        "Error processing cache metadata file during cleanup",
                        path=str(meta_path),
                        error=str(e),
                    )
            
            elapsed = time.time() - start_time
            logger.debug(
                "Filesystem cache cleanup completed",
                deleted_count=deleted_count,
                elapsed_seconds=elapsed,
            )
        
        except Exception as e:
            logger.error("Error during filesystem cache cleanup", error=str(e))
    
    async def _scan_directory(self, directory: Path):
        """
        Asynchronously scan a directory for files.
        
        Args:
            directory: Directory to scan
            
        Yields:
            Path: Path to each file in the directory
        """
        for entry in os.scandir(directory):
            if entry.is_file():
                yield Path(entry.path)
    
    def _get_file_path(self, key: str) -> Tuple[Path, Path]:
        """
        Get the file paths for a cache key.
        
        Args:
            key: Cache key
            
        Returns:
            Tuple[Path, Path]: Paths to the data file and metadata file
        """
        # Hash the key to ensure valid filenames
        hashed_key = hashlib.sha256(key.encode()).hexdigest()
        
        # Create paths
        data_path = self.data_dir / hashed_key
        meta_path = self.meta_dir / hashed_key
        
        return data_path, meta_path
    
    async def _get_lock(self, key: str) -> asyncio.Lock:
        """
        Get a lock for a specific key.
        
        Args:
            key: Cache key
            
        Returns:
            asyncio.Lock: Lock for the key
        """
        async with self._lock_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            Any: Cached value if found and not expired, None otherwise
        """
        data_path, meta_path = self._get_file_path(key)
        
        # Get lock for this key
        lock = await self._get_lock(key)
        
        async with lock:
            try:
                # Check if files exist
                if not data_path.exists() or not meta_path.exists():
                    return None
                
                # Check if expired
                try:
                    async with aiofiles.open(meta_path, "r") as f:
                        meta_data = json.loads(await f.read())
                    
                    expires_at = meta_data.get("expires_at")
                    if expires_at and expires_at <= time.time():
                        # Remove expired entry
                        await self._remove_files(data_path, meta_path)
                        return None
                except Exception as e:
                    logger.error(
                        "Error reading cache metadata",
                        key=key,
                        error=str(e),
                    )
                    return None
                
                # Read data file
                try:
                    value_type = meta_data.get("value_type", "pickle")
                    
                    if value_type == "string":
                        async with aiofiles.open(data_path, "r") as f:
                            return await f.read()
                    
                    elif value_type == "json":
                        async with aiofiles.open(data_path, "r") as f:
                            return json.loads(await f.read())
                    
                    elif value_type == "pickle":
                        async with aiofiles.open(data_path, "rb") as f:
                            return pickle.loads(await f.read())  # nosec B301: trusted internal cache
                    
                    elif value_type == "bytes":
                        async with aiofiles.open(data_path, "rb") as f:
                            return await f.read()
                    
                    else:
                        logger.warning(
                            "Unknown value type in cache",
                            key=key,
                            value_type=value_type,
                        )
                        return None
                
                except Exception as e:
                    logger.error(
                        "Error reading cache data",
                        key=key,
                        error=str(e),
                    )
                    return None
            
            except Exception as e:
                logger.error("Error getting value from cache", key=key, error=str(e))
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
        data_path, meta_path = self._get_file_path(key)
        
        # Get lock for this key
        lock = await self._get_lock(key)
        
        async with lock:
            try:
                # Determine value type and serialization method
                if isinstance(value, str):
                    value_type = "string"
                    async with aiofiles.open(data_path, "w") as f:
                        await f.write(value)
                
                elif isinstance(value, (dict, list)):
                    try:
                        # Try to serialize as JSON
                        json_str = json.dumps(value)
                        value_type = "json"
                        async with aiofiles.open(data_path, "w") as f:
                            await f.write(json_str)
                    except (TypeError, ValueError):
                        # Fall back to pickle for non-JSON serializable objects
                        value_type = "pickle"
                        async with aiofiles.open(data_path, "wb") as f:
                            await f.write(pickle.dumps(value))
                
                elif isinstance(value, bytes):
                    value_type = "bytes"
                    async with aiofiles.open(data_path, "wb") as f:
                        await f.write(value)
                
                else:
                    # Use pickle for other types
                    value_type = "pickle"
                    async with aiofiles.open(data_path, "wb") as f:
                        await f.write(pickle.dumps(value))
                
                # Create metadata
                meta_data = {
                    "key": key,
                    "value_type": value_type,
                    "created_at": time.time(),
                }
                
                # Set expiration if TTL is provided
                if ttl is not None:
                    meta_data["expires_at"] = time.time() + ttl
                elif self.ttl > 0:
                    meta_data["expires_at"] = time.time() + self.ttl
                
                # Write metadata
                async with aiofiles.open(meta_path, "w") as f:
                    await f.write(json.dumps(meta_data))
                
                return True
            
            except Exception as e:
                logger.error("Error setting value in cache", key=key, error=str(e))
                
                # Clean up any partial files
                await self._remove_files(data_path, meta_path)
                
                return False
    
    async def _remove_files(self, data_path: Path, meta_path: Path) -> None:
        """
        Remove data and metadata files.
        
        Args:
            data_path: Path to the data file
            meta_path: Path to the metadata file
        """
        try:
            if data_path.exists():
                await aiofiles.os.remove(data_path)
        except Exception as e:
            logger.warning("Error removing data file", path=str(data_path), error=str(e))
        
        try:
            if meta_path.exists():
                await aiofiles.os.remove(meta_path)
        except Exception as e:
            logger.warning("Error removing metadata file", path=str(meta_path), error=str(e))
    
    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if the key existed and was deleted, False otherwise
        """
        data_path, meta_path = self._get_file_path(key)
        
        # Get lock for this key
        lock = await self._get_lock(key)
        
        async with lock:
            existed = data_path.exists() or meta_path.exists()
            
            # Remove files
            await self._remove_files(data_path, meta_path)
            
            # Remove lock if it exists
            async with self._lock_lock:
                if key in self._locks:
                    del self._locks[key]
            
            return existed
    
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache and is not expired.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if the key exists and is not expired, False otherwise
        """
        data_path, meta_path = self._get_file_path(key)
        
        # Get lock for this key
        lock = await self._get_lock(key)
        
        async with lock:
            # Check if files exist
            if not data_path.exists() or not meta_path.exists():
                return False
            
            # Check if expired
            try:
                async with aiofiles.open(meta_path, "r") as f:
                    meta_data = json.loads(await f.read())
                
                expires_at = meta_data.get("expires_at")
                if expires_at and expires_at <= time.time():
                    # Remove expired entry
                    await self._remove_files(data_path, meta_path)
                    return False
                
                return True
            
            except Exception as e:
                logger.error(
                    "Error checking if key exists in cache",
                    key=key,
                    error=str(e),
                )
                return False
    
    async def clear(self) -> bool:
        """
        Clear all values from the cache.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Acquire all locks to prevent concurrent access during clear
            async with self._lock_lock:
                locks = list(self._locks.values())
            
            for lock in locks:
                await lock.acquire()
            
            try:
                # Remove all files in data and meta directories
                shutil.rmtree(self.data_dir)
                shutil.rmtree(self.meta_dir)
                
                # Recreate directories
                self.data_dir.mkdir(exist_ok=True)
                self.meta_dir.mkdir(exist_ok=True)
                
                # Clear locks
                async with self._lock_lock:
                    self._locks.clear()
                
                return True
            
            finally:
                # Release all locks
                for lock in locks:
                    lock.release()
        
        except Exception as e:
            logger.error("Error clearing cache", error=str(e))
            return False
    
    async def close(self) -> None:
        """Close the cache client and release resources."""
        if self._closed:
            return
        
        self._closed = True
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        logger.debug("Filesystem cache client closed")
    
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
        data_path, meta_path = self._get_file_path(key)
        
        # Get lock for this key
        lock = await self._get_lock(key)
        
        async with lock:
            try:
                # Check if files exist
                if not data_path.exists() or not meta_path.exists():
                    return None
                
                # Read metadata
                async with aiofiles.open(meta_path, "r") as f:
                    meta_data = json.loads(await f.read())
                
                # Check if expired
                expires_at = meta_data.get("expires_at")
                if expires_at and expires_at <= time.time():
                    # Remove expired entry
                    await self._remove_files(data_path, meta_path)
                    return None
                
                # Get value
                value = await self.get(key)
                if value is None:
                    return None
                
                # Determine value type
                value_type_str = meta_data.get("value_type", "pickle")
                if value_type_str == "string":
                    value_type = ValueType.STRING
                elif value_type_str == "json":
                    value_type = ValueType.JSON
                elif value_type_str == "bytes":
                    value_type = ValueType.BYTES
                else:
                    value_type = ValueType.PICKLE
                
                # Create cache entry
                entry = CacheEntry(
                    key=key,
                    value_type=value_type,
                    value=value,
                    created_at=datetime.fromtimestamp(
                        meta_data.get("created_at", time.time()),
                        tz=timezone.utc,
                    ),
                )
                
                # Set expiration if available
                if expires_at:
                    entry.expires_at = datetime.fromtimestamp(
                        expires_at,
                        tz=timezone.utc,
                    )
                
                return entry
            
            except Exception as e:
                logger.error(
                    "Error getting cache entry",
                    key=key,
                    error=str(e),
                )
                return None
    
    async def get_ttl(self, key: str) -> Optional[int]:
        """
        Get the remaining TTL for a key.
        
        Args:
            key: Cache key
            
        Returns:
            Optional[int]: Remaining TTL in seconds, -1 if no TTL, None if key doesn't exist
        """
        _, meta_path = self._get_file_path(key)
        
        # Get lock for this key
        lock = await self._get_lock(key)
        
        async with lock:
            try:
                # Check if file exists
                if not meta_path.exists():
                    return None
                
                # Read metadata
                async with aiofiles.open(meta_path, "r") as f:
                    meta_data = json.loads(await f.read())
                
                # Check expiration
                expires_at = meta_data.get("expires_at")
                if expires_at is None:
                    return -1  # No TTL
                
                # Calculate remaining TTL
                remaining = expires_at - time.time()
                if remaining <= 0:
                    # Expired
                    return 0
                
                return int(remaining)
            
            except Exception as e:
                logger.error(
                    "Error getting TTL for key",
                    key=key,
                    error=str(e),
                )
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
        data_path, meta_path = self._get_file_path(key)
        
        # Get lock for this key
        lock = await self._get_lock(key)
        
        async with lock:
            try:
                # Check if files exist
                if not data_path.exists() or not meta_path.exists():
                    return False
                
                # Read metadata
                async with aiofiles.open(meta_path, "r") as f:
                    meta_data = json.loads(await f.read())
                
                # Update expiration
                meta_data["expires_at"] = time.time() + ttl
                
                # Write updated metadata
                async with aiofiles.open(meta_path, "w") as f:
                    await f.write(json.dumps(meta_data))
                
                return True
            
            except Exception as e:
                logger.error(
                    "Error setting TTL for key",
                    key=key,
                    error=str(e),
                )
                return False
