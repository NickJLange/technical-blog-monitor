"""
Image extractor module for the technical blog monitor.

This module provides functionality for extracting and downloading images
from web pages, including finding the main image, extracting all images,
and downloading images for further processing.
"""
import asyncio
import os
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Set up structured logger
logger = structlog.get_logger()


async def extract_images(
    html_content: str,
    base_url: str,
    min_width: int = 100,
    min_height: int = 100,
) -> List[dict]:
    """
    Extract images from HTML content.
    
    Args:
        html_content: HTML content
        base_url: Base URL for resolving relative URLs
        min_width: Minimum image width to include
        min_height: Minimum image height to include
        
    Returns:
        List[dict]: List of image information dictionaries
    """
    logger.debug("Extracting images from HTML content")
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        images = []
        
        # Find all images
        for img in soup.find_all('img'):
            # Get image source
            src = img.get('src') or img.get('data-src')
            if not src:
                continue
            
            # Resolve relative URLs
            if not src.startswith(('http://', 'https://')):
                src = urljoin(base_url, src)
            
            # Get image dimensions
            width = img.get('width')
            height = img.get('height')
            
            # Convert dimensions to integers if possible
            try:
                width = int(width) if width else None
                height = int(height) if height else None
            except ValueError:
                width = None
                height = None
            
            # Skip small images if dimensions are available
            if width and height and (width < min_width or height < min_height):
                continue
            
            # Get alt text
            alt = img.get('alt', '')
            
            # Create image info dictionary
            image_info = {
                'src': src,
                'alt': alt,
                'width': width,
                'height': height,
            }
            
            images.append(image_info)
        
        logger.debug("Extracted images", count=len(images))
        return images
    
    except Exception as e:
        logger.error("Error extracting images", error=str(e))
        return []


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def download_image(
    url: str,
    output_dir: Path,
    filename: Optional[str] = None,
    timeout: float = 30.0,
) -> Optional[Path]:
    """
    Download an image from a URL.
    
    Args:
        url: Image URL
        output_dir: Directory to save the image
        filename: Optional filename (if not provided, derived from URL)
        timeout: Request timeout in seconds
        
    Returns:
        Optional[Path]: Path to the downloaded image, None if download failed
    """
    logger.debug("Downloading image", url=url)
    
    try:
        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine filename if not provided
        if not filename:
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            
            # If filename is empty or doesn't have an extension, use a default
            if not filename or '.' not in filename:
                filename = f"image_{hash(url) % 10000}.jpg"
        
        # Ensure filename has an extension
        if '.' not in filename:
            filename += '.jpg'
        
        # Create output path
        output_path = output_dir / filename
        
        # Download the image
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
            
            # Check if the response is an image
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                logger.warning(
                    "URL does not point to an image",
                    url=url,
                    content_type=content_type,
                )
                return None
            
            # Save the image
            async with open(output_path, 'wb') as f:
                f.write(response.content)
            
            logger.debug(
                "Image downloaded successfully",
                url=url,
                path=str(output_path),
            )
            
            return output_path
    
    except Exception as e:
        logger.error("Error downloading image", url=url, error=str(e))
        return None


async def get_main_image(
    html_content: str,
    base_url: str,
    output_dir: Optional[Path] = None,
    download: bool = False,
) -> Optional[dict]:
    """
    Get the main image from a page.
    
    This function attempts to find the most prominent image on a page,
    such as a featured image, hero image, or Open Graph image.
    
    Args:
        html_content: HTML content
        base_url: Base URL for resolving relative URLs
        output_dir: Directory to save the image if download is True
        download: Whether to download the image
        
    Returns:
        Optional[dict]: Main image information, None if no suitable image found
    """
    logger.debug("Finding main image")
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        main_image = None
        
        # Try Open Graph image first
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            src = og_image['content']
            if not src.startswith(('http://', 'https://')):
                src = urljoin(base_url, src)
            
            main_image = {
                'src': src,
                'alt': 'Open Graph image',
                'width': None,
                'height': None,
                'type': 'og_image',
            }
        
        # If no Open Graph image, try Twitter Card image
        if not main_image:
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image and twitter_image.get('content'):
                src = twitter_image['content']
                if not src.startswith(('http://', 'https://')):
                    src = urljoin(base_url, src)
                
                main_image = {
                    'src': src,
                    'alt': 'Twitter Card image',
                    'width': None,
                    'height': None,
                    'type': 'twitter_image',
                }
        
        # If still no image, try common featured image classes
        if not main_image:
            for selector in [
                '.featured-image img',
                '.post-thumbnail img',
                '.entry-image img',
                'article img:first-of-type',
                '.post img:first-of-type',
                'img.wp-post-image',
            ]:
                img = soup.select_one(selector)
                if img and img.get('src'):
                    src = img['src']
                    if not src.startswith(('http://', 'https://')):
                        src = urljoin(base_url, src)
                    
                    main_image = {
                        'src': src,
                        'alt': img.get('alt', ''),
                        'width': img.get('width'),
                        'height': img.get('height'),
                        'type': 'featured_image',
                    }
                    break
        
        # If still no image, use the first large image
        if not main_image:
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if not src:
                    continue
                
                # Skip small images and icons
                width = img.get('width')
                height = img.get('height')
                try:
                    width = int(width) if width else None
                    height = int(height) if height else None
                except ValueError:
                    width = None
                    height = None
                
                if width and height and (width < 200 or height < 200):
                    continue
                
                # Resolve relative URL
                if not src.startswith(('http://', 'https://')):
                    src = urljoin(base_url, src)
                
                main_image = {
                    'src': src,
                    'alt': img.get('alt', ''),
                    'width': width,
                    'height': height,
                    'type': 'first_large_image',
                }
                break
        
        # Download the image if requested
        if main_image and download and output_dir:
            path = await download_image(main_image['src'], output_dir)
            if path:
                main_image['local_path'] = str(path)
        
        return main_image
    
    except Exception as e:
        logger.error("Error finding main image", error=str(e))
        return None
