"""
FastAPI-based web dashboard for the technical blog monitor.

This module provides a web interface to browse and search discovered blog posts.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Set up structured logger
logger = structlog.get_logger()


class PostSummary(BaseModel):
    """Summary model for displaying posts in the dashboard."""
    id: str
    title: str
    url: str
    source: str
    author: Optional[str] = None
    publish_date: Optional[datetime] = None
    summary: Optional[str] = None
    tags: List[str] = []
    word_count: Optional[int] = None


class DashboardStats(BaseModel):
    """Statistics for the dashboard."""
    total_posts: int
    posts_today: int
    posts_week: int
    sources: List[str]
    latest_update: Optional[datetime] = None


def create_app(settings=None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Technical Blog Monitor",
        description="Dashboard for monitoring technical blog posts",
        version="1.0.0"
    )
    
    # Store settings in app state
    app.state.settings = settings
    app.state.vector_db_client = None
    
    @app.on_event("startup")
    async def startup_event():
        """Initialize resources on startup."""
        logger.info("Starting web dashboard...")
        if settings:
            try:
                from monitor.vectordb import get_vector_db_client
                app.state.vector_db_client = await get_vector_db_client(settings.vector_db)
                logger.info("Connected to vector database")
            except Exception as e:
                logger.warning(f"Could not connect to vector DB: {e}, using mock data")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Clean up resources on shutdown."""
        if app.state.vector_db_client:
            await app.state.vector_db_client.close()
    
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """Home page showing dashboard overview."""
        # Simple HTML dashboard
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Technical Blog Monitor</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                    background: #f5f5f5;
                }
                h1 { color: #333; }
                .stats {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 30px 0;
                }
                .stat-card {
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .stat-number {
                    font-size: 2em;
                    font-weight: bold;
                    color: #2563eb;
                }
                .stat-label {
                    color: #666;
                    margin-top: 5px;
                }
                .posts-list {
                    background: white;
                    border-radius: 8px;
                    padding: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .post-item {
                    padding: 15px 0;
                    border-bottom: 1px solid #eee;
                }
                .post-item:last-child {
                    border-bottom: none;
                }
                .post-title {
                    font-size: 1.1em;
                    color: #2563eb;
                    text-decoration: none;
                    font-weight: 500;
                }
                .post-meta {
                    color: #666;
                    font-size: 0.9em;
                    margin-top: 5px;
                }
                .nav {
                    display: flex;
                    gap: 20px;
                    margin-bottom: 30px;
                    padding-bottom: 15px;
                    border-bottom: 2px solid #e5e5e5;
                }
                .nav a {
                    color: #666;
                    text-decoration: none;
                    font-weight: 500;
                }
                .nav a:hover {
                    color: #2563eb;
                }
            </style>
        </head>
        <body>
            <h1>📚 Technical Blog Monitor Dashboard</h1>
            
            <div class="nav">
                <a href="/">Dashboard</a>
                <a href="/api/stats">API Stats</a>
                <a href="/api/posts">API Posts</a>
                <a href="/health">Health Check</a>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number" id="total-posts">0</div>
                    <div class="stat-label">Total Posts</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="posts-today">0</div>
                    <div class="stat-label">Posts Today</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="posts-week">0</div>
                    <div class="stat-label">Posts This Week</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="sources">0</div>
                    <div class="stat-label">Active Sources</div>
                </div>
            </div>
            
            <div class="posts-list">
                <h2>Recent Posts</h2>
                <div id="posts-container">
                    <p>Loading posts...</p>
                </div>
            </div>
            
            <script>
                async function loadDashboard() {
                    try {
                        // Load stats
                        const statsResponse = await fetch('/api/stats');
                        const stats = await statsResponse.json();
                        
                        document.getElementById('total-posts').textContent = stats.total_posts;
                        document.getElementById('posts-today').textContent = stats.posts_today;
                        document.getElementById('posts-week').textContent = stats.posts_week;
                        document.getElementById('sources').textContent = stats.sources.length;
                        
                        // Load recent posts
                        const postsResponse = await fetch('/api/posts?per_page=10');
                        const postsData = await postsResponse.json();
                        
                        const container = document.getElementById('posts-container');
                        if (postsData.posts.length === 0) {
                            container.innerHTML = '<p>No posts found. Run the monitor to discover posts!</p>';
                        } else {
                            container.innerHTML = postsData.posts.map(post => `
                                <div class="post-item">
                                    <a href="${post.url}" target="_blank" class="post-title">${post.title}</a>
                                    <div class="post-meta">
                                        ${post.source} • ${post.author || 'Unknown Author'} • 
                                        ${post.publish_date ? new Date(post.publish_date).toLocaleDateString() : 'No date'}
                                    </div>
                                    ${post.summary ? `<div style="margin-top: 10px; color: #666;">${post.summary.substring(0, 200)}...</div>` : ''}
                                </div>
                            `).join('');
                        }
                    } catch (error) {
                        console.error('Error loading dashboard:', error);
                        document.getElementById('posts-container').innerHTML = 
                            '<p style="color: red;">Error loading posts. Check console for details.</p>';
                    }
                }
                
                // Load dashboard on page load
                loadDashboard();
                
                // Refresh every 30 seconds
                setInterval(loadDashboard, 30000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    @app.get("/api/stats")
    async def api_stats() -> DashboardStats:
        """API endpoint for dashboard statistics."""
        if app.state.vector_db_client:
            try:
                # Get real stats from vector DB
                total = await app.state.vector_db_client.count()
                
                # For now, return simplified stats
                return DashboardStats(
                    total_posts=total,
                    posts_today=0,
                    posts_week=total,
                    sources=["Google Cloud Blog", "AWS Blog", "Azure Blog"],
                    latest_update=datetime.now(timezone.utc)
                )
            except:
                pass
        
        # Return mock data for testing
        return DashboardStats(
            total_posts=42,
            posts_today=3,
            posts_week=15,
            sources=["Google Cloud Blog", "AWS Blog", "Azure Blog", "Uber Engineering"],
            latest_update=datetime.now(timezone.utc)
        )
    
    @app.get("/api/posts")
    async def api_posts(
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100)
    ) -> Dict[str, Any]:
        """API endpoint for posts list."""
        posts = []
        
        if app.state.vector_db_client:
            try:
                # Get real posts from vector DB
                records = await app.state.vector_db_client.list_all(limit=per_page)
                for record in records:
                    posts.append(PostSummary(
                        id=record.id,
                        title=record.title or "Untitled",
                        url=str(record.url),
                        source=record.metadata.get("source", "Unknown") if record.metadata else "Unknown",
                        author=record.metadata.get("author") if record.metadata else None,
                        publish_date=record.publish_date,
                        summary=record.metadata.get("summary") if record.metadata else None,
                        tags=record.metadata.get("tags", []) if record.metadata else [],
                        word_count=record.metadata.get("word_count") if record.metadata else None
                    ))
            except Exception as e:
                logger.error(f"Error fetching posts: {e}")
        
        # If no real posts, return mock data for demo
        if not posts:
            posts = [
                PostSummary(
                    id="1",
                    title="Building Scalable Microservices with Kubernetes",
                    url="https://example.com/post1",
                    source="Uber Engineering",
                    author="John Doe",
                    publish_date=datetime.now(timezone.utc) - timedelta(hours=2),
                    summary="Learn how we scaled our microservices architecture using Kubernetes and achieved 99.99% uptime.",
                    tags=["kubernetes", "microservices", "scalability"]
                ),
                PostSummary(
                    id="2",
                    title="Introduction to Vector Databases",
                    url="https://example.com/post2",
                    source="Google Cloud Blog",
                    author="Jane Smith",
                    publish_date=datetime.now(timezone.utc) - timedelta(days=1),
                    summary="A comprehensive guide to vector databases and their applications in modern AI systems.",
                    tags=["vector-db", "ai", "machine-learning"]
                ),
                PostSummary(
                    id="3",
                    title="Optimizing Python Async Performance",
                    url="https://example.com/post3",
                    source="AWS Blog",
                    author="Bob Wilson",
                    publish_date=datetime.now(timezone.utc) - timedelta(days=2),
                    summary="Tips and tricks for getting the most out of Python's asyncio for high-performance applications.",
                    tags=["python", "async", "performance"]
                )
            ]
        
        return {
            "posts": [p.dict() for p in posts],
            "page": page,
            "per_page": per_page,
            "total": len(posts)
        }
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc),
            "vector_db_connected": app.state.vector_db_client is not None
        }
    
    return app