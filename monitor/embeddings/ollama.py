"""
Ollama embedding client for the technical blog monitor.

This module provides an async embedding client that uses local Ollama instance
to generate embeddings for text. It supports batch processing, retries, and
follows the project's embedding interface conventions.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from monitor.config import EmbeddingConfig
from monitor.embeddings import BaseEmbeddingClient

# Set up structured logger
logger = structlog.get_logger()


class OllamaEmbeddingClient(BaseEmbeddingClient):
    """
    Async embedding client for a local Ollama instance.
    
    This client connects to Ollama's embedding API to generate text embeddings
    using locally running models like nomic-embed-text.
    
    Endpoint:
      POST {base_url}/api/embeddings
      JSON: {"model": "...", "prompt": "...", "keep_alive": "5m"}
    
    Response:
      {"embedding": [float, ...]}
    """
    
    def __init__(
        self,
        config: EmbeddingConfig,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text:v1.5",
        timeout_seconds: float = 60.0,
        keep_alive: str = "5m",
        max_connections: int = 10,
    ):
        """
        Initialize the Ollama embedding client.
        
        Args:
            config: Embedding configuration
            base_url: Ollama API base URL
            model: Model name to use for embeddings
            timeout_seconds: Request timeout
            keep_alive: How long to keep model in memory
            max_connections: Maximum concurrent connections
        """
        super().__init__(config)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keep_alive = keep_alive
        self.target_dimension = config.embedding_dimensions # Use configured dimension for truncation
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            limits=httpx.Limits(max_connections=max_connections),
        )
        self._dim: Optional[int] = None
        
        logger.info(
            "Ollama embedding client initialized",
            base_url=self.base_url,
            model=self.model,
            batch_size=self.batch_size,
            target_dimension=self.target_dimension,
        )
    
    async def close(self) -> None:
        """Close the embedding client and release resources."""
        await self._client.aclose()
        await super().close()
    
    async def _embed_text_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        
        This method processes texts concurrently while respecting the batch size.
        
        Args:
            texts: Batch of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        logger.debug(
            "Generating Ollama text embeddings",
            count=len(texts),
            model=self.model,
        )
        
        # Process texts concurrently
        tasks = [self._embed_one(text) for text in texts]
        results = await asyncio.gather(*tasks)
        
        # Cache dimension if not already set
        if self._dim is None and results:
            self._dim = len(results[0])
            logger.info(
                "Detected embedding dimension",
                dimension=self._dim,
                model=self.model,
            )
        
        return results
    
    @retry(
        wait=wait_exponential(min=0.5, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def _embed_one(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        This method includes retry logic for transient failures.
        
        Args:
            text: Text to embed
            
        Returns:
            List[float]: Embedding vector
            
        Raises:
            RuntimeError: If the API returns an invalid response
        """
        payload = {
            "model": self.model,
            "prompt": text,
            "keep_alive": self.keep_alive,
        }
        
        url = f"{self.base_url}/api/embeddings"
        
        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            embedding = data.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise RuntimeError(f"Invalid embedding response from Ollama: {data}")
            
            if self.target_dimension and len(embedding) > self.target_dimension:
                logger.debug(
                    "Truncating embedding",
                    original_dimension=len(embedding),
                    target_dimension=self.target_dimension,
                )
                return embedding[:self.target_dimension]
            
            return embedding
            
        except httpx.HTTPError as e:
            logger.error(
                "HTTP error from Ollama",
                url=url,
                model=self.model,
                error=str(e),
                status_code=getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None,
            )
            raise
        except Exception as e:
            logger.error(
                "Error generating Ollama embedding",
                model=self.model,
                error=str(e),
            )
            raise
    
    async def _embed_image_batch(self, image_paths: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of images.
        
        Note: Ollama text embedding models don't support images, so this returns
        dummy embeddings for compatibility.
        
        Args:
            image_paths: Batch of paths to image files
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        logger.warning(
            "Ollama text models don't support image embeddings, returning dummy vectors",
            count=len(image_paths),
        )
        
        # Return dummy embeddings for images
        from monitor.embeddings import DummyEmbeddingClient
        dummy_client = DummyEmbeddingClient(self.config)
        return await dummy_client._embed_image_batch(image_paths)
    
    async def get_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors.
        
        If not already known, generates a test embedding to determine dimension.
        
        Returns:
            int: Embedding dimension
        """
        if self.target_dimension:
            return self.target_dimension
        
        if self._dim is None:
            probe = await self._embed_one("dimension probe")
            self._dim = len(probe)
        return self._dim