"""
Article parser module for the technical blog monitor.

This module provides functionality for extracting clean, readable content
from web pages, including the main article text, metadata, and structure.
It uses readability-lxml for main content extraction and BeautifulSoup for
additional parsing and cleaning.
"""
import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup, Comment, NavigableString
from dateutil import parser as date_parser
from readability import Document

from monitor.models.article import ArticleContent
from monitor.models.content_type import ContentType

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

# HTML elements to remove during cleaning
NOISE_ELEMENTS = [
    'script', 'style', 'iframe', 'form', 'button', 'input', 'nav', 'footer', 
    'header', 'aside', 'noscript', 'figcaption', 'figure', 'time', 'svg',
]

# CSS selectors for common article containers
ARTICLE_SELECTORS = [
    'article', 'main', '.post', '.article', '.entry', '.content', '.post-content',
    '.entry-content', '.article-content', '.blog-post', '.blog-entry',
    '#content', '#main', '#post', '#article',
]


async def extract_article_content(
    url: str,
    cache_client: Any,
    thread_pool: ThreadPoolExecutor,
    html_content: Optional[str] = None,
    use_cache: bool = True,
    cache_ttl: int = 86400,  # 1 day
) -> ArticleContent:
    """
    Extract article content from a URL or HTML content.
    
    This function orchestrates the entire extraction process, including
    fetching the content (if not provided), parsing, cleaning, and
    extracting metadata.
    
    Args:
        url: URL of the article
        cache_client: Cache client for storing/retrieving content
        thread_pool: Thread pool for CPU-bound operations
        html_content: Optional HTML content (if already fetched)
        use_cache: Whether to use cached content if available
        cache_ttl: Cache TTL in seconds
        
    Returns:
        ArticleContent: Extracted article content
        
    Raises:
        ValueError: If the article content cannot be extracted
    """
    start_time = time.time()
    logger.debug("Extracting article content", url=url)
    
    # Generate cache key
    cache_key = f"article_content:{url}"
    
    # Try to get from cache first
    if use_cache:
        cached_content = await cache_client.get(cache_key)
        if cached_content:
            if isinstance(cached_content, ArticleContent):
                logger.debug(
                    "Using cached article content",
                    url=url,
                    cached_at=cached_content.extracted_at,
                )
                return cached_content
            else:
                logger.warning(
                    "Invalid cached article content type",
                    url=url,
                    type=type(cached_content),
                )
    
    # Fetch HTML content if not provided
    if not html_content:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    timeout=30.0,
                )
                response.raise_for_status()
                html_content = response.text
        except Exception as e:
            logger.error("Error fetching article content", url=url, error=str(e))
            raise ValueError(f"Failed to fetch article content: {str(e)}")
    
    if not html_content:
        raise ValueError("Empty HTML content")
    
    # Extract content using readability (CPU-bound, run in thread pool)
    loop = asyncio.get_running_loop()
    try:
        document = await loop.run_in_executor(
            thread_pool,
            lambda: Document(html_content)
        )
        
        # Extract title and content
        title = document.title()
        content_html = document.summary()
        
        # Extract metadata
        metadata = await extract_article_metadata(
            html_content,
            url,
            title,
            thread_pool
        )
        
        # Clean and normalize content
        clean_text = await loop.run_in_executor(
            thread_pool,
            lambda: clean_article_text(content_html)
        )
        
        # Calculate word count
        word_count = len(clean_text.split())
        
        # Extract image URLs
        image_urls = await loop.run_in_executor(
            thread_pool,
            lambda: extract_image_urls(content_html, url)
        )
        
        # Create ArticleContent object
        article = ArticleContent(
            url=url,
            title=title,
            text=clean_text,
            html=content_html,
            author=metadata.get("author"),
            publish_date=metadata.get("publish_date"),
            summary=metadata.get("summary"),
            word_count=word_count,
            image_urls=image_urls,
            tags=metadata.get("tags", []),
            metadata=metadata,
            content_type=determine_content_type(clean_text, title, metadata),
        )
        
        # Cache the result
        if use_cache:
            await cache_client.set(cache_key, article, ttl=cache_ttl)
        
        elapsed = time.time() - start_time
        logger.debug(
            "Article content extracted successfully",
            url=url,
            title=title,
            word_count=word_count,
            elapsed_seconds=elapsed,
        )
        
        return article
    
    except Exception as e:
        logger.error("Error extracting article content", url=url, error=str(e))
        raise ValueError(f"Failed to extract article content: {str(e)}")


async def extract_main_content(
    html_content: str,
    thread_pool: ThreadPoolExecutor,
) -> Tuple[str, str]:
    """
    Extract the main content from HTML using readability.
    
    Args:
        html_content: HTML content
        thread_pool: Thread pool for CPU-bound operations
        
    Returns:
        Tuple[str, str]: Title and main content HTML
    """
    loop = asyncio.get_running_loop()
    
    try:
        # Use readability to extract main content (CPU-bound)
        document = await loop.run_in_executor(
            thread_pool,
            lambda: Document(html_content)
        )
        
        title = document.title()
        content = document.summary()
        
        return title, content
    
    except Exception as e:
        logger.error("Error extracting main content", error=str(e))
        
        # Fall back to BeautifulSoup if readability fails
        try:
            content = await loop.run_in_executor(
                thread_pool,
                lambda: extract_content_with_soup(html_content)
            )
            
            # Try to extract title with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            title = soup.title.string if soup.title else "Unknown Title"
            
            return title, content
        
        except Exception as fallback_error:
            logger.error("Fallback extraction failed", error=str(fallback_error))
            raise ValueError(f"Failed to extract content: {str(e)}")


def extract_content_with_soup(html_content: str) -> str:
    """
    Extract main content using BeautifulSoup as a fallback.
    
    This is used when readability fails to extract content.
    
    Args:
        html_content: HTML content
        
    Returns:
        str: Extracted content HTML
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove noise elements
    for element in NOISE_ELEMENTS:
        for node in soup.find_all(element):
            node.decompose()
    
    # Remove comments
    for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    # Try to find the main content container
    content = None
    
    # Try common article selectors
    for selector in ARTICLE_SELECTORS:
        content = soup.select_one(selector)
        if content and len(content.get_text(strip=True)) > 200:
            break
    
    # If no suitable container found, use the body
    if not content or len(content.get_text(strip=True)) < 200:
        content = soup.body
    
    # If still no content, use the entire document
    if not content:
        content = soup
    
    return str(content)


def clean_article_text(html_content: str) -> str:
    """
    Clean and normalize article text from HTML content.
    
    This function removes noise elements, normalizes whitespace,
    and extracts clean text from HTML.
    
    Args:
        html_content: HTML content
        
    Returns:
        str: Clean, normalized text
    """
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove noise elements
    for element in NOISE_ELEMENTS:
        for node in soup.find_all(element):
            node.decompose()
    
    # Remove comments
    for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    # Extract text with proper whitespace handling
    text_parts = []
    
    for element in soup.descendants:
        if isinstance(element, NavigableString) and element.strip():
            text_parts.append(element.strip())
        elif element.name == 'br' or element.name == 'p':
            text_parts.append('\n')
        elif element.name == 'h1' or element.name == 'h2' or element.name == 'h3':
            text_parts.append('\n\n')
    
    # Join text parts and normalize whitespace
    text = ' '.join(text_parts)
    
    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)
    
    # Replace multiple newlines with a maximum of two
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


async def extract_article_metadata(
    html_content: str,
    url: str,
    title: str,
    thread_pool: ThreadPoolExecutor,
) -> Dict[str, Any]:
    """
    Extract metadata from article HTML.
    
    Args:
        html_content: HTML content
        url: URL of the article
        title: Article title
        thread_pool: Thread pool for CPU-bound operations
        
    Returns:
        Dict[str, Any]: Extracted metadata
    """
    loop = asyncio.get_running_loop()
    
    # Extract metadata in thread pool (CPU-bound)
    metadata = await loop.run_in_executor(
        thread_pool,
        lambda: extract_metadata_sync(html_content, url, title)
    )
    
    return metadata


def extract_metadata_sync(html_content: str, url: str, title: str) -> Dict[str, Any]:
    """
    Extract metadata from article HTML (synchronous version).
    
    Args:
        html_content: HTML content
        url: URL of the article
        title: Article title
        
    Returns:
        Dict[str, Any]: Extracted metadata
    """
    metadata = {
        "url": url,
        "title": title,
        "domain": urlparse(url).netloc,
    }
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
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
        
        # Extract description/summary
        summary = extract_summary(soup)
        if summary:
            metadata["summary"] = summary
        
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


def extract_publish_date(soup: BeautifulSoup, html_content: str) -> Optional[datetime.datetime]:
    """
    Extract publication date from HTML.
    
    Args:
        soup: BeautifulSoup object
        html_content: Raw HTML content
        
    Returns:
        Optional[datetime.datetime]: Publication date if found, None otherwise
    """
    import datetime
    
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


def extract_summary(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract article summary/description from HTML.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Optional[str]: Summary if found, None otherwise
    """
    # Try meta description
    description = soup.find('meta', attrs={'name': 'description'})
    if description and description.get('content'):
        return description['content'].strip()
    
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
    
    # Try common summary classes
    for selector in ['.summary', '.excerpt', '.description', '.intro', '.lead']:
        summary_elem = soup.select_one(selector)
        if summary_elem:
            return summary_elem.get_text().strip()
    
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
    import json
    
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
                    
                    elif item_type == 'Person' and 'name' in item:
                        # Author information
                        jsonld_metadata['jsonld_person_name'] = item['name']
        
        except Exception as e:
            logger.warning("Error parsing JSON-LD", error=str(e))
    
    return jsonld_metadata


def extract_image_urls(html_content: str, base_url: str) -> List[str]:
    """
    Extract image URLs from HTML content.
    
    Args:
        html_content: HTML content
        base_url: Base URL for resolving relative URLs
        
    Returns:
        List[str]: List of image URLs
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    image_urls = []
    
    # Find all images
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src')
        if src:
            # Handle relative URLs
            if not src.startswith(('http://', 'https://')):
                src = urljoin(base_url, src)
            
            # Skip tiny images and icons
            if img.get('width') and img.get('height'):
                try:
                    width = int(img['width'])
                    height = int(img['height'])
                    if width < 100 or height < 100:
                        continue
                except ValueError:
                    pass
            
            image_urls.append(src)
    
    # Find background images in style attributes
    for element in soup.find_all(style=re.compile(r'background-image')):
        style = element.get('style', '')
        match = re.search(r'background-image:\s*url\([\'"]?([^\'"]+)[\'"]?\)', style)
        if match:
            src = match.group(1)
            if not src.startswith(('http://', 'https://')):
                src = urljoin(base_url, src)
            image_urls.append(src)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in image_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls


def determine_content_type(text: str, title: str, metadata: Dict[str, Any]) -> ContentType:
    """
    Determine the content type based on text, title, and metadata.
    
    Args:
        text: Article text
        title: Article title
        metadata: Article metadata
        
    Returns:
        ContentType: Determined content type
    """
    # Check metadata for explicit type information
    if metadata.get('og_type') == 'article':
        return ContentType.ARTICLE
    
    if metadata.get('jsonld_type') in ['BlogPosting', 'Blog']:
        return ContentType.BLOG_POST
    
    if metadata.get('jsonld_type') == 'TechArticle':
        return ContentType.DOCUMENTATION
    
    # Check title for content type hints
    title_lower = title.lower()
    
    if any(word in title_lower for word in ['tutorial', 'guide', 'how to', 'learn']):
        return ContentType.TUTORIAL
    
    if any(word in title_lower for word in ['release', 'version', 'update', 'changelog']):
        return ContentType.RELEASE_NOTES
    
    if any(word in title_lower for word in ['documentation', 'reference', 'manual']):
        return ContentType.DOCUMENTATION
    
    if any(word in title_lower for word in ['case study', 'success story']):
        return ContentType.CASE_STUDY
    
    # Check for blog post indicators
    if 'blog' in metadata.get('url', '').lower():
        return ContentType.BLOG_POST
    
    # Default to blog post for technical content
    return ContentType.BLOG_POST
