"""
BlogPost model for representing blog posts discovered from feeds.

This module defines the BlogPost model with validation and utility methods
for working with blog posts throughout the monitoring pipeline.
"""
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from monitor.models.content_type import ContentType


class BlogPost(BaseModel):
    """
    Represents a blog post discovered from a feed.
    
    This model contains all the metadata about a blog post including its
    source, publication info, and content classification.
    """
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

    # Additional fields for internal tracking
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_checked: Optional[datetime] = None
    processing_status: str = "pending"
    fetch_attempts: int = 0

    @field_validator("publish_date", "updated_date", mode="before")
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

    def is_same_as(self, other: 'BlogPost') -> bool:
        """Check if this blog post is the same as another."""
        if not isinstance(other, BlogPost):
            return False

        # Compare essential fields
        return (
            str(self.url) == str(other.url) and
            self.title == other.title and
            self.publish_date == other.publish_date
        )

    def has_been_updated(self, other: 'BlogPost') -> bool:
        """Check if this blog post has been updated compared to another."""
        if not self.is_same_as(other):
            return False

        # Check if updated_date exists and is newer
        if self.updated_date and other.updated_date:
            return self.updated_date > other.updated_date

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert the blog post to a dictionary with camelCase keys."""
        return self.model_dump(by_alias=True, mode='json')

    def to_cache_key(self) -> str:
        """Generate a cache key for this blog post."""
        return f"blog_post:{self.id}"

    def with_status(self, status: str) -> 'BlogPost':
        """Return a copy of this blog post with an updated status."""
        return self.model_copy(update={"processing_status": status})

    def increment_fetch_attempts(self) -> 'BlogPost':
        """Increment the fetch attempts counter and return updated post."""
        return self.model_copy(update={"fetch_attempts": self.fetch_attempts + 1})

    def update_last_checked(self) -> 'BlogPost':
        """Update the last_checked timestamp and return updated post."""
        return self.model_copy(
            update={"last_checked": datetime.now(timezone.utc)}
        )

    class Config:
        """Pydantic configuration for the BlogPost model."""
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            HttpUrl: str,
        }
        populate_by_name = True
        str_strip_whitespace = True
        validate_assignment = True
