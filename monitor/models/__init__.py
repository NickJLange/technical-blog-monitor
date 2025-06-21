"""
Data models for the technical blog monitor.

This module imports and exports all data models used throughout the application.
"""
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, HttpUrl

# Import models from submodules (to be created later)
from monitor.models.article import ArticleContent
from monitor.models.blog_post import BlogPost
from monitor.models.cache_entry import CacheEntry
from monitor.models.embedding import EmbeddingRecord


class ContentType(str, Enum):
    """Types of content that can be processed."""
    BLOG_POST = "blog_post"
    ARTICLE = "article"
    DOCUMENTATION = "documentation"
    RELEASE_NOTES = "release_notes"
    TUTORIAL = "tutorial"
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    """Status of content processing."""
    PENDING = "pending"
    FETCHED = "fetched"
    RENDERED = "rendered"
    EXTRACTED = "extracted"
    EMBEDDED = "embedded"
    STORED = "stored"
    FAILED = "failed"


class BlogPost(BaseModel):
    """Represents a blog post discovered from a feed."""
    id: str
    url: HttpUrl
    title: str
    source: str
    author: Optional[str] = None
    publish_date: Optional[datetime] = None
    updated_date: Optional[datetime] = None
    summary: Optional[str] = None
    content_type: ContentType = ContentType.BLOG_POST
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArticleContent(BaseModel):
    """Represents the extracted content from an article."""
    url: HttpUrl
    title: str
    text: str
    html: str
    author: Optional[str] = None
    publish_date: Optional[datetime] = None
    summary: Optional[str] = None
    word_count: int
    image_urls: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CacheEntry(BaseModel):
    """Represents an entry in the cache."""
    key: str
    value_type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EmbeddingRecord(BaseModel):
    """Represents an embedding record for storage in a vector database."""
    id: str
    url: HttpUrl
    title: str
    publish_date: Optional[datetime] = None
    text_embedding: List[float]
    image_embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ArticleContent",
    "BlogPost",
    "CacheEntry",
    "ContentType",
    "EmbeddingRecord",
    "ProcessingStatus",
]
