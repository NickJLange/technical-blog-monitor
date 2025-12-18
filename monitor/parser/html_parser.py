"""
HTML parsing abstraction layer using justhtml.

This module provides a clean abstraction for HTML parsing that works with
both the new justhtml library and maintains compatibility with existing
BeautifulSoup-based code patterns.

justhtml provides:
- 100% HTML5 spec compliance (passes all 9k+ html5lib tests)
- Pure Python (zero C dependencies)
- CSS selector support (familiar syntax)
- Better performance than BeautifulSoup for large-scale parsing
"""
from typing import Any, Dict, List, Optional, Union

import structlog
from justhtml import JustHTML

# Set up structured logger
logger = structlog.get_logger()


class HTMLElement:
    """
    Wrapper around justhtml elements that provides a BeautifulSoup-like API.
    
    This allows gradual migration from BeautifulSoup while maintaining
    compatibility with existing code.
    """
    
    def __init__(self, element: Any):
        """Initialize with a justhtml element."""
        self._element = element
    
    @property
    def name(self) -> Optional[str]:
        """Get the tag name."""
        return self._element.name if hasattr(self._element, 'name') else None
    
    @property
    def attrs(self) -> Dict[str, Any]:
        """Get element attributes as a dictionary."""
        if hasattr(self._element, 'attrs'):
            return self._element.attrs or {}
        return {}
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get an attribute value."""
        attrs = self.attrs
        if isinstance(attrs, dict):
            return attrs.get(key, default)
        return default
    
    def __getitem__(self, key: str) -> Any:
        """Get an attribute using bracket notation."""
        return self.attrs.get(key)
    
    def find(self, name: Optional[str] = None, **kwargs) -> Optional['HTMLElement']:
        """Find the first matching child element."""
        try:
            # Build CSS selector from name and kwargs
            selector = self._build_selector(name, kwargs)
            results = self._element.query(selector) if selector else []
            if results:
                return HTMLElement(results[0])
        except Exception as e:
            logger.debug("Error in find()", error=str(e))
        return None
    
    def find_all(self, name: Optional[str] = None, **kwargs) -> List['HTMLElement']:
        """Find all matching child elements."""
        try:
            selector = self._build_selector(name, kwargs)
            results = self._element.query(selector) if selector else []
            return [HTMLElement(elem) for elem in results]
        except Exception as e:
            logger.debug("Error in find_all()", error=str(e))
        return []
    
    def find_next(self, name: Optional[str] = None, **kwargs) -> Optional['HTMLElement']:
        """Find the next matching sibling element."""
        try:
            # justhtml doesn't have find_next, so traverse siblings manually
            current = self._element
            while hasattr(current, 'next_sibling'):
                current = current.next_sibling
                if current is None:
                    break
                if self._matches(current, name, kwargs):
                    return HTMLElement(current)
        except Exception:
            pass
        return None
    
    def get_text(self, separator: str = '', strip: bool = False) -> str:
        """Get all text content from this element and children."""
        try:
            if hasattr(self._element, 'text'):
                text = self._element.text
            elif hasattr(self._element, 'get_text'):
                text = self._element.get_text(separator=separator, strip=strip)
            else:
                text = str(self._element)
            
            if strip:
                text = text.strip()
            return text
        except Exception as e:
            logger.debug("Error in get_text()", error=str(e))
            return ""
    
    @property
    def parent(self) -> Optional['HTMLElement']:
        """Get the parent element."""
        if hasattr(self._element, 'parent'):
            parent = self._element.parent
            return HTMLElement(parent) if parent else None
        return None
    
    @property
    def next_sibling(self) -> Optional['HTMLElement']:
        """Get the next sibling element."""
        if hasattr(self._element, 'next_sibling'):
            sibling = self._element.next_sibling
            return HTMLElement(sibling) if sibling else None
        return None
    
    def __str__(self) -> str:
        """Return HTML representation."""
        return str(self._element)
    
    @staticmethod
    def _build_selector(name: Optional[str], kwargs: Dict[str, Any]) -> str:
        """Build a CSS selector from tag name and attributes."""
        selector_parts = []
        
        if name:
            selector_parts.append(name)
        
        # Handle 'attrs' dict for BeautifulSoup compatibility
        attrs_dict = kwargs.pop('attrs', {}) if 'attrs' in kwargs else {}
        # Merge attrs into kwargs for unified handling
        for k, v in attrs_dict.items():
            if k not in kwargs:
                kwargs[k] = v
        
        # Handle class attribute
        if 'class' in kwargs:
            classes = kwargs['class']
            if isinstance(classes, str):
                selector_parts.append('.' + classes.replace(' ', '.'))
            elif isinstance(classes, list):
                selector_parts.extend('.' + c for c in classes)
        
        # Handle id attribute
        if 'id' in kwargs:
            selector_parts.append('#' + kwargs['id'])
        
        # Handle rel attribute for links
        if 'rel' in kwargs:
            rel_val = kwargs['rel']
            if isinstance(rel_val, (list, tuple)):
                rel_val = ' '.join(rel_val)
            selector_parts.append(f'[rel="{rel_val}"]')
        
        # Handle type attribute
        if 'type' in kwargs:
            selector_parts.append(f'[type="{kwargs["type"]}"]')
        
        # Handle property attribute (for Open Graph meta tags)
        if 'property' in kwargs:
            selector_parts.append(f'[property="{kwargs["property"]}"]')
        
        # Handle name attribute (for meta tags like twitter:image)
        if 'name' in kwargs:
            selector_parts.append(f'[name="{kwargs["name"]}"]')
        
        # Handle itemprop attribute (for schema.org markup)
        if 'itemprop' in kwargs:
            selector_parts.append(f'[itemprop="{kwargs["itemprop"]}"]')
        
        # Handle content attribute
        if 'content' in kwargs:
            selector_parts.append(f'[content="{kwargs["content"]}"]')
        
        return ''.join(selector_parts) if selector_parts else ''
    
    @staticmethod
    def _matches(element: Any, name: Optional[str], kwargs: Dict[str, Any]) -> bool:
        """Check if an element matches the given criteria."""
        if name and (not hasattr(element, 'name') or element.name != name):
            return False
        
        if 'class' in kwargs:
            elem_classes = element.attrs.get('class', [])
            if isinstance(elem_classes, str):
                elem_classes = elem_classes.split()
            
            match_classes = kwargs['class']
            if isinstance(match_classes, str):
                match_classes = [match_classes]
            
            if not any(c in elem_classes for c in match_classes):
                return False
        
        return True


class HTMLParser:
    """
    Main HTML parser class using justhtml.
    
    Provides a simple, clean API for HTML parsing with CSS selectors.
    """
    
    def __init__(self, content: Union[str, bytes]):
        """
        Initialize the parser with HTML content.
        
        Args:
            content: HTML content as string or bytes
        """
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        
        try:
            self.doc = JustHTML(content)
            self.root = self.doc
        except Exception as e:
            logger.warning("Error parsing HTML with justhtml", error=str(e))
            self.doc = None
            self.root = None
    
    def find(self, name: Optional[str] = None, **kwargs) -> Optional[HTMLElement]:
        """Find the first element matching the criteria."""
        if not self.root:
            return None
        
        try:
            # Build CSS selector
            selector = self._build_selector(name, kwargs)
            results = self.root.query(selector) if selector else []
            if results:
                return HTMLElement(results[0])
        except Exception as e:
            logger.debug("Error in find()", error=str(e))
        
        return None
    
    def find_all(self, name: Optional[str] = None, **kwargs) -> List[HTMLElement]:
        """Find all elements matching the criteria."""
        if not self.root:
            return []
        
        try:
            selector = self._build_selector(name, kwargs)
            results = self.root.query(selector) if selector else []
            return [HTMLElement(elem) for elem in results]
        except Exception as e:
            logger.debug("Error in find_all()", error=str(e))
        
        return []
    
    def select(self, selector: str) -> List[HTMLElement]:
        """Select elements using CSS selector syntax."""
        if not self.root:
            return []
        
        try:
            results = self.root.query(selector)
            return [HTMLElement(elem) for elem in results]
        except Exception as e:
            logger.debug("Error in select()", error=str(e))
        
        return []
    
    def select_one(self, selector: str) -> Optional[HTMLElement]:
        """Select the first element matching the CSS selector."""
        results = self.select(selector)
        return results[0] if results else None
    
    def get_text(self) -> str:
        """Get all text content from the document."""
        if not self.root:
            return ""
        
        try:
            if hasattr(self.root, 'text'):
                return self.root.text
        except Exception as e:
            logger.debug("Error getting document text", error=str(e))
        
        return ""
    
    @staticmethod
    def _build_selector(name: Optional[str], kwargs: Dict[str, Any]) -> str:
        """Build a CSS selector from tag name and attributes."""
        selector_parts = []
        
        if name:
            selector_parts.append(name)
        
        # Handle 'attrs' dict for BeautifulSoup compatibility
        attrs_dict = kwargs.pop('attrs', {}) if 'attrs' in kwargs else {}
        # Merge attrs into kwargs for unified handling
        for k, v in attrs_dict.items():
            if k not in kwargs:
                kwargs[k] = v
        
        # Handle class attribute
        if 'class' in kwargs:
            classes = kwargs['class']
            if isinstance(classes, str):
                selector_parts.append('.' + classes.replace(' ', '.'))
            elif isinstance(classes, list):
                selector_parts.extend('.' + c for c in classes)
        
        # Handle id attribute
        if 'id' in kwargs:
            selector_parts.append('#' + kwargs['id'])
        
        # Handle rel attribute
        if 'rel' in kwargs:
            rel_val = kwargs['rel']
            if isinstance(rel_val, (list, tuple)):
                rel_val = ' '.join(rel_val)
            selector_parts.append(f'[rel="{rel_val}"]')
        
        # Handle type attribute
        if 'type' in kwargs:
            selector_parts.append(f'[type="{kwargs["type"]}"]')
        
        # Handle property attribute (for Open Graph meta tags)
        if 'property' in kwargs:
            selector_parts.append(f'[property="{kwargs["property"]}"]')
        
        # Handle name attribute (for meta tags like twitter:image)
        if 'name' in kwargs:
            selector_parts.append(f'[name="{kwargs["name"]}"]')
        
        # Handle itemprop attribute (for schema.org markup)
        if 'itemprop' in kwargs:
            selector_parts.append(f'[itemprop="{kwargs["itemprop"]}"]')
        
        # Handle content attribute
        if 'content' in kwargs:
            selector_parts.append(f'[content="{kwargs["content"]}"]')
        
        return ''.join(selector_parts) if selector_parts else ''


def parse_html(content: Union[str, bytes]) -> HTMLParser:
    """
    Parse HTML content and return a parser object.
    
    This is the main entry point for HTML parsing.
    
    Args:
        content: HTML content as string or bytes
        
    Returns:
        HTMLParser: A parser object that can be used to query the HTML
    """
    return HTMLParser(content)
