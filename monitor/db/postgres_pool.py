"""
Shared PostgreSQL connection pool for the technical blog monitor.

This module provides a singleton asyncpg connection pool that can be shared
between the vector database client and the cache client when both use PostgreSQL.
"""
import asyncio
from typing import Dict, Optional

import asyncpg
import structlog

logger = structlog.get_logger()

_pools: Dict[str, asyncpg.Pool] = {}
_pool_lock = asyncio.Lock()


async def get_pool(
    dsn: str,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: int = 30,
) -> asyncpg.Pool:
    """
    Get or create a shared asyncpg connection pool for a given DSN.

    Multiple calls with the same DSN will return the same pool instance.

    Args:
        dsn: PostgreSQL connection string
        min_size: Minimum number of connections in the pool
        max_size: Maximum number of connections in the pool
        command_timeout: Default timeout for commands in seconds

    Returns:
        asyncpg.Pool: Shared connection pool
    """
    global _pools

    if dsn in _pools:
        return _pools[dsn]

    async with _pool_lock:
        if dsn not in _pools:
            logger.info(
                "Creating PostgreSQL connection pool",
                dsn=dsn.split("@")[-1] if "@" in dsn else dsn,
                min_size=min_size,
                max_size=max_size,
            )
            _pools[dsn] = await asyncpg.create_pool(
                dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=command_timeout,
            )
        return _pools[dsn]


async def close_pool(dsn: Optional[str] = None) -> None:
    """
    Close the PostgreSQL connection pool(s).

    Args:
        dsn: Specific DSN to close. If None, closes all pools.
    """
    global _pools

    if dsn is not None:
        if dsn in _pools:
            safe_dsn = dsn.split("@")[-1] if "@" in dsn else dsn
            logger.info("Closing PostgreSQL connection pool", dsn=safe_dsn)
            await _pools[dsn].close()
            del _pools[dsn]
    else:
        for pool_dsn, pool in list(_pools.items()):
            safe_dsn = pool_dsn.split("@")[-1] if "@" in pool_dsn else pool_dsn
            logger.info("Closing PostgreSQL connection pool", dsn=safe_dsn)
            await pool.close()
        _pools.clear()
