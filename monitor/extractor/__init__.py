"""
Extractor package for the technical blog monitor.

This package provides functionality for extracting content from web pages,
including main article text, metadata, and embedded media. It handles
various content formats and structures, and provides a consistent interface
for content extraction regardless of the source.

The main components are:
- Article parser for extracting main content from HTML
- Metadata extractor for pulling author, date, tags, etc.
- Image extractor for finding and downloading images
- Text cleaner for normalizing and sanitizing extracted text
"""
from monitor.extractor.article_parser import (
    extract_article_content,
    extract_main_content,
    extract_article_metadata,
    clean_article_text,
)
from monitor.extractor.image_extractor import (
    extract_images,
    download_image,
    get_main_image,
)
from monitor.extractor.metadata import (
    extract_metadata,
    extract_publish_date,
    extract_author,
    extract_tags,
)

__all__ = [
    "extract_article_content",
    "extract_main_content",
    "extract_article_metadata",
    "clean_article_text",
    "extract_images",
    "download_image",
    "get_main_image",
    "extract_metadata",
    "extract_publish_date",
    "extract_author",
    "extract_tags",
]
