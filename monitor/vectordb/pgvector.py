"""
pgvector database client for the technical blog monitor.

This module provides an async client for PostgreSQL with pgvector extension,
enabling efficient storage and retrieval of vector embeddings.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import numpy as np
import structlog
from pgvector.asyncpg import register_vector

from monitor.config import VectorDBConfig
from monitor.models.embedding import EmbeddingRecord
from monitor.vectordb import BaseVectorDBClient

# Set up structured logger
logger = structlog.get_logger()


class PgVectorDBClient(BaseVectorDBClient):
    """
    PostgreSQL with pgvector extension database client.
    
    This client uses PostgreSQL's pgvector extension for efficient
    vector similarity search operations.
    """
    
    def __init__(self, config: VectorDBConfig):
        """
        Initialize the pgvector database client.
        
        Args:
            config: Vector database configuration
        """
        super().__init__(config)
        self.connection_string = config.connection_string
        self.pool: Optional[asyncpg.Pool] = None
        self.table_name = f"blog_posts_{config.collection_name}"
        self.text_dimension = config.text_vector_dimension
        self.image_dimension = config.image_vector_dimension
        
        logger.info(
            "pgvector database client initialized",
            connection=self.connection_string,
            table=self.table_name,
            text_dim=self.text_dimension,
        )
    
    async def initialize(self) -> None:
        """Initialize the pgvector database connection and tables."""
        try:
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=2,
                max_size=10,
                command_timeout=self.config.timeout_seconds,
            )
            
            # Register pgvector type
            async with self.pool.acquire() as conn:
                await register_vector(conn)
                
                # Create pgvector extension if not exists
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                
                # Create table for blog posts with vector columns
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id TEXT PRIMARY KEY,
                        url TEXT NOT NULL,
                        title TEXT NOT NULL,
                        source TEXT,
                        author TEXT,
                        publish_date TIMESTAMPTZ,
                        text_embedding vector({self.text_dimension}),
                        image_embedding vector({self.image_dimension or 512}),
                        metadata JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                
                # Create indexes for vector similarity search
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_text_embedding_idx
                    ON {self.table_name} USING ivfflat (text_embedding vector_cosine_ops)
                    WITH (lists = 100)
                """)
                
                if self.image_dimension:
                    await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS {self.table_name}_image_embedding_idx
                        ON {self.table_name} USING ivfflat (image_embedding vector_cosine_ops)
                        WITH (lists = 100)
                    """)
                
                # Create index on publish_date for time-based queries
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_publish_date_idx
                    ON {self.table_name} (publish_date DESC)
                """)
                
                logger.info(
                    "pgvector database initialized",
                    table=self.table_name,
                )
        
        except Exception as e:
            logger.error(
                "Failed to initialize pgvector database",
                error=str(e),
            )
            raise
    
    async def close(self) -> None:
        """Close the pgvector database connection."""
        if self.pool:
            await self.pool.close()
        await super().close()
    
    async def upsert(self, record: EmbeddingRecord) -> bool:
        """
        Insert or update a record in the pgvector database.
        
        Args:
            record: Embedding record to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                # Prepare metadata as JSON
                metadata = record.metadata or {}
                metadata.update({
                    "tags": metadata.get("tags", []),
                    "summary": metadata.get("summary", ""),
                    "word_count": metadata.get("word_count", 0),
                })
                
                # Convert embeddings to PostgreSQL vector format
                text_vec = record.text_embedding if record.text_embedding else None
                image_vec = record.image_embedding if record.image_embedding else None
                
                # Upsert the record
                await conn.execute(f"""
                    INSERT INTO {self.table_name} (
                        id, url, title, source, author, publish_date,
                        text_embedding, image_embedding, metadata, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        url = EXCLUDED.url,
                        title = EXCLUDED.title,
                        source = EXCLUDED.source,
                        author = EXCLUDED.author,
                        publish_date = EXCLUDED.publish_date,
                        text_embedding = EXCLUDED.text_embedding,
                        image_embedding = EXCLUDED.image_embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """,
                    record.id,
                    str(record.url),
                    record.title,
                    metadata.get("source", "Unknown"),
                    metadata.get("author"),
                    record.publish_date,
                    text_vec,
                    image_vec,
                    json.dumps(metadata)
                )
                
                logger.debug(
                    "Upserted record in pgvector",
                    id=record.id,
                    title=record.title,
                )
                return True
        
        except Exception as e:
            logger.error(
                "Error upserting record in pgvector",
                id=record.id,
                error=str(e),
            )
            return False
    
    async def _upsert_batch(self, records: List[EmbeddingRecord]) -> bool:
        """
        Insert or update a batch of records in the pgvector database.
        
        Args:
            records: Batch of embedding records to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                # Prepare batch data
                values = []
                for record in records:
                    metadata = record.metadata or {}
                    metadata.update({
                        "tags": metadata.get("tags", []),
                        "summary": metadata.get("summary", ""),
                        "word_count": metadata.get("word_count", 0),
                    })
                    
                    values.append((
                        record.id,
                        str(record.url),
                        record.title,
                        metadata.get("source", "Unknown"),
                        metadata.get("author"),
                        record.publish_date,
                        record.text_embedding,
                        record.image_embedding,
                        json.dumps(metadata)
                    ))
                
                # Batch upsert
                await conn.executemany(f"""
                    INSERT INTO {self.table_name} (
                        id, url, title, source, author, publish_date,
                        text_embedding, image_embedding, metadata, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        url = EXCLUDED.url,
                        title = EXCLUDED.title,
                        source = EXCLUDED.source,
                        author = EXCLUDED.author,
                        publish_date = EXCLUDED.publish_date,
                        text_embedding = EXCLUDED.text_embedding,
                        image_embedding = EXCLUDED.image_embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, values)
                
                logger.debug(
                    "Upserted batch of records in pgvector",
                    count=len(records),
                )
                return True
        
        except Exception as e:
            logger.error(
                "Error upserting batch in pgvector",
                count=len(records),
                error=str(e),
            )
            return False
    
    async def get(self, id: str) -> Optional[EmbeddingRecord]:
        """
        Get a record from the pgvector database by ID.
        
        Args:
            id: Record ID
            
        Returns:
            Optional[EmbeddingRecord]: Record if found, None otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(f"""
                    SELECT id, url, title, source, author, publish_date,
                           text_embedding, image_embedding, metadata
                    FROM {self.table_name}
                    WHERE id = $1
                """, id)
                
                if row:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    return EmbeddingRecord(
                        id=row["id"],
                        url=row["url"],
                        title=row["title"],
                        publish_date=row["publish_date"],
                        text_embedding=row["text_embedding"].tolist() if row["text_embedding"] else None,
                        image_embedding=row["image_embedding"].tolist() if row["image_embedding"] else None,
                        metadata=metadata
                    )
                return None
        
        except Exception as e:
            logger.error(
                "Error getting record from pgvector",
                id=id,
                error=str(e),
            )
            return None
    
    async def get_by_id(self, id: str) -> Optional[EmbeddingRecord]:
        """Alias for get() to match web dashboard expectations."""
        return await self.get(id)
    
    async def delete(self, id: str) -> bool:
        """
        Delete a record from the pgvector database.
        
        Args:
            id: Record ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(f"""
                    DELETE FROM {self.table_name}
                    WHERE id = $1
                """, id)
                
                return result.split()[-1] != "0"
        
        except Exception as e:
            logger.error(
                "Error deleting record from pgvector",
                id=id,
                error=str(e),
            )
            return False
    
    async def search_by_text(
        self,
        text_embedding: List[float],
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Tuple[EmbeddingRecord, float]]:
        """
        Search for records by text embedding similarity.
        
        Args:
            text_embedding: Text embedding vector
            limit: Maximum number of results
            min_score: Minimum similarity score
            
        Returns:
            List[Tuple[EmbeddingRecord, float]]: List of records and scores
        """
        try:
            async with self.pool.acquire() as conn:
                # Use cosine similarity (1 - cosine distance)
                rows = await conn.fetch(f"""
                    SELECT id, url, title, source, author, publish_date,
                           text_embedding, image_embedding, metadata,
                           1 - (text_embedding <=> $1::vector) AS score
                    FROM {self.table_name}
                    WHERE text_embedding IS NOT NULL
                    AND 1 - (text_embedding <=> $1::vector) >= $2
                    ORDER BY text_embedding <=> $1::vector
                    LIMIT $3
                """, text_embedding, min_score, limit)
                
                results = []
                for row in rows:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    record = EmbeddingRecord(
                        id=row["id"],
                        url=row["url"],
                        title=row["title"],
                        publish_date=row["publish_date"],
                        text_embedding=row["text_embedding"].tolist() if row["text_embedding"] else None,
                        image_embedding=row["image_embedding"].tolist() if row["image_embedding"] else None,
                        metadata=metadata
                    )
                    results.append((record, row["score"]))
                
                return results
        
        except Exception as e:
            logger.error(
                "Error searching by text in pgvector",
                error=str(e),
            )
            return []
    
    async def search_by_image(
        self,
        image_embedding: List[float],
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Tuple[EmbeddingRecord, float]]:
        """
        Search for records by image embedding similarity.
        
        Args:
            image_embedding: Image embedding vector
            limit: Maximum number of results
            min_score: Minimum similarity score
            
        Returns:
            List[Tuple[EmbeddingRecord, float]]: List of records and scores
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(f"""
                    SELECT id, url, title, source, author, publish_date,
                           text_embedding, image_embedding, metadata,
                           1 - (image_embedding <=> $1::vector) AS score
                    FROM {self.table_name}
                    WHERE image_embedding IS NOT NULL
                    AND 1 - (image_embedding <=> $1::vector) >= $2
                    ORDER BY image_embedding <=> $1::vector
                    LIMIT $3
                """, image_embedding, min_score, limit)
                
                results = []
                for row in rows:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    record = EmbeddingRecord(
                        id=row["id"],
                        url=row["url"],
                        title=row["title"],
                        publish_date=row["publish_date"],
                        text_embedding=row["text_embedding"].tolist() if row["text_embedding"] else None,
                        image_embedding=row["image_embedding"].tolist() if row["image_embedding"] else None,
                        metadata=metadata
                    )
                    results.append((record, row["score"]))
                
                return results
        
        except Exception as e:
            logger.error(
                "Error searching by image in pgvector",
                error=str(e),
            )
            return []
    
    async def search_hybrid(
        self,
        text_embedding: List[float],
        image_embedding: Optional[List[float]] = None,
        text_weight: float = 0.5,
        image_weight: float = 0.5,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Tuple[EmbeddingRecord, float]]:
        """
        Search for records using both text and image embeddings.
        
        Args:
            text_embedding: Text embedding vector
            image_embedding: Optional image embedding vector
            text_weight: Weight for text similarity (0.0 to 1.0)
            image_weight: Weight for image similarity (0.0 to 1.0)
            limit: Maximum number of results
            min_score: Minimum combined similarity score
            
        Returns:
            List[Tuple[EmbeddingRecord, float]]: List of records and scores
        """
        if not image_embedding:
            return await self.search_by_text(text_embedding, limit, min_score)
        
        try:
            async with self.pool.acquire() as conn:
                # Hybrid search with weighted combination
                rows = await conn.fetch(f"""
                    SELECT id, url, title, source, author, publish_date,
                           text_embedding, image_embedding, metadata,
                           (
                               {text_weight} * (1 - (text_embedding <=> $1::vector)) +
                               {image_weight} * (1 - (image_embedding <=> $2::vector))
                           ) AS score
                    FROM {self.table_name}
                    WHERE text_embedding IS NOT NULL
                    ORDER BY score DESC
                    LIMIT $3
                """, text_embedding, image_embedding, limit)
                
                results = []
                for row in rows:
                    if row["score"] >= min_score:
                        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                        record = EmbeddingRecord(
                            id=row["id"],
                            url=row["url"],
                            title=row["title"],
                            publish_date=row["publish_date"],
                            text_embedding=row["text_embedding"].tolist() if row["text_embedding"] else None,
                            image_embedding=row["image_embedding"].tolist() if row["image_embedding"] else None,
                            metadata=metadata
                        )
                        results.append((record, row["score"]))
                
                return results
        
        except Exception as e:
            logger.error(
                "Error in hybrid search in pgvector",
                error=str(e),
            )
            return []
    
    async def count(self) -> int:
        """
        Count the number of records in the pgvector database.
        
        Returns:
            int: Number of records
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(f"SELECT COUNT(*) FROM {self.table_name}")
                return row["count"]
        
        except Exception as e:
            logger.error(
                "Error counting records in pgvector",
                error=str(e),
            )
            return 0
    
    async def list_all(self, limit: int = 1000) -> List[EmbeddingRecord]:
        """
        List all records in the database.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List[EmbeddingRecord]: List of records
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(f"""
                    SELECT id, url, title, source, author, publish_date,
                           text_embedding, image_embedding, metadata
                    FROM {self.table_name}
                    ORDER BY publish_date DESC NULLS LAST
                    LIMIT $1
                """, limit)
                
                records = []
                for row in rows:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    # Merge source and author into metadata
                    metadata["source"] = row["source"]
                    metadata["author"] = row["author"]
                    
                    record = EmbeddingRecord(
                        id=row["id"],
                        url=row["url"],
                        title=row["title"],
                        publish_date=row["publish_date"],
                        text_embedding=row["text_embedding"].tolist() if row["text_embedding"] else None,
                        image_embedding=row["image_embedding"].tolist() if row["image_embedding"] else None,
                        metadata=metadata
                    )
                    records.append(record)
                
                return records
        
        except Exception as e:
            logger.error(
                "Error listing all records from pgvector",
                error=str(e),
            )
            return []
    
    async def clear(self) -> bool:
        """
        Clear all records from the pgvector database.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(f"TRUNCATE TABLE {self.table_name}")
                
                logger.info(
                    "Cleared all records from pgvector",
                    table=self.table_name,
                )
                return True
        
        except Exception as e:
            logger.error(
                "Error clearing records from pgvector",
                error=str(e),
            )
            return False