"""
Technical Blog Monitor

A daemon that monitors technical blogs, renders pages, and generates embeddings for vector search.
"""

__version__ = "0.1.0"
__author__ = "Technical Blog Monitor Team"
__description__ = "A system for monitoring technical blogs and generating embeddings"
__license__ = "MIT"

# Package level constants
DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_CACHE_DIR = "cache"
DEFAULT_DATA_DIR = "data"

# Version info tuple
VERSION_INFO = tuple(map(int, __version__.split('.')))
