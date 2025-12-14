"""
Feed processing package for the technical blog monitor.

This package handles the discovery and processing of blog feeds from various sources,
including RSS/Atom feeds and JSON endpoints. It provides functionality to check for
new posts, parse feed entries, and convert them to BlogPost objects for further processing.

The main entry point is the `process_feed_posts` function, which handles the entire
feed processing pipeline from discovery to post extraction.
"""
from monitor.feeds.atom import AtomFeedProcessor
from monitor.feeds.base import (
    discover_new_posts,
    get_feed_processor,
    parse_feed_entries,
    process_feed_posts,
)
from monitor.feeds.json import JSONFeedProcessor
from monitor.feeds.rss import RSSFeedProcessor

__all__ = [
    "process_feed_posts",
    "get_feed_processor",
    "discover_new_posts",
    "parse_feed_entries",
    "RSSFeedProcessor",
    "AtomFeedProcessor",
    "JSONFeedProcessor",
]
