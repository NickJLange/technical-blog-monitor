"""
Database utilities for the technical blog monitor.

This package provides shared database connection pooling and utilities
for PostgreSQL with pgvector extension.
"""

from monitor.db.postgres_pool import close_pool, get_pool

__all__ = ["get_pool", "close_pool"]
