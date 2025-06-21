"""
JSON feed processor for the technical blog monitor.

This module provides functionality for fetching and parsing JSON feeds,
extracting blog posts, and handling various JSON formats and edge cases.
It implements the FeedProcessor interface for JSON feeds, supporting both
the standardized JSON Feed format (https://jsonfeed.org/) and custom
JSON-based feed formats.
"""
import asyncio
import datetime
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitor.config import FeedConfig
from monitor.feeds.base import FeedProcessor, parse_feed_entries
from monitor.models.blog_post import BlogPost

# Set up structured logger
logger = structlog.get_logger()


class JSONFeedProcessor(FeedProcessor):
    """
    JSON feed processor implementation.
    
    This processor handles fetching and parsing JSON feeds, extracting blog posts,
    and handling various JSON formats and edge cases. It supports both the
    standardized JSON Feed format and custom JSON-based feed formats.
    """
    
    def __init__(self, config: FeedConfig):
        """
        Initialize the JSON feed processor.
        
        Args:
            config: Feed configuration
        """
        super().__init__(config)
        # Add JSON content type to headers if not present
        if not any(h.lower() == 'accept' for h in self.headers):
            self.headers['Accept'] = 'application/json'
    
    async def fetch_feed(self, client: httpx.AsyncClient) -> bytes:
        """
        Fetch the JSON feed content from the source.
        
        Args:
            client: HTTP client to use for the request
            
        Returns:
            bytes: Raw feed content
            
        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        logger.debug("Fetching JSON feed", url=self.url)
        
        # Make the request
        response = await client.get(
            str(self.url),
            headers=self.headers,
            follow_redirects=True,
        )
        response.raise_for_status()
        
        # Get the content
        content = response.content
        
        # Check if the content is valid JSON
        try:
            # Just try to parse it to validate, but return the raw content
            json.loads(content)
        except json.JSONDecodeError:
            # Not valid JSON, try to find JSON feed URL in HTML
            try:
                soup = BeautifulSoup(content, 'html.parser')
                json_link = soup.find('link', rel='alternate', type='application/json')
                
                if json_link and json_link.get('href'):
                    json_url = json_link['href']
                    # Handle relative URLs
                    if not json_url.startswith(('http://', 'https://')):
                        base_url = str(self.url)
                        json_url = urljoin(base_url, json_url)
                    
                    logger.info(
                        "Found JSON feed link in HTML, fetching actual feed",
                        original_url=self.url,
                        json_url=json_url,
                    )
                    
                    # Fetch the actual JSON feed
                    response = await client.get(
                        json_url,
                        headers=self.headers,
                        follow_redirects=True,
                    )
                    response.raise_for_status()
                    content = response.content
                    
                    # Validate JSON again
                    json.loads(content)
                else:
                    raise ValueError("Content is not valid JSON and no JSON feed link found in HTML")
            except Exception as e:
                logger.warning(
                    "Error trying to find JSON feed URL in HTML",
                    url=self.url,
                    error=str(e),
                )
                raise ValueError(f"Content from {self.url} is not valid JSON: {str(e)}")
        
        logger.debug(
            "JSON feed fetched successfully",
            url=self.url,
            content_length=len(content),
        )
        
        return content
    
    async def parse_feed(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Parse the JSON feed content into a list of entry dictionaries.
        
        This method handles both standard JSON Feed format and custom JSON formats
        by looking for common patterns in the JSON structure.
        
        Args:
            content: Raw feed content
            
        Returns:
            List[Dict[str, Any]]: List of feed entries as dictionaries
            
        Raises:
            ValueError: If the feed content cannot be parsed
        """
        logger.debug("Parsing JSON feed content")
        
        try:
            # Parse JSON content
            # This is CPU-bound, so we run it in a thread pool
            loop = asyncio.get_running_loop()
            feed_data = await loop.run_in_executor(
                None,
                lambda: json.loads(content)
            )
            
            # Try to find entries in the JSON structure
            entries = []
            
            # Check for standard JSON Feed format first
            if isinstance(feed_data, dict):
                # Standard JSON Feed format (https://jsonfeed.org/)
                if 'items' in feed_data and isinstance(feed_data['items'], list):
                    entries = feed_data['items']
                
                # WordPress REST API format
                elif 'posts' in feed_data and isinstance(feed_data['posts'], list):
                    entries = feed_data['posts']
                
                # Ghost Blog API format
                elif 'data' in feed_data and isinstance(feed_data['data'], dict) and 'posts' in feed_data['data']:
                    entries = feed_data['data']['posts']
                
                # Medium API format
                elif 'payload' in feed_data and 'references' in feed_data['payload']:
                    if 'Post' in feed_data['payload']['references']:
                        entries = list(feed_data['payload']['references']['Post'].values())
                
                # Generic API format with data array
                elif 'data' in feed_data and isinstance(feed_data['data'], list):
                    entries = feed_data['data']
                
                # Generic API format with results array
                elif 'results' in feed_data and isinstance(feed_data['results'], list):
                    entries = feed_data['results']
                
                # Generic API format with articles array
                elif 'articles' in feed_data and isinstance(feed_data['articles'], list):
                    entries = feed_data['articles']
                
                # Generic API format with content array
                elif 'content' in feed_data and isinstance(feed_data['content'], list):
                    entries = feed_data['content']
            
            # If the root is an array, assume it's the entries
            elif isinstance(feed_data, list):
                entries = feed_data
            
            if not entries:
                logger.warning(
                    "Could not find entries in JSON feed",
                    url=self.url,
                    keys=list(feed_data.keys()) if isinstance(feed_data, dict) else "root is array",
                )
                # Return empty list if we couldn't find entries
                return []
            
            logger.debug(
                "JSON feed parsed successfully",
                url=self.url,
                entry_count=len(entries),
            )
            
            return entries
        
        except json.JSONDecodeError as e:
            logger.error(
                "Error parsing JSON feed",
                url=self.url,
                error=str(e),
                position=e.pos,
            )
            raise ValueError(f"Invalid JSON content: {str(e)}")
        
        except Exception as e:
            logger.error(
                "Unexpected error parsing JSON feed",
                url=self.url,
                error=str(e),
            )
            raise ValueError(f"Error parsing JSON feed: {str(e)}")
    
    async def extract_posts(self, entries: List[Dict[str, Any]]) -> List[BlogPost]:
        """
        Extract blog posts from JSON feed entries.
        
        This method handles various JSON feed formats by looking for common
        field names and patterns.
        
        Args:
            entries: List of feed entries as dictionaries
            
        Returns:
            List[BlogPost]: List of blog posts
        """
        logger.debug(
            "Extracting blog posts from JSON feed entries",
            url=self.url,
            entry_count=len(entries),
        )
        
        posts = []
        
        for entry in entries:
            try:
                # Extract required fields with fallbacks for different formats
                
                # Title
                title = self._get_nested_value(entry, [
                    'title', 'headline', 'name', 'subject', 'topic'
                ])
                if not title:
                    # Skip entries without a title
                    continue
                
                # URL
                url = self._get_nested_value(entry, [
                    'url', 'link', 'permalink', 'canonical_url', 'href',
                    'external_url', 'alternate_url', 'id'
                ])
                if not url:
                    # Skip entries without a URL
                    continue
                
                # Generate a unique ID
                entry_id = self._get_nested_value(entry, [
                    'id', 'guid', 'uuid', 'slug', 'uri', 'url'
                ])
                if not entry_id:
                    entry_id = url
                
                import hashlib
                post_id = hashlib.md5(f"{self.name}:{entry_id}".encode()).hexdigest()
                
                # Author
                author = self._get_nested_value(entry, [
                    'author', 'creator', 'writer', 'byline'
                ])
                
                # Handle complex author objects
                if isinstance(author, dict):
                    author = self._get_nested_value(author, [
                        'name', 'display_name', 'username', 'login', 'email'
                    ])
                
                # Publication date
                publish_date = None
                date_str = self._get_nested_value(entry, [
                    'date_published', 'published', 'pubDate', 'date',
                    'created', 'created_at', 'published_at', 'timestamp'
                ])
                
                if date_str:
                    try:
                        if isinstance(date_str, (int, float)):
                            # Unix timestamp
                            publish_date = datetime.datetime.fromtimestamp(
                                date_str,
                                tz=datetime.timezone.utc
                            )
                        else:
                            # String date
                            publish_date = date_parser.parse(date_str)
                            if publish_date.tzinfo is None:
                                publish_date = publish_date.replace(tzinfo=datetime.timezone.utc)
                    except Exception as e:
                        logger.warning(
                            "Error parsing publication date",
                            url=url,
                            date=date_str,
                            error=str(e),
                        )
                
                # Updated date
                updated_date = None
                updated_str = self._get_nested_value(entry, [
                    'date_modified', 'modified', 'updated', 'updated_at',
                    'last_modified', 'modified_at'
                ])
                
                if updated_str:
                    try:
                        if isinstance(updated_str, (int, float)):
                            # Unix timestamp
                            updated_date = datetime.datetime.fromtimestamp(
                                updated_str,
                                tz=datetime.timezone.utc
                            )
                        else:
                            # String date
                            updated_date = date_parser.parse(updated_str)
                            if updated_date.tzinfo is None:
                                updated_date = updated_date.replace(tzinfo=datetime.timezone.utc)
                    except Exception as e:
                        logger.warning(
                            "Error parsing updated date",
                            url=url,
                            date=updated_str,
                            error=str(e),
                        )
                
                # Summary/description
                summary = self._get_nested_value(entry, [
                    'summary', 'description', 'excerpt', 'snippet',
                    'abstract', 'subtitle', 'content_text', 'preview'
                ])
                
                # Clean HTML in summary
                if summary and '<' in summary:
                    try:
                        soup = BeautifulSoup(summary, 'html.parser')
                        summary = soup.get_text(separator=' ', strip=True)
                    except Exception:
                        # If parsing fails, use a simple regex to strip tags
                        summary = re.sub(r'<[^>]+>', '', summary)
                
                # Limit summary length
                if summary and len(summary) > 500:
                    summary = summary[:497] + '...'
                
                # Tags/categories
                tags = []
                
                # Try different tag field names
                for tag_field in ['tags', 'categories', 'keywords', 'topics', 'subjects']:
                    tag_list = entry.get(tag_field)
                    if tag_list:
                        if isinstance(tag_list, list):
                            for tag in tag_list:
                                if isinstance(tag, str):
                                    tags.append(tag.strip())
                                elif isinstance(tag, dict) and 'name' in tag:
                                    tags.append(tag['name'].strip())
                        elif isinstance(tag_list, str):
                            # Split comma-separated tags
                            for tag in tag_list.split(','):
                                tags.append(tag.strip())
                
                # Create BlogPost object
                post = BlogPost(
                    id=post_id,
                    url=url,
                    title=title,
                    source=self.name,
                    author=author,
                    publish_date=publish_date,
                    updated_date=updated_date,
                    summary=summary,
                    tags=tags,
                    metadata={
                        'feed_url': str(self.url),
                        'original_id': entry_id,
                    }
                )
                
                # Store full content if available
                content = self._get_nested_value(entry, [
                    'content_html', 'content', 'article', 'body', 'text'
                ])
                if content:
                    post.metadata['full_content'] = content
                
                # Add to posts list
                posts.append(post)
            
            except Exception as e:
                logger.warning(
                    "Error processing JSON feed entry",
                    url=self.url,
                    error=str(e),
                    entry=str(entry)[:200] + '...' if len(str(entry)) > 200 else str(entry),
                )
        
        logger.debug(
            "Extracted blog posts from JSON feed",
            url=self.url,
            post_count=len(posts),
        )
        
        return posts
    
    async def get_feed_fingerprint(self, content: bytes) -> str:
        """
        Generate a fingerprint for the feed content to detect changes.
        
        For JSON feeds, we try to extract the most recent entry's ID or URL
        as the fingerprint, as this is more reliable than hashing the entire
        feed content (which might contain timestamps).
        
        Args:
            content: Raw feed content
            
        Returns:
            str: Feed fingerprint
        """
        try:
            # Parse the feed
            feed_data = json.loads(content)
            
            # Try to find entries
            entries = []
            
            if isinstance(feed_data, dict):
                # Check various common entry container fields
                for field in ['items', 'posts', 'data', 'results', 'articles', 'content']:
                    if field in feed_data:
                        if isinstance(feed_data[field], list):
                            entries = feed_data[field]
                            break
                        elif isinstance(feed_data[field], dict) and 'posts' in feed_data[field]:
                            entries = feed_data[field]['posts']
                            break
            elif isinstance(feed_data, list):
                entries = feed_data
            
            if entries and len(entries) > 0:
                # Get the most recent entry
                most_recent = entries[0]
                
                # Try to get a stable identifier
                for id_field in ['id', 'guid', 'uuid', 'url', 'link', 'permalink']:
                    if id_field in most_recent:
                        return f"{id_field}:{most_recent[id_field]}"
                
                # If no ID field, try title
                if 'title' in most_recent:
                    return f"title:{most_recent['title']}"
            
            # If we couldn't find a stable identifier, fall back to default
            return await super().get_feed_fingerprint(content)
        
        except Exception as e:
            logger.warning(
                "Error generating JSON feed fingerprint, falling back to default",
                url=self.url,
                error=str(e),
            )
            return await super().get_feed_fingerprint(content)
    
    def _get_nested_value(self, data: Dict[str, Any], keys: List[str]) -> Optional[Any]:
        """
        Get a value from a dictionary using a list of possible keys.
        
        This helper method tries each key in order and returns the first
        value found. It also handles nested objects by checking if the value
        is a dictionary and has any of the keys.
        
        Args:
            data: Dictionary to search
            keys: List of possible keys to try
            
        Returns:
            Any: The value if found, None otherwise
        """
        if not isinstance(data, dict):
            return None
        
        # Try direct keys first
        for key in keys:
            if key in data:
                return data[key]
        
        # Try nested keys (one level deep)
        for outer_key, outer_value in data.items():
            if isinstance(outer_value, dict):
                for key in keys:
                    if key in outer_value:
                        return outer_value[key]
        
        return None
