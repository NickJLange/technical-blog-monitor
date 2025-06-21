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
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import structlog
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

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
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract basic metadata if not provided
        if not title:
            title_tag = soup.title
            if title_tag:
                metadata["title"] = title_tag.string.strip()
        
        # Extract author
        author = extract_author(soup, html_content)
        if author:
            metadata["author"] = author
        
        # Extract publication date
        publish_date = extract_publish_date(soup, html_content)
        if publish_date:
            metadata["publish_date"] = publish_date
        
        # Extract tags/keywords
        tags = extract_tags(soup)
        if tags:
            metadata["tags"] = tags
        
        # Extract description
        description = extract_description(soup)
        if description:
            metadata["description"] = description
        
        # Extract canonical URL
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            metadata["canonical_url"] = canonical['href']
        
        # Extract Open Graph metadata
        og_metadata = extract_open_graph(soup)
        if og_metadata:
            metadata.update(og_metadata)
        
        # Extract Twitter Card metadata
        twitter_metadata = extract_twitter_card(soup)
        if twitter_metadata:
            metadata.update(twitter_metadata)
        
        # Extract JSON-LD metadata
        jsonld_metadata = extract_jsonld(soup)
        if jsonld_metadata:
            metadata.update(jsonld_metadata)
        
        return metadata
    
    except Exception as e:
        logger.warning("Error extracting metadata", url=url, error=str(e))
        return metadata


def extract_author(soup: BeautifulSoup, html_content: str) -> Optional[str]:
    """
    Extract author information from HTML.
    
    Args:
        soup: BeautifulSoup object
        html_content: Raw HTML content
        
    Returns:
        Optional[str]: Author name if found, None otherwise
    """
    # Try meta tags first
    for meta in soup.find_all('meta'):
        if meta.get('name') and meta.get('content'):
            name = meta['name'].lower()
            if name in ['author', 'dc.creator', 'article:author']:
                return meta['content'].strip()
    
    # Try Open Graph
    og_author = soup.find('meta', property='og:author')
    if og_author and og_author.get('content'):
        return og_author['content'].strip()
    
    # Try schema.org markup
    author_elem = soup.find(['span', 'div', 'a'], itemprop='author')
    if author_elem:
        name_elem = author_elem.find(['span', 'div'], itemprop='name')
        if name_elem:
            return name_elem.get_text().strip()
        return author_elem.get_text().strip()
    
    # Try common author classes/IDs
    for selector in ['.author', '.byline', '.meta-author', '#author', '[rel="author"]']:
        author_elem = soup.select_one(selector)
        if author_elem:
            return author_elem.get_text().strip()
    
    # Try regex patterns
    for pattern in AUTHOR_PATTERNS:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def extract_publish_date(soup: BeautifulSoup, html_content: str) -> Optional[datetime]:
    """
    Extract publication date from HTML.
    
    Args:
        soup: BeautifulSoup object
        html_content: Raw HTML content
        
    Returns:
        Optional[datetime]: Publication date if found, None otherwise
    """
    # Try meta tags first
    for meta in soup.find_all('meta'):
        if meta.get('name') and meta.get('content'):
            name = meta['name'].lower()
            if name in ['date', 'pubdate', 'publishdate', 'dc.date', 'article:published_time']:
                try:
                    return date_parser.parse(meta['content'])
                except Exception:
                    pass
    
    # Try Open Graph
    og_date = soup.find('meta', property='og:published_time')
    if og_date and og_date.get('content'):
        try:
            return date_parser.parse(og_date['content'])
        except Exception:
            pass
    
    # Try schema.org markup
    date_elem = soup.find(['span', 'div', 'time'], itemprop='datePublished')
    if date_elem:
        if date_elem.get('datetime'):
            try:
                return date_parser.parse(date_elem['datetime'])
            except Exception:
                pass
        try:
            return date_parser.parse(date_elem.get_text())
        except Exception:
            pass
    
    # Try time elements
    time_elem = soup.find('time')
    if time_elem and time_elem.get('datetime'):
        try:
            return date_parser.parse(time_elem['datetime'])
        except Exception:
            pass
    
    # Try common date classes
    for selector in ['.date', '.published', '.post-date', '.entry-date', '.meta-date']:
        date_elem = soup.select_one(selector)
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


def extract_tags(soup: BeautifulSoup) -> List[str]:
    """
    Extract tags/keywords from HTML.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        List[str]: List of tags
    """
    tags = []
    
    # Try meta keywords
    keywords = soup.find('meta', attrs={'name': 'keywords'})
    if keywords and keywords.get('content'):
        for keyword in keywords['content'].split(','):
            if keyword.strip():
                tags.append(keyword.strip())
    
    # Try article:tag meta tags
    for tag_meta in soup.find_all('meta', property='article:tag'):
        if tag_meta.get('content'):
            tags.append(tag_meta['content'].strip())
    
    # Try common tag classes
    for selector in ['.tags', '.categories', '.keywords', '.topics']:
        tag_container = soup.select_one(selector)
        if tag_container:
            for tag_elem in tag_container.find_all(['a', 'span', 'li']):
                tag_text = tag_elem.get_text().strip()
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


def extract_description(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract description/summary from HTML.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Optional[str]: Description if found, None otherwise
    """
    # Try meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        return meta_desc['content'].strip()
    
    # Try Open Graph description
    og_desc = soup.find('meta', property='og:description')
    if og_desc and og_desc.get('content'):
        return og_desc['content'].strip()
    
    # Try Twitter Card description
    twitter_desc = soup.find('meta', attrs={'name': 'twitter:description'})
    if twitter_desc and twitter_desc.get('content'):
        return twitter_desc['content'].strip()
    
    # Try schema.org markup
    desc_elem = soup.find(['span', 'div', 'p'], itemprop='description')
    if desc_elem:
        return desc_elem.get_text().strip()
    
    return None


def extract_open_graph(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract Open Graph metadata from HTML.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Dict[str, Any]: Open Graph metadata
    """
    og_metadata = {}
    
    # Extract all Open Graph meta tags
    for meta in soup.find_all('meta', property=re.compile(r'^og:')):
        if meta.get('content'):
            # Remove 'og:' prefix and use as key
            key = meta['property'][3:]
            og_metadata[f"og_{key}"] = meta['content'].strip()
    
    return og_metadata


def extract_twitter_card(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract Twitter Card metadata from HTML.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Dict[str, Any]: Twitter Card metadata
    """
    twitter_metadata = {}
    
    # Extract all Twitter Card meta tags
    for meta in soup.find_all('meta', attrs={'name': re.compile(r'^twitter:')}):
        if meta.get('content'):
            # Remove 'twitter:' prefix and use as key
            key = meta['name'][8:]
            twitter_metadata[f"twitter_{key}"] = meta['content'].strip()
    
    return twitter_metadata


def extract_jsonld(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract JSON-LD metadata from HTML.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Dict[str, Any]: JSON-LD metadata
    """
    jsonld_metadata = {}
    
    # Find JSON-LD script tags
    jsonld_scripts = soup.find_all('script', type='application/ld+json')
    
    for script in jsonld_scripts:
        try:
            data = json.loads(script.string)
            
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
                                jsonld_metadata['jsonld_date_published'] = date_parser.parse(item['datePublished'])
                            except Exception:
                                pass
                        
                        if 'dateModified' in item:
                            try:
                                jsonld_metadata['jsonld_date_modified'] = date_parser.parse(item['dateModified'])
                            except Exception:
                                pass
                        
                        if 'description' in item:
                            jsonld_metadata['jsonld_description'] = item['description']
                        
                        if 'keywords' in item:
                            if isinstance(item['keywords'], list):
                                jsonld_metadata['jsonld_keywords'] = item['keywords']
                            elif isinstance(item['keywords'], str):
                                jsonld_metadata['jsonld_keywords'] = [k.strip() for k in item['keywords'].split(',')]
        
        except Exception as e:
            logger.warning("Error parsing JSON-LD", error=str(e))
    
    return jsonld_metadata
