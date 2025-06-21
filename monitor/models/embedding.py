"""
EmbeddingRecord model for representing vector embeddings of content.

This module defines the EmbeddingRecord model with validation and utility methods
for working with embeddings throughout the monitoring pipeline and for storage
in vector databases.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator
from pydantic.alias_generators import to_camel


class EmbeddingRecord(BaseModel):
    """
    Represents an embedding record for storage in a vector database.
    
    This model contains both text and optional image embeddings along with
    metadata about the source content, embedding process, and storage information.
    It supports operations needed for vector database integration.
    """
    # Core identity fields
    id: str
    url: HttpUrl
    title: str
    
    # Embedding vectors
    text_embedding: List[float]
    image_embedding: Optional[List[float]] = None
    
    # Source information
    source: Optional[str] = None
    author: Optional[str] = None
    publish_date: Optional[datetime] = None
    content_snippet: Optional[str] = None
    
    # Embedding metadata
    text_model_id: Optional[str] = None
    image_model_id: Optional[str] = None
    embedding_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    embedding_version: str = "1.0"
    
    # Storage for additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Vector database specific fields
    collection_name: Optional[str] = None
    vector_db_id: Optional[str] = None
    
    @field_validator("publish_date", mode="before")
    @classmethod
    def ensure_timezone(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Ensure all datetime fields have timezone information."""
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
    
    @field_validator("text_embedding", "image_embedding")
    @classmethod
    def validate_embedding_dimensions(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        """Validate embedding dimensions and values."""
        if v is None:
            return None
            
        # Check that embeddings are not empty
        if len(v) == 0:
            raise ValueError("Embedding vector cannot be empty")
            
        # Check that embeddings contain valid float values
        for val in v:
            if not isinstance(val, (int, float)) or np.isnan(val) or np.isinf(val):
                raise ValueError(f"Invalid embedding value: {val}")
                
        return v
    
    @model_validator(mode='after')
    def validate_model_consistency(self) -> 'EmbeddingRecord':
        """Validate that model fields are consistent."""
        # Ensure we have at least one embedding
        if not self.text_embedding and not self.image_embedding:
            raise ValueError("At least one of text_embedding or image_embedding must be provided")
            
        return self
    
    def get_text_vector_dimension(self) -> int:
        """Get the dimension of the text embedding vector."""
        if self.text_embedding:
            return len(self.text_embedding)
        return 0
    
    def get_image_vector_dimension(self) -> int:
        """Get the dimension of the image embedding vector."""
        if self.image_embedding:
            return len(self.image_embedding)
        return 0
    
    def to_vector_db_payload(self) -> Dict[str, Any]:
        """
        Convert the embedding record to a payload suitable for vector database storage.
        
        The exact format may vary depending on the vector database being used.
        """
        payload = {
            "id": self.id,
            "vectors": {
                "text": self.text_embedding
            },
            "payload": {
                "url": str(self.url),
                "title": self.title,
                "source": self.source,
                "author": self.author,
                "publish_date": self.publish_date.isoformat() if self.publish_date else None,
                "content_snippet": self.content_snippet,
                "embedding_created_at": self.embedding_created_at.isoformat(),
                "embedding_version": self.embedding_version,
            }
        }
        
        # Add image embedding if available
        if self.image_embedding:
            payload["vectors"]["image"] = self.image_embedding
            
        # Add all metadata
        if self.metadata:
            payload["payload"]["metadata"] = self.metadata
            
        return payload
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the embedding record to a dictionary with camelCase keys."""
        return self.model_dump(by_alias=True, mode='json')
    
    def to_cache_key(self) -> str:
        """Generate a cache key for this embedding record."""
        return f"embedding:{self.id}"
    
    def get_similarity_score(self, other: 'EmbeddingRecord', mode: str = "text") -> float:
        """
        Calculate cosine similarity between this embedding and another.
        
        Args:
            other: Another EmbeddingRecord to compare with
            mode: Which embedding to use ('text', 'image', or 'combined')
            
        Returns:
            float: Cosine similarity score (-1 to 1, higher is more similar)
        """
        if mode == "text" and self.text_embedding and other.text_embedding:
            return self._cosine_similarity(self.text_embedding, other.text_embedding)
        elif mode == "image" and self.image_embedding and other.image_embedding:
            return self._cosine_similarity(self.image_embedding, other.image_embedding)
        elif mode == "combined":
            # Average of text and image similarity if both are available
            scores = []
            if self.text_embedding and other.text_embedding:
                scores.append(self._cosine_similarity(self.text_embedding, other.text_embedding))
            if self.image_embedding and other.image_embedding:
                scores.append(self._cosine_similarity(self.image_embedding, other.image_embedding))
            if scores:
                return sum(scores) / len(scores)
        return 0.0
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
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
    
    @classmethod
    def from_text_embedding(
        cls,
        id: str,
        url: HttpUrl,
        title: str,
        text_embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> 'EmbeddingRecord':
        """
        Create an EmbeddingRecord from a text embedding.
        
        Args:
            id: Unique identifier for the record
            url: URL of the source content
            title: Title of the source content
            text_embedding: Text embedding vector
            metadata: Additional metadata
            **kwargs: Additional fields to include
            
        Returns:
            EmbeddingRecord: A new embedding record
        """
        return cls(
            id=id,
            url=url,
            title=title,
            text_embedding=text_embedding,
            metadata=metadata or {},
            **kwargs
        )
    
    @classmethod
    def from_dual_embeddings(
        cls,
        id: str,
        url: HttpUrl,
        title: str,
        text_embedding: List[float],
        image_embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> 'EmbeddingRecord':
        """
        Create an EmbeddingRecord from both text and image embeddings.
        
        Args:
            id: Unique identifier for the record
            url: URL of the source content
            title: Title of the source content
            text_embedding: Text embedding vector
            image_embedding: Image embedding vector
            metadata: Additional metadata
            **kwargs: Additional fields to include
            
        Returns:
            EmbeddingRecord: A new embedding record with both embeddings
        """
        return cls(
            id=id,
            url=url,
            title=title,
            text_embedding=text_embedding,
            image_embedding=image_embedding,
            metadata=metadata or {},
            **kwargs
        )
    
    class Config:
        """Pydantic configuration for the EmbeddingRecord model."""
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            HttpUrl: str,
            np.ndarray: lambda arr: arr.tolist(),
        }
        populate_by_name = True
        validate_assignment = True
