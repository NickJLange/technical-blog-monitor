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
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Set up structured logger
logger = structlog.get_logger()

# Setup templates
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


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
        return templates.TemplateResponse("index.html", {"request": request})
    
    @app.get("/api/stats")
    async def api_stats() -> DashboardStats:
        """API endpoint for dashboard statistics."""
        if app.state.vector_db_client:
            try:
                # Get real stats from vector DB
                all_posts = await app.state.vector_db_client.list_all(limit=10000)  # Adjust limit as needed
                
                now = datetime.now(timezone.utc)
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                week_start = today_start - timedelta(days=now.weekday())
                
                posts_today = 0
                posts_week = 0
                sources = set()
                
                for post in all_posts:
                    if post.publish_date:
                        if post.publish_date >= today_start:
                            posts_today += 1
                        if post.publish_date >= week_start:
                            posts_week += 1
                    if post.metadata and post.metadata.get("source"):
                        sources.add(post.metadata.get("source"))

                return DashboardStats(
                    total_posts=len(all_posts),
                    posts_today=posts_today,
                    posts_week=posts_week,
                    sources=list(sources),
                    latest_update=datetime.now(timezone.utc)
                )
            except Exception as e:
                logger.error(f"Error fetching stats: {e}")
                # Fallback to mock data on error
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