#!/usr/bin/env python3
"""
Script to view the latest blog post entries from the cache.
"""
import json
import pickle
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from monitor.models.article import ArticleContent
except ImportError:
    # Define a dummy class if import fails, though it shouldn't
    class ArticleContent:
        pass

def load_cache_entries(cache_dir: Path) -> List[Dict[str, Any]]:
    """Load all blog post entries from the cache."""
    data_dir = cache_dir / "data"
    meta_dir = cache_dir / "meta"
    
    if not meta_dir.exists():
        print(f"Cache directory not found: {cache_dir}")
        return []
    
    posts = []
    
    # print(f"Scanning cache directory: {meta_dir}")
    count = 0
    article_count = 0
    
    for meta_file in meta_dir.glob("*"):
        try:
            # Read metadata
            with open(meta_file, "r") as f:
                meta = json.loads(f.read())
            
            key = meta.get("key", "")
            
            # Look for article content
            if not key.startswith("article_content:"):
                continue
                
            value_type = meta.get("value_type")
            data_file = data_dir / meta_file.name
            
            if not data_file.exists():
                # print(f"Data file missing for {meta_file.name}")
                continue
                
            data = None
            if value_type == "json":
                with open(data_file, "r") as f:
                    data = json.loads(f.read())
            elif value_type == "pickle":
                with open(data_file, "rb") as f:
                    data = pickle.load(f)
            elif value_type == "string":
                with open(data_file, "r") as f:
                    data = f.read()
            
            # Extract data
            post_data = {}
            
            if isinstance(data, dict):
                post_data = data
            elif hasattr(data, "title") and hasattr(data, "url"):
                # Pydantic model
                post_data = {
                    "title": getattr(data, "title", "No Title"),
                    "url": str(getattr(data, "url", "")),
                    "source": getattr(data, "metadata", {}).get("domain", "Unknown"),
                    "publish_date": getattr(data, "publish_date", None),
                    "extracted_at": getattr(data, "extracted_at", None)
                }
                
                # Try to get better source from metadata
                if hasattr(data, "metadata") and isinstance(data.metadata, dict):
                    if "feed_name" in data.metadata:
                        post_data["source"] = data.metadata["feed_name"]
            
            if post_data:
                # Ensure we have a date for sorting
                if not post_data.get("publish_date"):
                    post_data["publish_date"] = meta.get("created_at")
                
                posts.append(post_data)
                article_count += 1
                
            count += 1
            
        except Exception:
            # print(f"Error reading {meta_file}: {e}")
            continue
            
    # print(f"Found {article_count} cached articles.")
    return posts

def format_date(dt_str_or_obj):
    """Format date for display."""
    if not dt_str_or_obj:
        return "N/A"
    
    if isinstance(dt_str_or_obj, (int, float)):
        return datetime.fromtimestamp(dt_str_or_obj).strftime("%Y-%m-%d %H:%M")
    
    if isinstance(dt_str_or_obj, str):
        try:
            # Try parsing ISO format
            dt = datetime.fromisoformat(dt_str_or_obj.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M")
        except:
            return dt_str_or_obj
            
    if isinstance(dt_str_or_obj, datetime):
        return dt_str_or_obj.strftime("%Y-%m-%d %H:%M")
        
    return str(dt_str_or_obj)

def main():
    cache_dir = Path("cache")
    posts = load_cache_entries(cache_dir)
    
    if not posts:
        print("No articles found in cache.")
        return
    
    # Sort by publish_date, descending
    def get_sort_key(p):
        d = p.get("publish_date")
        if isinstance(d, (int, float)):
            return d
        if isinstance(d, str):
            try:
                return datetime.fromisoformat(d.replace('Z', '+00:00')).timestamp()
            except:
                return 0
        if isinstance(d, datetime):
            return d.timestamp()
        return 0
        
    posts.sort(key=get_sort_key, reverse=True)
    
    print("\n" + "="*100)
    print(f"LATEST 32 ARTICLES (Total: {len(posts)})")
    print("="*100)
    print(f"{'#':<3} | {'Date':<16} | {'Source':<25} | {'Title'}")
    print("-" * 100)
    
    for i, post in enumerate(posts[:32]):
        date_str = format_date(post.get("publish_date"))
        source = post.get("source", "Unknown")
        if len(source) > 25:
            source = source[:22] + "..."
            
        title = post.get("title", "No Title")
        if len(title) > 50:
            title = title[:47] + "..."
            
        print(f"{i+1:<3} | {date_str:<16} | {source:<25} | {title}")
        
    print("-" * 100)
    print("Run './view_latest_entries.py' to see this list again.")

if __name__ == "__main__":
    main()
