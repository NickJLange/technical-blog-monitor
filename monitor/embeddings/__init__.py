"""
Embeddings package for the technical blog monitor.

This package provides functionality for generating embeddings from text and images,
with support for different embedding models and providers. It handles batching,
caching, and provides a consistent interface for all embedding operations.

The main components are:
- Embedding client interface
- Factory function to get the appropriate client
- Implementations for different embedding providers
"""
import asyncio
import base64
import hashlib
import os
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, Type, Union

import numpy as np
import structlog

from monitor.config import EmbeddingConfig, EmbeddingModelType

# Set up structured logger
logger = structlog.get_logger()


class EmbeddingClient(Protocol):
    """Protocol defining the interface for embedding clients."""
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embeddings for text.
        
        Args:
            text: Text to embed
            
        Returns:
            List[float]: Embedding vector
        """
        ...
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        ...
    
    async def embed_image(self, image_path: str) -> List[float]:
        """
        Generate embeddings for an image.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            List[float]: Embedding vector
        """
        ...
    
    async def embed_images(self, image_paths: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple images.
        
        Args:
            image_paths: List of paths to image files
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        ...
    
    async def close(self) -> None:
        """Close the embedding client and release resources."""
        ...
    
    async def __aenter__(self) -> "EmbeddingClient":
        """Enter the async context manager."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        await self.close()


class BaseEmbeddingClient(ABC):
    """
    Base class for embedding clients.
    
    This class provides common functionality for all embedding clients,
    including batching, caching, and a consistent interface.
    """
    
    def __init__(self, config: EmbeddingConfig):
        """
        Initialize the base embedding client.
        
        Args:
            config: Embedding configuration
        """
        self.config = config
        self.batch_size = config.batch_size
        self._closed = False
    
    async def __aenter__(self) -> "BaseEmbeddingClient":
        """Enter the async context manager."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        await self.close()
    
    async def close(self) -> None:
        """Close the embedding client and release resources."""
        self._closed = True
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embeddings for text.
        
        Args:
            text: Text to embed
            
        Returns:
            List[float]: Embedding vector
        """
        # Single text embedding is just a special case of batch embedding
        result = await self.embed_texts([text])
        return result[0]
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        This method batches the texts according to the configured batch size
        and calls the _embed_text_batch method for each batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        if not texts:
            return []
        
        # Process in batches
        results = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_results = await self._embed_text_batch(batch)
            results.extend(batch_results)
        
        return results
    
    @abstractmethod
    async def _embed_text_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        
        This method must be implemented by subclasses to provide the actual
        embedding functionality.
        
        Args:
            texts: Batch of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        pass
    
    async def embed_image(self, image_path: str) -> List[float]:
        """
        Generate embeddings for an image.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            List[float]: Embedding vector
        """
        # Single image embedding is just a special case of batch embedding
        result = await self.embed_images([image_path])
        return result[0]
    
    async def embed_images(self, image_paths: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple images.
        
        This method batches the images according to the configured batch size
        and calls the _embed_image_batch method for each batch.
        
        Args:
            image_paths: List of paths to image files
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        if not image_paths:
            return []
        
        # Process in batches
        results = []
        for i in range(0, len(image_paths), self.batch_size):
            batch = image_paths[i:i + self.batch_size]
            batch_results = await self._embed_image_batch(batch)
            results.extend(batch_results)
        
        return results
    
    @abstractmethod
    async def _embed_image_batch(self, image_paths: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of images.
        
        This method must be implemented by subclasses to provide the actual
        embedding functionality.
        
        Args:
            image_paths: Batch of paths to image files
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        pass


class DummyEmbeddingClient(BaseEmbeddingClient):
    """
    Dummy embedding client for testing.
    
    This client generates random embedding vectors for testing purposes.
    """
    
    def __init__(self, config: EmbeddingConfig):
        """
        Initialize the dummy embedding client.
        
        Args:
            config: Embedding configuration
        """
        super().__init__(config)
        self.text_dim = config.embedding_dimensions or 1536  # Default to OpenAI dimensions
        self.image_dim = config.image_vector_dimension or 512  # Default to CLIP dimensions
        
        # Seed the random number generator for reproducible embeddings
        self.rng = np.random.RandomState(42)
    
    async def _embed_text_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate dummy embeddings for a batch of texts.
        
        This method generates deterministic random vectors based on the hash of the text.
        
        Args:
            texts: Batch of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        results = []
        
        for text in texts:
            # Generate a deterministic seed from the text
            text_hash = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
            
            # Create a separate random generator for this text
            text_rng = np.random.RandomState(text_hash)
            
            # Generate a random vector
            vector = text_rng.randn(self.text_dim)
            
            # Normalize the vector
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm
            
            # Convert to list of floats
            results.append(vector.tolist())
        
        return results
    
    async def _embed_image_batch(self, image_paths: List[str]) -> List[List[float]]:
        """
        Generate dummy embeddings for a batch of images.
        
        This method generates deterministic random vectors based on the hash of the image path.
        
        Args:
            image_paths: Batch of paths to image files
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        results = []
        
        for path in image_paths:
            # Generate a deterministic seed from the path
            path_hash = int(hashlib.md5(str(path).encode()).hexdigest(), 16) % (2**32)
            
            # Create a separate random generator for this image
            path_rng = np.random.RandomState(path_hash)
            
            # Generate a random vector
            vector = path_rng.randn(self.image_dim)
            
            # Normalize the vector
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm
            
            # Convert to list of floats
            results.append(vector.tolist())
        
        return results


class OpenAIEmbeddingClient(BaseEmbeddingClient):
    """
    OpenAI embedding client.
    
    This client uses the OpenAI API to generate embeddings for text and images.
    """
    
    def __init__(self, config: EmbeddingConfig):
        """
        Initialize the OpenAI embedding client.
        
        Args:
            config: Embedding configuration
        """
        super().__init__(config)
        
        # Import OpenAI here to avoid dependency if not used
        try:
            import openai
            self.openai = openai
            
            # Set up OpenAI client
            if config.openai_api_key:
                self.client = openai.OpenAI(
                    api_key=config.openai_api_key.get_secret_value()
                )
            else:
                raise ValueError("OpenAI API key is required")
            
            # Set model names
            self.text_model = config.text_model_name or "text-embedding-ada-002"
            self.image_model = config.image_model_name
            
            logger.info(
                "OpenAI embedding client initialized",
                text_model=self.text_model,
                image_model=self.image_model,
            )
        
        except ImportError:
            raise ImportError(
                "OpenAI package is required for OpenAIEmbeddingClient. "
                "Install it with 'pip install openai'."
            )
    
    async def _embed_text_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts using OpenAI API.
        
        Args:
            texts: Batch of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        # This is a stub implementation
        # In a real implementation, this would call the OpenAI API
        logger.debug(
            "Generating OpenAI text embeddings",
            model=self.text_model,
            count=len(texts),
        )
        
        # For now, return dummy embeddings
        dummy_client = DummyEmbeddingClient(self.config)
        return await dummy_client._embed_text_batch(texts)
    
    async def _embed_image_batch(self, image_paths: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of images using OpenAI API.
        
        Args:
            image_paths: Batch of paths to image files
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        # This is a stub implementation
        # In a real implementation, this would call the OpenAI API
        logger.debug(
            "Generating OpenAI image embeddings",
            model=self.image_model,
            count=len(image_paths),
        )
        
        # For now, return dummy embeddings
        dummy_client = DummyEmbeddingClient(self.config)
        return await dummy_client._embed_image_batch(image_paths)


class HuggingFaceEmbeddingClient(BaseEmbeddingClient):
    """
    HuggingFace embedding client.
    
    This client uses HuggingFace models to generate embeddings for text and images.
    """
    
    def __init__(self, config: EmbeddingConfig):
        """
        Initialize the HuggingFace embedding client.
        
        Args:
            config: Embedding configuration
        """
        super().__init__(config)
        
        # This is a stub implementation
        # In a real implementation, this would load HuggingFace models
        self.text_model = config.text_model_name or "sentence-transformers/all-MiniLM-L6-v2"
        self.image_model = config.image_model_name
        
        logger.info(
            "HuggingFace embedding client initialized (stub)",
            text_model=self.text_model,
            image_model=self.image_model,
        )
    
    async def _embed_text_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts using HuggingFace models.
        
        Args:
            texts: Batch of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        # This is a stub implementation
        # In a real implementation, this would use HuggingFace models
        logger.debug(
            "Generating HuggingFace text embeddings (stub)",
            model=self.text_model,
            count=len(texts),
        )
        
        # For now, return dummy embeddings
        dummy_client = DummyEmbeddingClient(self.config)
        return await dummy_client._embed_text_batch(texts)
    
    async def _embed_image_batch(self, image_paths: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of images using HuggingFace models.
        
        Args:
            image_paths: Batch of paths to image files
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        # This is a stub implementation
        # In a real implementation, this would use HuggingFace models
        logger.debug(
            "Generating HuggingFace image embeddings (stub)",
            model=self.image_model,
            count=len(image_paths),
        )
        
        # For now, return dummy embeddings
        dummy_client = DummyEmbeddingClient(self.config)
        return await dummy_client._embed_image_batch(image_paths)


async def get_embedding_client(config: EmbeddingConfig) -> EmbeddingClient:
    """
    Get an embedding client based on configuration.
    
    This factory function creates the appropriate embedding client based on
    the provided configuration.
    
    Args:
        config: Embedding configuration
        
    Returns:
        EmbeddingClient: Configured embedding client
        
    Raises:
        ValueError: If the embedding model type is invalid or not supported
    """
    if config.text_model_type == EmbeddingModelType.OPENAI:
        return OpenAIEmbeddingClient(config)
    
    elif config.text_model_type == EmbeddingModelType.HUGGINGFACE:
        return HuggingFaceEmbeddingClient(config)
    
    elif config.text_model_type == EmbeddingModelType.SENTENCE_TRANSFORMERS:
        # For now, treat sentence-transformers as HuggingFace
        return HuggingFaceEmbeddingClient(config)
    
    elif config.text_model_type == EmbeddingModelType.CUSTOM:
        # For custom models, use the dummy client for now
        logger.warning(
            "Custom embedding model type not fully implemented, using dummy client",
            model_name=config.text_model_name,
        )
        return DummyEmbeddingClient(config)
    
    else:
        # Default to dummy client for testing
        logger.info(
            "Using dummy embedding client",
            model_type=config.text_model_type,
        )
        return DummyEmbeddingClient(config)


# Import specific implementations to make them available
__all__ = [
    "EmbeddingClient",
    "BaseEmbeddingClient",
    "DummyEmbeddingClient",
    "OpenAIEmbeddingClient",
    "HuggingFaceEmbeddingClient",
    "get_embedding_client",
]
