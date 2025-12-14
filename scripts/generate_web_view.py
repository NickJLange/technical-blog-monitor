#!/usr/bin/env python3
"""
Script to generate a premium HTML view of the cached blog post entries.
"""
import json
import pickle
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_cache_entries(cache_dir: Path) -> List[Dict[str, Any]]:
    """Load all blog post entries from the cache."""
    data_dir = cache_dir / "data"
    meta_dir = cache_dir / "meta"

    if not meta_dir.exists():
        print(f"Cache directory not found: {cache_dir}")
        return []

    posts = []
    print(f"Scanning cache directory: {meta_dir}")

    for meta_file in meta_dir.glob("*"):
        try:
            with open(meta_file, "r") as f:
                meta = json.loads(f.read())

            key = meta.get("key", "")
            if not key.startswith("article_content:"):
                continue

            value_type = meta.get("value_type")
            data_file = data_dir / meta_file.name

            if not data_file.exists():
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

            post_data = {}
            if isinstance(data, dict):
                post_data = data
            elif hasattr(data, "title") and hasattr(data, "url"):
                post_data = {
                    "title": getattr(data, "title", "No Title"),
                    "url": str(getattr(data, "url", "")),
                    "source": getattr(data, "metadata", {}).get("domain", "Unknown"),
                    "publish_date": getattr(data, "publish_date", None),
                    "extracted_at": getattr(data, "extracted_at", None),
                    "summary": getattr(data, "summary", "") or getattr(data, "content", "")[:200] + "..."
                }

                if hasattr(data, "metadata") and isinstance(data.metadata, dict):
                    if "feed_name" in data.metadata:
                        post_data["source"] = data.metadata["feed_name"]

            if post_data:
                if not post_data.get("publish_date"):
                    post_data["publish_date"] = meta.get("created_at")
                posts.append(post_data)

        except Exception:
            continue

    return posts

def format_date(dt_str_or_obj):
    """Format date for display."""
    if not dt_str_or_obj:
        return "N/A"

    dt = None
    if isinstance(dt_str_or_obj, (int, float)):
        dt = datetime.fromtimestamp(dt_str_or_obj)
    elif isinstance(dt_str_or_obj, str):
        try:
            dt = datetime.fromisoformat(dt_str_or_obj.replace('Z', '+00:00'))
        except ValueError:
            return dt_str_or_obj
    elif isinstance(dt_str_or_obj, datetime):
        dt = dt_str_or_obj

    if dt:
        return dt.strftime("%B %d, %Y")
    return str(dt_str_or_obj)

def generate_html(posts: List[Dict[str, Any]], output_file: Path):
    """Generate the HTML file."""

    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Technical Blog Monitor</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #6366f1;
            --accent-hover: #818cf8;
            --border: #334155;
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem;
        }
        
        header {
            max-width: 1200px;
            margin: 0 auto 3rem;
            text-align: center;
        }
        
        h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            background: linear-gradient(to right, #6366f1, #a855f7, #ec4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .stats {
            color: var(--text-secondary);
            font-size: 1.1rem;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 2rem;
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .card {
            background-color: var(--card-bg);
            border-radius: 1rem;
            padding: 1.5rem;
            border: 1px solid var(--border);
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex;
            flex-direction: column;
            height: 100%;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.3);
            border-color: var(--accent);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        
        .source {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            background: rgba(99, 102, 241, 0.1);
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
        }
        
        .date {
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        .card-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            line-height: 1.4;
        }
        
        .card-title a {
            color: var(--text-primary);
            text-decoration: none;
            transition: color 0.2s;
        }
        
        .card-title a:hover {
            color: var(--accent-hover);
        }
        
        .card-summary {
            color: var(--text-secondary);
            font-size: 0.95rem;
            flex-grow: 1;
            margin-bottom: 1.5rem;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        
        .card-footer {
            margin-top: auto;
            pt: 1rem;
            border-top: 1px solid var(--border);
            padding-top: 1rem;
        }
        
        .read-more {
            display: inline-flex;
            align-items: center;
            color: var(--accent);
            text-decoration: none;
            font-weight: 500;
            font-size: 0.9rem;
            transition: color 0.2s;
        }
        
        .read-more:hover {
            color: var(--accent-hover);
        }
        
        .read-more svg {
            margin-left: 0.5rem;
            width: 16px;
            height: 16px;
        }

        .search-container {
            max-width: 600px;
            margin: 0 auto 2rem;
            position: relative;
        }

        .search-input {
            width: 100%;
            padding: 1rem 1.5rem;
            border-radius: 9999px;
            border: 1px solid var(--border);
            background-color: var(--card-bg);
            color: var(--text-primary);
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        .search-input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }

        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
            h1 {
                font-size: 2rem;
            }
        }
    </style>
</head>
<body>
    <header>
        <h1>Technical Blog Monitor</h1>
        <p class="stats">Monitoring 32 Engineering Blogs • {total_count} Articles Cached</p>
    </header>

    <div class="search-container">
        <input type="text" id="searchInput" class="search-input" placeholder="Search articles by title or source...">
    </div>

    <div class="grid" id="articleGrid">
        {articles_html}
    </div>

    <script>
        const searchInput = document.getElementById('searchInput');
        const articleGrid = document.getElementById('articleGrid');
        const cards = document.querySelectorAll('.card');

        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            
            cards.forEach(card => {
                const title = card.querySelector('.card-title').textContent.toLowerCase();
                const source = card.querySelector('.source').textContent.toLowerCase();
                
                if (title.includes(searchTerm) || source.includes(searchTerm)) {
                    card.style.display = 'flex';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    </script>
</body>
</html>
    """

    articles_html = ""
    for post in posts:
        source = post.get("source", "Unknown")
        title = post.get("title", "No Title")
        url = post.get("url", "#")
        date_str = format_date(post.get("publish_date"))
        summary = post.get("summary", "")

        # Clean up summary if it's too raw
        if len(summary) > 200:
            summary = summary[:197] + "..."

        article_html = f"""
        <article class="card">
            <div class="card-header">
                <span class="source">{source}</span>
                <span class="date">{date_str}</span>
            </div>
            <h2 class="card-title">
                <a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
            </h2>
            <p class="card-summary">{summary}</p>
            <div class="card-footer">
                <a href="{url}" target="_blank" rel="noopener noreferrer" class="read-more">
                    Read Article
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                </a>
            </div>
        </article>
        """
        articles_html += article_html

    final_html = html_template.replace(
        "{total_count}", str(len(posts))
    ).replace(
        "{articles_html}", articles_html
    )

    with open(output_file, "w") as f:
        f.write(final_html)

    print(f"Generated HTML view at: {output_file.absolute()}")

def main():
    # Paths relative to project root
    project_root = Path(__file__).parent.parent
    cache_dir = project_root / "cache"

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

    output_file = project_root / "data" / "artifacts" / "latest_articles.html"
    # Ensure directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    generate_html(posts, output_file)

    # Try to open in browser
    try:
        webbrowser.open(f"file://{output_file.absolute()}")
        print("Opened in default browser.")
    except Exception as e:
        print(f"Could not open browser: {e}")
        print(f"Please open {output_file.absolute()} manually.")

if __name__ == "__main__":
    main()
