"""
Vector database package for the technical blog monitor.

This package provides functionality for storing and retrieving vector embeddings,
with support for different vector database backends. It handles serialization,
indexing, and provides a consistent interface for all vector database operations.

The main components are:
- Vector database client interface
- Factory function to get the appropriate client
- Implementations for different vector database backends
"""
import asyncio
import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, Type, Union

import numpy as np
import structlog

from monitor.config import VectorDBConfig, VectorDBType
from monitor.models.embedding import EmbeddingRecord

# Set up structured logger
logger = structlog.get_logger()


class VectorDBClient(Protocol):
    """Protocol defining the interface for vector database clients."""
    
    async def initialize(self) -> None:
        """
        Initialize the vector database client.
        
        This method creates collections, indexes, and other resources
        needed by the vector database.
        """
        ...
    
    async def upsert(self, record: EmbeddingRecord) -> bool:
        """
        Insert or update a record in the vector database.
        
        Args:
            record: Embedding record to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        ...
    
    async def upsert_batch(self, records: List[EmbeddingRecord]) -> bool:
        """
        Insert or update multiple records in the vector database.
        
        Args:
            records: List of embedding records to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        ...
    
    async def get(self, id: str) -> Optional[EmbeddingRecord]:
        """
        Get a record from the vector database by ID.
        
        Args:
            id: Record ID
            
        Returns:
            Optional[EmbeddingRecord]: Record if found, None otherwise
        """
        ...
    
    async def delete(self, id: str) -> bool:
        """
        Delete a record from the vector database.
        
        Args:
            id: Record ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        ...
    
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
        ...
    
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
        ...
    
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
        ...
    
    async def count(self) -> int:
        """
        Count the number of records in the vector database.
        
        Returns:
            int: Number of records
        """
        ...
    
    async def clear(self) -> bool:
        """
        Clear all records from the vector database.
        
        Returns:
            bool: True if successful, False otherwise
        """
        ...
    
    async def close(self) -> None:
        """Close the vector database client and release resources."""
        ...
    
    async def __aenter__(self) -> "VectorDBClient":
        """Enter the async context manager."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        await self.close()


class BaseVectorDBClient(ABC):
    """
    Base class for vector database clients.
    
    This class provides common functionality for all vector database clients,
    including batching, serialization, and a consistent interface.
    """
    
    def __init__(self, config: VectorDBConfig):
        """
        Initialize the base vector database client.
        
        Args:
            config: Vector database configuration
        """
        self.config = config
        self.collection_name = config.collection_name
        self.batch_size = config.batch_size
        self._closed = False
    
    async def __aenter__(self) -> "BaseVectorDBClient":
        """Enter the async context manager."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        await self.close()
    
    async def initialize(self) -> None:
        """
        Initialize the vector database client.
        
        This method creates collections, indexes, and other resources
        needed by the vector database.
        """
        pass
    
    async def close(self) -> None:
        """Close the vector database client and release resources."""
        self._closed = True
    
    async def upsert_batch(self, records: List[EmbeddingRecord]) -> bool:
        """
        Insert or update multiple records in the vector database.
        
        This method batches the records according to the configured batch size
        and calls the _upsert_batch method for each batch.
        
        Args:
            records: List of embedding records to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not records:
            return True
        
        # Process in batches
        success = True
        for i in range(0, len(records), self.batch_size):
            batch = records[i:i + self.batch_size]
            batch_success = await self._upsert_batch(batch)
            success = success and batch_success
        
        return success
    
    @abstractmethod
    async def _upsert_batch(self, records: List[EmbeddingRecord]) -> bool:
        """
        Insert or update a batch of records in the vector database.
        
        This method must be implemented by subclasses to provide the actual
        upsert functionality.
        
        Args:
            records: Batch of embedding records to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            float: Cosine similarity (-1.0 to 1.0)
        """
        if len(vec1) != len(vec2):
            raise ValueError("Vector dimensions do not match")
        
        # Convert to numpy arrays for efficient calculation
        a = np.array(vec1)
        b = np.array(vec2)
        
        # Calculate cosine similarity
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    
    @staticmethod
    def euclidean_distance(vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate Euclidean distance between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            float: Euclidean distance (0.0 to inf)
        """
        if len(vec1) != len(vec2):
            raise ValueError("Vector dimensions do not match")
        
        # Convert to numpy arrays for efficient calculation
        a = np.array(vec1)
        b = np.array(vec2)
        
        # Calculate Euclidean distance
        return np.linalg.norm(a - b)
    
    @staticmethod
    def dot_product(vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate dot product between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            float: Dot product
        """
        if len(vec1) != len(vec2):
            raise ValueError("Vector dimensions do not match")
        
        # Convert to numpy arrays for efficient calculation
        a = np.array(vec1)
        b = np.array(vec2)
        
        # Calculate dot product
        return np.dot(a, b)


class InMemoryVectorDBClient(BaseVectorDBClient):
    """
    In-memory vector database client for testing.
    
    This client stores vectors in memory and provides basic search functionality.
    It is useful for testing and development, but not suitable for production.
    """
    
    def __init__(self, config: VectorDBConfig):
        """
        Initialize the in-memory vector database client.
        
        Args:
            config: Vector database configuration
        """
        super().__init__(config)
        self.records: Dict[str, EmbeddingRecord] = {}
        self.distance_metric = config.distance_metric
    
    async def initialize(self) -> None:
        """Initialize the in-memory vector database."""
        logger.info(
            "Initializing in-memory vector database",
            collection=self.collection_name,
        )
    
    async def upsert(self, record: EmbeddingRecord) -> bool:
        """
        Insert or update a record in the in-memory vector database.
        
        Args:
            record: Embedding record to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.records[record.id] = record
            return True
        except Exception as e:
            logger.error(
                "Error upserting record",
                id=record.id,
                error=str(e),
            )
            return False
    
    async def _upsert_batch(self, records: List[EmbeddingRecord]) -> bool:
        """
        Insert or update a batch of records in the in-memory vector database.
        
        Args:
            records: Batch of embedding records to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            for record in records:
                self.records[record.id] = record
            return True
        except Exception as e:
            logger.error(
                "Error upserting batch of records",
                count=len(records),
                error=str(e),
            )
            return False
    
    async def get(self, id: str) -> Optional[EmbeddingRecord]:
        """
        Get a record from the in-memory vector database by ID.
        
        Args:
            id: Record ID
            
        Returns:
            Optional[EmbeddingRecord]: Record if found, None otherwise
        """
        return self.records.get(id)
    
    async def delete(self, id: str) -> bool:
        """
        Delete a record from the in-memory vector database.
        
        Args:
            id: Record ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        if id in self.records:
            del self.records[id]
            return True
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
        results = []
        
        for record in self.records.values():
            if not record.text_embedding:
                continue
            
            # Calculate similarity score
            score = 0.0
            if self.distance_metric == "cosine":
                score = self.cosine_similarity(text_embedding, record.text_embedding)
            elif self.distance_metric == "euclidean":
                # Convert distance to similarity score (1.0 / (1.0 + distance))
                distance = self.euclidean_distance(text_embedding, record.text_embedding)
                score = 1.0 / (1.0 + distance)
            elif self.distance_metric == "dot":
                score = self.dot_product(text_embedding, record.text_embedding)
            
            # Add to results if score is above threshold
            if score >= min_score:
                results.append((record, score))
        
        # Sort by score (descending) and limit results
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
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
        results = []
        
        for record in self.records.values():
            if not record.image_embedding:
                continue
            
            # Calculate similarity score
            score = 0.0
            if self.distance_metric == "cosine":
                score = self.cosine_similarity(image_embedding, record.image_embedding)
            elif self.distance_metric == "euclidean":
                # Convert distance to similarity score (1.0 / (1.0 + distance))
                distance = self.euclidean_distance(image_embedding, record.image_embedding)
                score = 1.0 / (1.0 + distance)
            elif self.distance_metric == "dot":
                score = self.dot_product(image_embedding, record.image_embedding)
            
            # Add to results if score is above threshold
            if score >= min_score:
                results.append((record, score))
        
        # Sort by score (descending) and limit results
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
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
        # If no image embedding, just do text search
        if not image_embedding:
            return await self.search_by_text(text_embedding, limit, min_score)
        
        results = []
        
        for record in self.records.values():
            if not record.text_embedding:
                continue
            
            # Calculate text similarity score
            text_score = 0.0
            if self.distance_metric == "cosine":
                text_score = self.cosine_similarity(text_embedding, record.text_embedding)
            elif self.distance_metric == "euclidean":
                distance = self.euclidean_distance(text_embedding, record.text_embedding)
                text_score = 1.0 / (1.0 + distance)
            elif self.distance_metric == "dot":
                text_score = self.dot_product(text_embedding, record.text_embedding)
            
            # Calculate image similarity score if available
            image_score = 0.0
            if record.image_embedding and image_embedding:
                if self.distance_metric == "cosine":
                    image_score = self.cosine_similarity(image_embedding, record.image_embedding)
                elif self.distance_metric == "euclidean":
                    distance = self.euclidean_distance(image_embedding, record.image_embedding)
                    image_score = 1.0 / (1.0 + distance)
                elif self.distance_metric == "dot":
                    image_score = self.dot_product(image_embedding, record.image_embedding)
            
            # Calculate combined score
            combined_score = (text_score * text_weight) + (image_score * image_weight)
            
            # Add to results if score is above threshold
            if combined_score >= min_score:
                results.append((record, combined_score))
        
        # Sort by score (descending) and limit results
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    async def count(self) -> int:
        """
        Count the number of records in the in-memory vector database.
        
        Returns:
            int: Number of records
        """
        return len(self.records)
    
    async def clear(self) -> bool:
        """
        Clear all records from the in-memory vector database.
        
        Returns:
            bool: True if successful, False otherwise
        """
        self.records.clear()
        return True


class QdrantVectorDBClient(BaseVectorDBClient):
    """
    Qdrant vector database client.
    
    This client uses the Qdrant vector database for storing and searching embeddings.
    """
    
    def __init__(self, config: VectorDBConfig):
        """
        Initialize the Qdrant vector database client.
        
        Args:
            config: Vector database configuration
        """
        super().__init__(config)
        
        # This is a stub implementation
        # In a real implementation, this would connect to Qdrant
        logger.info(
            "Qdrant vector database client initialized (stub)",
            connection=config.connection_string,
            collection=config.collection_name,
        )
    
    async def initialize(self) -> None:
        """Initialize the Qdrant vector database."""
        # This is a stub implementation
        logger.info(
            "Initializing Qdrant vector database (stub)",
            collection=self.collection_name,
        )
    
    async def upsert(self, record: EmbeddingRecord) -> bool:
        """
        Insert or update a record in the Qdrant vector database.
        
        Args:
            record: Embedding record to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        # This is a stub implementation
        logger.debug(
            "Upserting record in Qdrant (stub)",
            id=record.id,
            title=record.title,
        )
        return True
    
    async def _upsert_batch(self, records: List[EmbeddingRecord]) -> bool:
        """
        Insert or update a batch of records in the Qdrant vector database.
        
        Args:
            records: Batch of embedding records to insert or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        # This is a stub implementation
        logger.debug(
            "Upserting batch of records in Qdrant (stub)",
            count=len(records),
        )
        return True
    
    async def get(self, id: str) -> Optional[EmbeddingRecord]:
        """
        Get a record from the Qdrant vector database by ID.
        
        Args:
            id: Record ID
            
        Returns:
            Optional[EmbeddingRecord]: Record if found, None otherwise
        """
        # This is a stub implementation
        logger.debug(
            "Getting record from Qdrant (stub)",
            id=id,
        )
        return None
    
    async def delete(self, id: str) -> bool:
        """
        Delete a record from the Qdrant vector database.
        
        Args:
            id: Record ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        # This is a stub implementation
        logger.debug(
            "Deleting record from Qdrant (stub)",
            id=id,
        )
        return True
    
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
        # This is a stub implementation
        logger.debug(
            "Searching by text embedding in Qdrant (stub)",
            limit=limit,
            min_score=min_score,
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
        # This is a stub implementation
        logger.debug(
            "Searching by image embedding in Qdrant (stub)",
            limit=limit,
            min_score=min_score,
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
        # This is a stub implementation
        logger.debug(
            "Searching by hybrid embeddings in Qdrant (stub)",
            text_weight=text_weight,
            image_weight=image_weight,
            limit=limit,
            min_score=min_score,
        )
        return []
    
    async def count(self) -> int:
        """
        Count the number of records in the Qdrant vector database.
        
        Returns:
            int: Number of records
        """
        # This is a stub implementation
        return 0
    
    async def clear(self) -> bool:
        """
        Clear all records from the Qdrant vector database.
        
        Returns:
            bool: True if successful, False otherwise
        """
        # This is a stub implementation
        logger.debug(
            "Clearing all records from Qdrant (stub)",
            collection=self.collection_name,
        )
        return True


class ChromaVectorDBClient(BaseVectorDBClient):
    """
    Chroma vector database client.
    
    This client uses the Chroma vector database for storing and searching embeddings.
    """
    
    def __init__(self, config: VectorDBConfig):
        """
        Initialize the Chroma vector database client.
        
        Args:
            config: Vector database configuration
        """
        super().__init__(config)
        
        # This is a stub implementation
        # In a real implementation, this would connect to Chroma
        logger.info(
            "Chroma vector database client initialized (stub)",
            connection=config.connection_string,
            collection=config.collection_name,
        )
    
    # Implement abstract methods with stub implementations
    # Similar to QdrantVectorDBClient
    
    async def initialize(self) -> None:
        """Initialize the Chroma vector database."""
        # Stub implementation
        logger.info(
            "Initializing Chroma vector database (stub)",
            collection=self.collection_name,
        )
    
    async def upsert(self, record: EmbeddingRecord) -> bool:
        """Stub implementation for upsert."""
        return True
    
    async def _upsert_batch(self, records: List[EmbeddingRecord]) -> bool:
        """Stub implementation for batch upsert."""
        return True
    
    async def get(self, id: str) -> Optional[EmbeddingRecord]:
        """Stub implementation for get."""
        return None
    
    async def delete(self, id: str) -> bool:
        """Stub implementation for delete."""
        return True
    
    async def search_by_text(
        self,
        text_embedding: List[float],
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Tuple[EmbeddingRecord, float]]:
        """Stub implementation for text search."""
        return []
    
    async def search_by_image(
        self,
        image_embedding: List[float],
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Tuple[EmbeddingRecord, float]]:
        """Stub implementation for image search."""
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
        """Stub implementation for hybrid search."""
        return []
    
    async def count(self) -> int:
        """Stub implementation for count."""
        return 0
    
    async def clear(self) -> bool:
        """Stub implementation for clear."""
        return True


async def get_vector_db_client(config: VectorDBConfig) -> VectorDBClient:
    """
    Get a vector database client based on configuration.
    
    This factory function creates the appropriate vector database client based on
    the provided configuration.
    
    Args:
        config: Vector database configuration
        
    Returns:
        VectorDBClient: Configured vector database client
        
    Raises:
        ValueError: If the vector database type is invalid or not supported
    """
    if config.db_type == VectorDBType.QDRANT:
        client = QdrantVectorDBClient(config)
    
    elif config.db_type == VectorDBType.CHROMA:
        client = ChromaVectorDBClient(config)
    
    elif config.db_type == VectorDBType.PINECONE:
        # Stub implementation for Pinecone
        logger.warning(
            "Pinecone vector database not fully implemented, using in-memory client",
        )
        client = InMemoryVectorDBClient(config)
    
    elif config.db_type == VectorDBType.MILVUS:
        # Stub implementation for Milvus
        logger.warning(
            "Milvus vector database not fully implemented, using in-memory client",
        )
        client = InMemoryVectorDBClient(config)
    
    elif config.db_type == VectorDBType.WEAVIATE:
        # Stub implementation for Weaviate
        logger.warning(
            "Weaviate vector database not fully implemented, using in-memory client",
        )
        client = InMemoryVectorDBClient(config)
    
    else:
        # Default to in-memory client for testing
        logger.info(
            "Using in-memory vector database client",
            db_type=config.db_type,
        )
        client = InMemoryVectorDBClient(config)
    
    # Initialize the client
    await client.initialize()
    
    return client


# Import specific implementations to make them available
__all__ = [
    "VectorDBClient",
    "BaseVectorDBClient",
    "InMemoryVectorDBClient",
    "QdrantVectorDBClient",
    "ChromaVectorDBClient",
    "get_vector_db_client",
]
