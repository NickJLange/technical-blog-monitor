"""
Metadata extraction module for the technical blog monitor.

This module provides functionality for extracting metadata from web pages,
including publication dates, authors, tags, and other structured information.
It supports various metadata formats including Open Graph, Twitter Cards,
JSON-LD, and common HTML patterns.
"""
import re
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import structlog
from dateutil import parser as date_parser

from monitor.parser import parse_html
from monitor.parser.html_parser import HTMLParser

# Set up structured logger
logger = structlog.get_logger()

# Common patterns for date extraction
DATE_PATTERNS = [
    r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',  # YYYY-MM-DD or YYYY/MM/DD
    r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',  # DD-MM-YYYY or DD/MM/YYYY
    r'(\w+ \d{1,2}, \d{4})',           # Month DD, YYYY
    r'(\d{1,2} \w+ \d{4})',            # DD Month YYYY
]

# Common patterns for author extraction
AUTHOR_PATTERNS = [
    r'author[:\s]+([^<>\n]+)',
    r'by[:\s]+([^<>\n]+)',
    r'written by[:\s]+([^<>\n]+)',
]


def extract_metadata(
    html_content: str,
    url: str,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract metadata from HTML content.
    
    This function extracts various metadata from HTML, including Open Graph,
    Twitter Cards, JSON-LD, and common HTML patterns.
    
    Args:
        html_content: HTML content
        url: URL of the page
        title: Optional title (if already extracted)
        
    Returns:
        Dict[str, Any]: Extracted metadata
    """
    metadata = {
        "url": url,
        "domain": urlparse(url).netloc,
    }
    
    if title:
        metadata["title"] = title
    
    try:
        parser = parse_html(html_content)
        
        # Extract basic metadata if not provided
        if not title:
            title_tag = parser.find('title')
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                if title_text:
                    metadata["title"] = title_text
        
        # Extract author
        author = extract_author(parser, html_content)
        if author:
            metadata["author"] = author
        
        # Extract publication date
        publish_date = extract_publish_date(parser, html_content)
        if publish_date:
            metadata["publish_date"] = publish_date
        
        # Extract tags/keywords
        tags = extract_tags(parser)
        if tags:
            metadata["tags"] = tags
        
        # Extract description
        description = extract_description(parser)
        if description:
            metadata["description"] = description
        
        # Extract canonical URL
        canonical = parser.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            metadata["canonical_url"] = canonical.get('href')
        
        # Extract Open Graph metadata
        og_metadata = extract_open_graph(parser)
        if og_metadata:
            metadata.update(og_metadata)
        
        # Extract Twitter Card metadata
        twitter_metadata = extract_twitter_card(parser)
        if twitter_metadata:
            metadata.update(twitter_metadata)
        
        # Extract JSON-LD metadata
        jsonld_metadata = extract_jsonld(parser)
        if jsonld_metadata:
            metadata.update(jsonld_metadata)
        
        return metadata
    
    except Exception as e:
        logger.warning("Error extracting metadata", url=url, error=str(e))
        return metadata


def extract_author(parser: HTMLParser, html_content: str) -> Optional[str]:
    """
    Extract author information from HTML.
    
    Args:
        parser: HTMLParser object
        html_content: Raw HTML content
        
    Returns:
        Optional[str]: Author name if found, None otherwise
    """
    # Try meta tags first
    for meta in parser.find_all('meta'):
        name_attr = meta.get('name')
        content_attr = meta.get('content')
        if name_attr and content_attr:
            name_lower = name_attr.lower()
            if name_lower in ['author', 'dc.creator', 'article:author']:
                return content_attr.strip()
    
    # Try Open Graph
    og_author = parser.find('meta', property='og:author')
    if og_author:
        content = og_author.get('content')
        if content:
            return content.strip()
    
    # Try schema.org markup
    for tag_name in ['span', 'div', 'a']:
        author_elem = parser.find(tag_name, itemprop='author')
        if author_elem:
            # Try to find name sub-element
            for sub_tag in ['span', 'div']:
                name_elem = author_elem.find(sub_tag, itemprop='name')
                if name_elem:
                    return name_elem.get_text(strip=True)
            return author_elem.get_text(strip=True)
    
    # Try common author classes/IDs
    for selector in ['.author', '.byline', '.meta-author', '#author', '[rel="author"]']:
        author_elem = parser.select_one(selector)
        if author_elem:
            return author_elem.get_text(strip=True)
    
    # Try regex patterns
    for pattern in AUTHOR_PATTERNS:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def extract_publish_date(parser: HTMLParser, html_content: str) -> Optional[datetime]:
    """
    Extract publication date from HTML.
    
    Args:
        parser: HTMLParser object
        html_content: Raw HTML content
        
    Returns:
        Optional[datetime]: Publication date if found, None otherwise
    """
    # Try meta tags first
    for meta in parser.find_all('meta'):
        name_attr = meta.get('name')
        content_attr = meta.get('content')
        if name_attr and content_attr:
            name_lower = name_attr.lower()
            date_names = ['date', 'pubdate', 'publishdate', 'dc.date', 'article:published_time']
            if name_lower in date_names:
                try:
                    return date_parser.parse(content_attr)
                except Exception:
                    pass
    
    # Try Open Graph
    og_date = parser.find('meta', property='og:published_time')
    if og_date:
        content = og_date.get('content')
        if content:
            try:
                return date_parser.parse(content)
            except Exception:
                pass
    
    # Try schema.org markup
    for tag_name in ['span', 'div', 'time']:
        date_elem = parser.find(tag_name, itemprop='datePublished')
        if date_elem:
            datetime_attr = date_elem.get('datetime')
            if datetime_attr:
                try:
                    return date_parser.parse(datetime_attr)
                except Exception:
                    pass
            try:
                return date_parser.parse(date_elem.get_text())
            except Exception:
                pass
    
    # Try time elements
    time_elem = parser.find('time')
    if time_elem:
        datetime_attr = time_elem.get('datetime')
        if datetime_attr:
            try:
                return date_parser.parse(datetime_attr)
            except Exception:
                pass
    
    # Try common date classes
    for selector in ['.date', '.published', '.post-date', '.entry-date', '.meta-date']:
        date_elem = parser.select_one(selector)
        if date_elem:
            try:
                return date_parser.parse(date_elem.get_text())
            except Exception:
                pass
    
    # Try regex patterns
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, html_content)
        if match:
            try:
                return date_parser.parse(match.group(1))
            except Exception:
                pass
    
    return None


def extract_tags(parser: HTMLParser) -> List[str]:
    """
    Extract tags/keywords from HTML.
    
    Args:
        parser: HTMLParser object
        
    Returns:
        List[str]: List of tags
    """
    tags = []
    
    # Try meta keywords
    keywords = parser.find('meta', name='keywords')
    if keywords:
        content = keywords.get('content')
        if content:
            for keyword in content.split(','):
                if keyword.strip():
                    tags.append(keyword.strip())
    
    # Try article:tag meta tags
    for tag_meta in parser.find_all('meta', property='article:tag'):
        content = tag_meta.get('content')
        if content:
            tags.append(content.strip())
    
    # Try common tag classes
    for selector in ['.tags', '.categories', '.keywords', '.topics']:
        tag_container = parser.select_one(selector)
        if tag_container:
            for tag_name in ['a', 'span', 'li']:
                for tag_elem in tag_container.find_all(tag_name):
                    tag_text = tag_elem.get_text(strip=True)
                    if tag_text and tag_text not in ['Tags:', 'Categories:', 'Keywords:']:
                        tags.append(tag_text)
    
    # Remove duplicates and normalize
    normalized_tags = []
    seen = set()
    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower not in seen and len(tag) > 1:
            seen.add(tag_lower)
            normalized_tags.append(tag)
    
    return normalized_tags


def extract_description(parser: HTMLParser) -> Optional[str]:
    """
    Extract description/summary from HTML.
    
    Args:
        parser: HTMLParser object
        
    Returns:
        Optional[str]: Description if found, None otherwise
    """
    # Try meta description
    meta_desc = parser.find('meta', name='description')
    if meta_desc:
        content = meta_desc.get('content')
        if content:
            return content.strip()
    
    # Try Open Graph description
    og_desc = parser.find('meta', property='og:description')
    if og_desc:
        content = og_desc.get('content')
        if content:
            return content.strip()
    
    # Try Twitter Card description
    twitter_desc = parser.find('meta', name='twitter:description')
    if twitter_desc:
        content = twitter_desc.get('content')
        if content:
            return content.strip()
    
    # Try schema.org markup
    for tag_name in ['span', 'div', 'p']:
        desc_elem = parser.find(tag_name, itemprop='description')
        if desc_elem:
            return desc_elem.get_text(strip=True)
    
    return None


def extract_open_graph(parser: HTMLParser) -> Dict[str, Any]:
    """
    Extract Open Graph metadata from HTML.
    
    Args:
        parser: HTMLParser object
        
    Returns:
        Dict[str, Any]: Open Graph metadata
    """
    og_metadata = {}
    
    # Extract all Open Graph meta tags by iterating through all meta tags
    for meta in parser.find_all('meta'):
        prop = meta.get('property')
        if prop and prop.startswith('og:'):
            content = meta.get('content')
            if content:
                # Remove 'og:' prefix and use as key
                key = prop[3:]
                og_metadata[f"og_{key}"] = content.strip()
    
    return og_metadata


def extract_twitter_card(parser: HTMLParser) -> Dict[str, Any]:
    """
    Extract Twitter Card metadata from HTML.
    
    Args:
        parser: HTMLParser object
        
    Returns:
        Dict[str, Any]: Twitter Card metadata
    """
    twitter_metadata = {}
    
    # Extract all Twitter Card meta tags by iterating through all meta tags
    for meta in parser.find_all('meta'):
        name_attr = meta.get('name')
        if name_attr and name_attr.startswith('twitter:'):
            content = meta.get('content')
            if content:
                # Remove 'twitter:' prefix and use as key
                key = name_attr[8:]
                twitter_metadata[f"twitter_{key}"] = content.strip()
    
    return twitter_metadata


def extract_jsonld(parser: HTMLParser) -> Dict[str, Any]:
    """
    Extract JSON-LD metadata from HTML.
    
    Args:
        parser: HTMLParser object
        
    Returns:
        Dict[str, Any]: JSON-LD metadata
    """
    jsonld_metadata = {}
    
    # Find JSON-LD script tags
    jsonld_scripts = parser.find_all('script', type='application/ld+json')
    
    for script in jsonld_scripts:
        try:
            # Get script content
            script_content = script.get_text()
            if not script_content:
                continue
                
            data = json.loads(script_content)
            
            # Handle single item or array of items
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                # Extract type
                if '@type' in item:
                    item_type = item['@type']
                    jsonld_metadata['jsonld_type'] = item_type
                    
                    # Extract data based on type
                    if item_type in ['Article', 'BlogPosting', 'NewsArticle']:
                        # Article metadata
                        if 'headline' in item:
                            jsonld_metadata['jsonld_headline'] = item['headline']
                        
                        if 'author' in item:
                            if isinstance(item['author'], dict) and 'name' in item['author']:
                                jsonld_metadata['jsonld_author'] = item['author']['name']
                            elif isinstance(item['author'], str):
                                jsonld_metadata['jsonld_author'] = item['author']
                        
                        if 'datePublished' in item:
                            try:
                                parsed = date_parser.parse(item['datePublished'])
                                jsonld_metadata['jsonld_date_published'] = parsed
                            except Exception:
                                pass
                        
                        if 'dateModified' in item:
                            try:
                                parsed = date_parser.parse(item['dateModified'])
                                jsonld_metadata['jsonld_date_modified'] = parsed
                            except Exception:
                                pass
                        
                        if 'description' in item:
                            jsonld_metadata['jsonld_description'] = item['description']
                        
                        if 'keywords' in item:
                            if isinstance(item['keywords'], list):
                                jsonld_metadata['jsonld_keywords'] = item['keywords']
                            elif isinstance(item['keywords'], str):
                                kw_list = [k.strip() for k in item['keywords'].split(',')]
                                jsonld_metadata['jsonld_keywords'] = kw_list
        
        except Exception as e:
            logger.warning("Error parsing JSON-LD", error=str(e))
    
    return jsonld_metadata
