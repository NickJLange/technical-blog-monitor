#!/usr/bin/env python3
"""Generate HTML web view from vector database entries."""
import asyncio
import sys
import webbrowser
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from monitor.config import load_settings
from monitor.vectordb import get_vector_db_client

async def generate_html(records):
    """Generate HTML from records."""
    # Sort by publish_date (newest first)
    records.sort(key=lambda r: r.publish_date if r.publish_date else datetime.min, reverse=True)
    
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Technical Blog Monitor</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 40px 20px;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            
            header {
                text-align: center;
                color: white;
                margin-bottom: 40px;
            }
            
            header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            
            header p {
                font-size: 1.1em;
                opacity: 0.9;
            }
            
            .articles-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
                gap: 24px;
                margin-bottom: 40px;
            }
            
            .article-card {
                background: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
                transition: transform 0.3s ease, box-shadow 0.3s ease;
                display: flex;
                flex-direction: column;
            }
            
            .article-card:hover {
                transform: translateY(-8px);
                box-shadow: 0 15px 40px rgba(0, 0, 0, 0.3);
            }
            
            .article-header {
                padding: 24px 24px 16px;
                border-bottom: 2px solid #f0f0f0;
            }
            
            .article-title {
                font-size: 1.3em;
                font-weight: 600;
                color: #1a1a1a;
                margin-bottom: 8px;
                line-height: 1.4;
            }
            
            .article-meta {
                font-size: 0.85em;
                color: #666;
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                margin-bottom: 8px;
            }
            
            .meta-item {
                display: flex;
                align-items: center;
                gap: 4px;
            }
            
            .article-body {
                padding: 20px 24px;
                flex-grow: 1;
                display: flex;
                flex-direction: column;
            }
            
            .summary-label {
                font-size: 0.75em;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #667eea;
                margin-bottom: 8px;
            }
            
            .article-summary {
                font-size: 0.95em;
                color: #555;
                line-height: 1.6;
                margin-bottom: 12px;
                flex-grow: 1;
            }
            
            .article-tags {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                margin-top: 12px;
            }
            
            .tag {
                display: inline-block;
                background: #f0f0f0;
                color: #667eea;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.75em;
                font-weight: 500;
            }
            
            .article-footer {
                padding: 16px 24px 20px;
                border-top: 1px solid #f0f0f0;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .read-more {
                display: inline-block;
                color: #667eea;
                font-weight: 600;
                font-size: 0.95em;
                text-decoration: none;
                transition: color 0.2s ease;
            }
            
            .read-more:hover {
                color: #764ba2;
                text-decoration: underline;
            }
            
            .source-badge {
                background: #667eea;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.75em;
                font-weight: 600;
            }
            
            .empty-state {
                text-align: center;
                padding: 60px 20px;
                color: white;
            }
            
            .empty-state h2 {
                font-size: 1.8em;
                margin-bottom: 10px;
            }
            
            .stats {
                text-align: center;
                color: white;
                margin-bottom: 20px;
                font-size: 1.1em;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🚀 Technical Blog Monitor</h1>
                <p>Latest articles from the world's best tech blogs</p>
            </header>
            
            <div class="stats">
                <strong>{count}</strong> articles tracked
            </div>
    """
    
    if not records:
        html_content += """
            <div class="empty-state">
                <h2>No articles found</h2>
                <p>Run the monitor to start collecting articles.</p>
            </div>
        """
    else:
        html_content += '<div class="articles-grid">\n'
        
        for record in records:
            # Format date
            pub_date = record.publish_date.strftime("%b %d, %Y") if record.publish_date else "Unknown"
            
            # Prepare summary
            summary = record.summary or record.get_summary() or "No summary available"
            if len(summary) > 300:
                summary = summary[:297] + "..."
            
            # Prepare author (fallback to source if not found)
            author = record.author or record.source or "Unknown"
            
            # Prepare source
            source = record.source or "Unknown"
            
            # Get tags from metadata
            tags = record.metadata.get("tags", []) if record.metadata else []
            tags_html = ''.join(f'<span class="tag">{tag}</span>' for tag in tags[:3]) if tags else ''
            
            html_content += f"""
            <div class="article-card">
                <div class="article-header">
                    <h3 class="article-title">{record.title}</h3>
                    <div class="article-meta">
                        <span class="meta-item">📅 {pub_date}</span>
                        <span class="meta-item">✍️ {author}</span>
                    </div>
                </div>
                
                <div class="article-body">
                    <div class="summary-label">AI Summary</div>
                    <p class="article-summary">{summary}</p>
                    <div class="article-tags">
                        {tags_html}
                    </div>
                </div>
                
                <div class="article-footer">
                    <a href="{record.url}" class="read-more" target="_blank">Read Article →</a>
                    <span class="source-badge">{source}</span>
                </div>
            </div>
            """
        
        html_content += '</div>\n'
    
    html_content += """
        </div>
    </body>
    </html>
    """
    
    return html_content.replace("{count}", str(len(records)))

async def main():
    """Main function."""
    settings = load_settings()
    vdb = await get_vector_db_client(settings.vector_db)
    
    # Fetch all records
    records = await vdb.list_all(limit=1000)
    
    print(f"Found {len(records)} records in database")
    
    if not records:
        print("No records found. Run the monitor first.")
        return
    
    # Generate HTML
    html = await generate_html(records)
    
    # Write to file
    output_file = Path("latest_articles.html")
    with open(output_file, "w") as f:
        f.write(html)
    
    print(f"Generated {output_file}")
    
    # Try to open in browser
    try:
        webbrowser.open(f"file://{output_file.absolute()}")
        print("Opened in default browser.")
    except Exception as e:
        print(f"Could not open browser: {e}")
        print(f"Please open {output_file.absolute()} manually.")

if __name__ == "__main__":
    asyncio.run(main())
