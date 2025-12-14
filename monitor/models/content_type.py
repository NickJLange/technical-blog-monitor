"""
ContentType enum for classifying different types of content.

This module defines the ContentType enum used throughout the application
to classify and categorize different types of technical content that
the monitoring system processes.
"""
from enum import Enum


class ContentType(str, Enum):
    """
    Types of content that can be processed by the monitoring system.
    
    This enum helps categorize different types of technical content
    to enable specialized processing and filtering capabilities.
    """
    BLOG_POST = "blog_post"
    ARTICLE = "article"
    DOCUMENTATION = "documentation"
    RELEASE_NOTES = "release_notes"
    TUTORIAL = "tutorial"
    NEWS = "news"
    CASE_STUDY = "case_study"
    WHITEPAPER = "whitepaper"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, content_type: str) -> 'ContentType':
        """
        Convert a string to a ContentType enum value.
        
        Args:
            content_type: String representation of content type
            
        Returns:
            The matching ContentType enum value, or UNKNOWN if no match
        """
        try:
            return cls(content_type.lower())
        except ValueError:
            return cls.UNKNOWN

    def is_educational(self) -> bool:
        """Check if the content type is primarily educational."""
        return self in (self.TUTORIAL, self.DOCUMENTATION)

    def is_news(self) -> bool:
        """Check if the content type is primarily news-oriented."""
        return self in (self.BLOG_POST, self.NEWS, self.RELEASE_NOTES)

    def is_detailed(self) -> bool:
        """Check if the content type is typically detailed/long-form."""
        return self in (self.WHITEPAPER, self.CASE_STUDY, self.DOCUMENTATION)
