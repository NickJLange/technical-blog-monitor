"""
CacheEntry model for representing items in the cache.

This module defines the CacheEntry model with validation and utility methods
for working with cached content throughout the monitoring pipeline, including
expiration handling, serialization, and metadata management.
"""
import json
import pickle
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json import pydantic_encoder

T = TypeVar('T')


class ValueType(str, Enum):
    """Types of values that can be stored in the cache."""
    STRING = "string"
    JSON = "json"
    PICKLE = "pickle"
    BYTES = "bytes"
    IMAGE = "image"
    HTML = "html"
    TEXT = "text"


class CacheEntry(BaseModel):
    """
    Represents an entry in the cache.
    
    This model handles the storage, expiration, and serialization of cached content,
    along with metadata for tracking and management of cached items.
    """
    # Core fields
    key: str
    value_type: ValueType
    value: Any

    # Timing fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_url: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    content_hash: Optional[str] = None

    @field_validator("created_at", "expires_at", "last_accessed_at", mode="before")
    @classmethod
    def ensure_timezone(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Ensure all datetime fields have timezone information."""
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode='after')
    def validate_expiration(self) -> 'CacheEntry':
        """Validate that expires_at is after created_at if provided."""
        if self.expires_at and self.created_at and self.expires_at <= self.created_at:
            raise ValueError("Expiration time must be after creation time")
        return self

    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    def time_to_expiration(self) -> Optional[timedelta]:
        """Get the time remaining until expiration."""
        if not self.expires_at:
            return None
        now = datetime.now(timezone.utc)
        if now >= self.expires_at:
            return timedelta(0)
        return self.expires_at - now

    def time_since_creation(self) -> timedelta:
        """Get the time elapsed since creation."""
        return datetime.now(timezone.utc) - self.created_at

    def time_since_last_access(self) -> timedelta:
        """Get the time elapsed since last access."""
        return datetime.now(timezone.utc) - self.last_accessed_at

    def access(self) -> 'CacheEntry':
        """
        Mark the entry as accessed and return an updated copy.
        
        This updates the last_accessed_at timestamp and increments the access_count.
        """
        return self.model_copy(update={
            "last_accessed_at": datetime.now(timezone.utc),
            "access_count": self.access_count + 1
        })

    def with_ttl(self, ttl_seconds: int) -> 'CacheEntry':
        """
        Set the expiration time based on a TTL in seconds and return an updated copy.
        
        Args:
            ttl_seconds: Time to live in seconds
            
        Returns:
            Updated CacheEntry with expiration set
        """
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        return self.model_copy(update={"expires_at": expires_at})

    def serialize(self) -> bytes:
        """
        Serialize the cache entry for storage.
        
        Returns:
            bytes: Serialized representation of the cache entry
        """
        # For pickle value type, we need special handling
        if self.value_type == ValueType.PICKLE:
            # Store the original value temporarily
            original_value = self.value
            # Replace with None for JSON serialization
            self_dict = self.model_dump()
            self_dict["value"] = None

            # Serialize the entry without the value
            entry_bytes = json.dumps(self_dict, default=pydantic_encoder).encode('utf-8')

            # Pickle the value separately
            value_bytes = pickle.dumps(original_value)

            # Combine the two with a separator
            separator = b"__PICKLE_SEPARATOR__"
            return entry_bytes + separator + value_bytes

        # For bytes and image types, we need to handle binary data
        elif self.value_type in (ValueType.BYTES, ValueType.IMAGE):
            # Store the original value temporarily
            original_value = self.value
            # Replace with None for JSON serialization
            self_dict = self.model_dump()
            self_dict["value"] = None

            # Serialize the entry without the value
            entry_bytes = json.dumps(self_dict, default=pydantic_encoder).encode('utf-8')

            # Combine with the binary value
            separator = b"__BINARY_SEPARATOR__"
            if isinstance(original_value, bytes):
                value_bytes = original_value
            else:
                value_bytes = str(original_value).encode('utf-8')

            return entry_bytes + separator + value_bytes

        # For other types, standard JSON serialization works
        return json.dumps(self.model_dump(), default=pydantic_encoder).encode('utf-8')

    @classmethod
    def deserialize(cls, data: bytes) -> 'CacheEntry':
        """
        Deserialize a cache entry from bytes.
        
        Args:
            data: Serialized cache entry
            
        Returns:
            CacheEntry: Deserialized cache entry
        """
        # Check if this is a pickle or binary entry
        if b"__PICKLE_SEPARATOR__" in data:
            # Split the data
            entry_bytes, value_bytes = data.split(b"__PICKLE_SEPARATOR__", 1)

            # Parse the entry
            entry_dict = json.loads(entry_bytes.decode('utf-8'))

            # Unpickle the value
            value = pickle.loads(value_bytes)  # nosec B301: trusted internal cache

            # Restore the value
            entry_dict["value"] = value

            return cls.model_validate(entry_dict)

        elif b"__BINARY_SEPARATOR__" in data:
            # Split the data
            entry_bytes, value_bytes = data.split(b"__BINARY_SEPARATOR__", 1)

            # Parse the entry
            entry_dict = json.loads(entry_bytes.decode('utf-8'))

            # Restore the binary value
            entry_dict["value"] = value_bytes

            return cls.model_validate(entry_dict)

        # Standard JSON deserialization
        return cls.model_validate(json.loads(data.decode('utf-8')))

    @classmethod
    def create_string_entry(cls, key: str, value: str, ttl_seconds: Optional[int] = None, **kwargs) -> 'CacheEntry':
        """
        Create a cache entry for a string value.
        
        Args:
            key: Cache key
            value: String value to cache
            ttl_seconds: Optional TTL in seconds
            **kwargs: Additional fields for the cache entry
            
        Returns:
            CacheEntry: A new cache entry
        """
        entry = cls(
            key=key,
            value_type=ValueType.STRING,
            value=value,
            **kwargs
        )

        if ttl_seconds is not None:
            entry = entry.with_ttl(ttl_seconds)

        return entry

    @classmethod
    def create_json_entry(cls, key: str, value: Any, ttl_seconds: Optional[int] = None, **kwargs) -> 'CacheEntry':
        """
        Create a cache entry for a JSON-serializable value.
        
        Args:
            key: Cache key
            value: JSON-serializable value to cache
            ttl_seconds: Optional TTL in seconds
            **kwargs: Additional fields for the cache entry
            
        Returns:
            CacheEntry: A new cache entry
        """
        # Validate that the value is JSON serializable
        try:
            json.dumps(value, default=pydantic_encoder)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Value is not JSON serializable: {e}")

        entry = cls(
            key=key,
            value_type=ValueType.JSON,
            value=value,
            **kwargs
        )

        if ttl_seconds is not None:
            entry = entry.with_ttl(ttl_seconds)

        return entry

    @classmethod
    def create_pickle_entry(cls, key: str, value: Any, ttl_seconds: Optional[int] = None, **kwargs) -> 'CacheEntry':
        """
        Create a cache entry for any Python object using pickle.
        
        Args:
            key: Cache key
            value: Any Python object to cache
            ttl_seconds: Optional TTL in seconds
            **kwargs: Additional fields for the cache entry
            
        Returns:
            CacheEntry: A new cache entry
            
        Security Note:
            This method uses pickle serialization which is not secure against
            untrusted data. Ensure that the cache is only populated with trusted
            data from within the application boundary.
        """
        entry = cls(
            key=key,
            value_type=ValueType.PICKLE,
            value=value,
            **kwargs
        )

        if ttl_seconds is not None:
            entry = entry.with_ttl(ttl_seconds)

        return entry

    @classmethod
    def create_bytes_entry(cls, key: str, value: bytes, ttl_seconds: Optional[int] = None, **kwargs) -> 'CacheEntry':
        """
        Create a cache entry for binary data.
        
        Args:
            key: Cache key
            value: Binary data to cache
            ttl_seconds: Optional TTL in seconds
            **kwargs: Additional fields for the cache entry
            
        Returns:
            CacheEntry: A new cache entry
        """
        entry = cls(
            key=key,
            value_type=ValueType.BYTES,
            value=value,
            **kwargs
        )

        if ttl_seconds is not None:
            entry = entry.with_ttl(ttl_seconds)

        return entry

    @classmethod
    def create_html_entry(cls, key: str, value: str, ttl_seconds: Optional[int] = None, **kwargs) -> 'CacheEntry':
        """
        Create a cache entry for HTML content.
        
        Args:
            key: Cache key
            value: HTML content to cache
            ttl_seconds: Optional TTL in seconds
            **kwargs: Additional fields for the cache entry
            
        Returns:
            CacheEntry: A new cache entry
        """
        entry = cls(
            key=key,
            value_type=ValueType.HTML,
            value=value,
            **kwargs
        )

        if ttl_seconds is not None:
            entry = entry.with_ttl(ttl_seconds)

        return entry

    class Config:
        """Pydantic configuration for the CacheEntry model."""
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            bytes: lambda b: None,  # Bytes cannot be JSON serialized directly
        }
        arbitrary_types_allowed = True
