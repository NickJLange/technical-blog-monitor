"""
ArticleContent model for representing extracted content from articles.

This module defines the ArticleContent model with validation and utility methods
for working with extracted article content throughout the monitoring pipeline.
"""
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator
from pydantic.alias_generators import to_camel

from monitor.models.content_type import ContentType


class ArticleContent(BaseModel):
    """
    Represents the extracted content from an article.
    
    This model contains both the raw HTML and processed text content,
    along with metadata extracted from the article such as author,
    publication date, and embedded media references.
    """
    url: HttpUrl
    title: str
    text: str  # Plain text content
    html: str  # Raw HTML content
    author: Optional[str] = None
    publish_date: Optional[datetime] = None
    summary: Optional[str] = None
    word_count: int
    image_urls: List[str] = Field(default_factory=list)
    # Local filesystem paths to screenshots (full-page or key sections) captured
    # when the article was rendered in a headless browser.  Multiple screenshots
    # are supported to accommodate very long articles.
    screenshot_paths: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields for content analysis
    content_type: ContentType = ContentType.ARTICLE
    reading_time_minutes: Optional[float] = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    language: Optional[str] = None
    
    @field_validator("publish_date", mode="before")
    @classmethod
    def ensure_timezone(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Ensure all datetime fields have timezone information."""
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
    
    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: List[str]) -> List[str]:
        """Normalize tags by removing duplicates and empty tags."""
        # Convert to set to remove duplicates, then back to list
        return sorted(list(set(tag.strip().lower() for tag in v if tag.strip())))
    
    @field_validator("image_urls")
    @classmethod
    def normalize_image_urls(cls, v: List[str]) -> List[str]:
        """Normalize image URLs and remove duplicates."""
        # Remove empty URLs and duplicates
        return list(set(url.strip() for url in v if url.strip()))
    
    @field_validator("screenshot_paths")
    @classmethod
    def normalize_screenshot_paths(cls, v: List[str]) -> List[str]:
        """Normalize screenshot paths and remove duplicates / empties."""
        return sorted({path.strip() for path in v if path.strip()})
    
    @model_validator(mode='after')
    def calculate_reading_time(self) -> 'ArticleContent':
        """Calculate the estimated reading time in minutes if not provided."""
        if self.reading_time_minutes is None and self.word_count > 0:
            # Average reading speed is about 200-250 words per minute
            # Using 225 as a middle ground
            self.reading_time_minutes = round(self.word_count / 225, 1)
        return self
    
    @model_validator(mode='after')
    def sanitize_text(self) -> 'ArticleContent':
        """Sanitize the text content by removing excessive whitespace."""
        if self.text:
            # Replace multiple newlines with a maximum of two
            self.text = re.sub(r'\n{3,}', '\n\n', self.text)
            # Replace multiple spaces with a single space
            self.text = re.sub(r' {2,}', ' ', self.text)
            # Trim leading/trailing whitespace
            self.text = self.text.strip()
        return self
    
    def generate_id(self) -> str:
        """Generate a unique ID for the article content based on URL and title."""
        unique_string = f"{self.url}:{self.title}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the article content to a dictionary with camelCase keys."""
        return self.model_dump(by_alias=True, mode='json')
    
    def to_cache_key(self) -> str:
        """Generate a cache key for this article content."""
        article_id = self.generate_id()
        return f"article_content:{article_id}"
    
    def get_main_image_url(self) -> Optional[str]:
        """Get the main image URL if available."""
        if self.image_urls:
            return self.image_urls[0]
        return None
    
    def get_domain(self) -> str:
        """Extract the domain name from the article URL."""
        parsed_url = urlparse(str(self.url))
        return parsed_url.netloc
    
    def get_text_snippet(self, max_length: int = 200) -> str:
        """Get a snippet of the article text with a maximum length."""
        if not self.text:
            return ""
        
        if len(self.text) <= max_length:
            return self.text
        
        # Find the last space before max_length to avoid cutting words
        snippet = self.text[:max_length]
        last_space = snippet.rfind(' ')
        if last_space > 0:
            snippet = snippet[:last_space]
        
        return f"{snippet}..."
    
    def resolve_relative_urls(self, base_url: str) -> 'ArticleContent':
        """Resolve relative URLs in image_urls to absolute URLs."""
        resolved_urls = []
        for url in self.image_urls:
            if not url.startswith(('http://', 'https://')):
                resolved_urls.append(urljoin(base_url, url))
            else:
                resolved_urls.append(url)
        
        return self.model_copy(update={"image_urls": resolved_urls})
    
    class Config:
        """Pydantic configuration for the ArticleContent model."""
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            HttpUrl: str,
        }
        populate_by_name = True
        str_strip_whitespace = True
        validate_assignment = True
