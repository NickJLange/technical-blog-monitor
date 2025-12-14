#!/usr/bin/env python3
"""
Technical Blog Monitor - Entry Point

This module serves as the main entry point for the technical blog monitor daemon.
It handles initialization of all components, sets up the scheduler, and manages
the lifecycle of the application including graceful shutdown.
"""
import argparse
import asyncio
import atexit
import os
import signal
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import start_http_server
from tenacity import retry, stop_after_attempt, wait_exponential

from monitor.config import LogLevel, Settings, load_settings
from monitor.i18n import _

# Set up structured logger
logger = structlog.get_logger()


class AppContext:
    """
    Application context that holds all initialized components and resources.
    
    This class manages the lifecycle of all components and provides access
    to them throughout the application.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.exit_stack = AsyncExitStack()
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.thread_pool: Optional[ThreadPoolExecutor] = None
        self.browser_pool = None  # Will be initialized later
        self.cache_client = None  # Will be initialized later
        self.embedding_client = None  # Will be initialized later
        self.generation_client = None  # Will be initialized later
        self.vector_db_client = None  # Will be initialized later
        self.shutdown_event = asyncio.Event()
    
    async def initialize(self) -> None:
        """Initialize all components and resources."""
        logger.info("Initializing application context")
        
        # Set up thread pool for CPU-bound tasks
        self.thread_pool = ThreadPoolExecutor(
            max_workers=self.settings.max_concurrent_tasks,
            thread_name_prefix="monitor-worker"
        )
        
        # Initialize components
        await self._init_cache()
        await self._init_browser_pool()
        await self._init_embedding_client()
        await self._init_generation_client()
        await self._init_vector_db()
        
        # Set up scheduler
        await self._init_scheduler()
        
        logger.info("Application context initialized")
    
    async def _init_cache(self) -> None:
        """Initialize the cache client."""
        from monitor.cache import get_cache_client
        
        logger.info("Initializing cache client")
        self.cache_client = await get_cache_client(self.settings.cache, self.settings.vector_db)
        await self.exit_stack.enter_async_context(self.cache_client)
        logger.info("Cache client initialized", type=type(self.cache_client).__name__)
    
    async def _init_browser_pool(self) -> None:
        """Initialize the browser pool."""
        from monitor.fetcher.browser import BrowserPool
        
        logger.info("Initializing browser pool")
        self.browser_pool = BrowserPool(self.settings.browser)
        await self.exit_stack.enter_async_context(self.browser_pool)
        logger.info("Browser pool initialized", 
                    max_browsers=self.settings.browser.max_concurrent_browsers)
    
    async def _init_embedding_client(self) -> None:
        """Initialize the embedding client."""
        from monitor.embeddings import get_embedding_client
        
        logger.info("Initializing embedding client")
        self.embedding_client = await get_embedding_client(self.settings.embedding)
        await self.exit_stack.enter_async_context(self.embedding_client)
        logger.info("Embedding client initialized", 
                    text_model=self.settings.embedding.text_model_name,
                    image_model=self.settings.embedding.image_model_name)
    
    async def _init_generation_client(self) -> None:
        """Initialize the generation client."""
        from monitor.llm import get_generation_client
        
        logger.info("Initializing generation client")
        self.generation_client = get_generation_client(self.settings.llm)
        await self.exit_stack.enter_async_context(self.generation_client)
        logger.info("Generation client initialized", 
                    provider=self.settings.llm.provider.value,
                    model=self.settings.llm.model_name)

    async def _init_vector_db(self) -> None:
        """Initialize the vector database client."""
        from monitor.vectordb import get_vector_db_client
        
        logger.info("Initializing vector database client")
        self.vector_db_client = await get_vector_db_client(self.settings.vector_db)
        await self.exit_stack.enter_async_context(self.vector_db_client)
        logger.info("Vector database client initialized", 
                    type=self.settings.vector_db.db_type.value,
                    collection=self.settings.vector_db.collection_name)
    
    async def _init_scheduler(self) -> None:
        """Initialize the job scheduler."""
        logger.info("Initializing job scheduler")
        
        # Set up job stores
        jobstores = {"default": MemoryJobStore()}
        
        # Create scheduler (use default AsyncIO executor)
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=self.settings.scheduler.timezone,
            job_defaults={
                "coalesce": self.settings.scheduler.coalesce,
                "misfire_grace_time": self.settings.scheduler.misfire_grace_time,
                "max_instances": self.settings.scheduler.max_instances
            }
        )
        
        # Attach application context so helper modules can access it
        # (monitor.scheduler expects `scheduler.app_context` to be present).
        self.scheduler.app_context = self

        # Schedule jobs
        self._schedule_jobs()
        
        # Start scheduler
        self.scheduler.start()
        logger.info("Job scheduler initialized and started")
    
    def _schedule_jobs(self) -> None:
        """Schedule all monitoring jobs."""
        from monitor.scheduler import schedule_feed_jobs
        
        schedule_feed_jobs(self.scheduler, self.settings.feeds)
        
        logger.info("Scheduled feed monitoring jobs", 
                    feed_count=len(self.settings.feeds))
    
    async def shutdown(self) -> None:
        """Gracefully shut down all components and resources."""
        logger.info("Shutting down application")
        
        # Signal shutdown to all tasks
        self.shutdown_event.set()
        
        # Cancel all active tasks
        if self.active_tasks:
            logger.info("Cancelling active tasks", count=len(self.active_tasks))
            for task in self.active_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete cancellation
            await asyncio.gather(*self.active_tasks, return_exceptions=True)
        
        # Shutdown scheduler
        if self.scheduler and self.scheduler.running:
            logger.info("Shutting down scheduler")
            self.scheduler.shutdown(wait=False)
        
        # Close all components using the exit stack
        logger.info("Closing all components")
        await self.exit_stack.aclose()
        
        # Shutdown thread pool
        if self.thread_pool:
            logger.info("Shutting down thread pool")
            self.thread_pool.shutdown(wait=True, cancel_futures=True)
        
        logger.info("Application shutdown complete")
    
    def create_task(self, coro) -> asyncio.Task:
        """Create a tracked asyncio task."""
        task = asyncio.create_task(coro)
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)
        return task


async def process_feed(app_context: AppContext, feed_name: str) -> None:
    """
    Process a single feed to check for new posts.
    
    This is the main job function that will be called by the scheduler.
    It handles the entire pipeline from fetching to embedding and storage.
    """
    from monitor.feeds.base import process_feed_posts
    
    logger.info("Processing feed", feed_name=feed_name)
    feed_config = app_context.settings.get_feed_by_name(feed_name)
    
    if not feed_config:
        logger.error("Feed configuration not found", feed_name=feed_name)
        return
    
    if not feed_config.enabled:
        logger.info("Feed is disabled, skipping", feed_name=feed_name)
        return
    
    try:
        # Process the feed and get new posts
        new_posts = await process_feed_posts(
            feed_config,
            app_context.cache_client,
            app_context.browser_pool,
            max_posts=feed_config.max_posts_per_check
        )
        
        if not new_posts:
            logger.info("No new posts found", feed_name=feed_name)
            return
        
        logger.info("Found new posts", feed_name=feed_name, count=len(new_posts))

        # ------------------------------------------------------------------
        # Optional full-article capture (text, screenshots, etc.)
        # ------------------------------------------------------------------
        if app_context.settings.article_processing.full_content_capture:
            from monitor.feeds.base import process_individual_article

            conc = app_context.settings.article_processing.concurrent_article_tasks
            sem_capture = asyncio.Semaphore(conc)

            async def _capture(post):
                async with sem_capture:
                    return await process_individual_article(
                        post,
                        app_context.cache_client,
                        app_context.browser_pool,
                    )

            # Capture articles concurrently (bounded by semaphore)
            new_posts = await asyncio.gather(*[_capture(p) for p in new_posts])
            logger.info(
                "Full article capture complete",
                feed_name=feed_name,
                processed=len(new_posts),
            )
        
        # Process each post in parallel with a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(app_context.settings.max_concurrent_tasks)
        tasks = []
        
        for post in new_posts:
            task = app_context.create_task(
                process_post(app_context, post, semaphore)
            )
            tasks.append(task)
        
        if tasks:
            # Wait for all post processing tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error("Error processing post", 
                                feed_name=feed_name,
                                post_url=new_posts[i].url,
                                error=str(result))
        
        logger.info("Feed processing complete", feed_name=feed_name)
    
    except Exception as e:
        logger.exception("Error processing feed", 
                        feed_name=feed_name,
                        error=str(e))


async def process_post(app_context: AppContext, post, semaphore: asyncio.Semaphore) -> None:
    """
    Process a single post through the entire pipeline.
    
    This function handles:
    1. Rendering the page with a headless browser
    2. Extracting text and images
    3. Generating embeddings
    4. Storing in the vector database
    """
    from monitor.extractor.article_parser import extract_article_content
    from monitor.models import EmbeddingRecord
    
    async with semaphore:
        logger.info("Processing post", url=post.url, title=post.title)
        
        try:
            # Render page with browser
            screenshot_path = await app_context.browser_pool.render_and_screenshot(post.url)
            
            # Extract article content
            content = await extract_article_content(
                post.url, 
                app_context.cache_client,
                app_context.thread_pool
            )
            
            # Generate summary if enabled
            ai_summary = None
            if app_context.settings.article_processing.generate_summary:
                try:
                    logger.info("Generating AI summary", url=post.url)
                    # Limit context to avoid token limits, though 10k chars is usually fine for modern models
                    # Ideally we'd tokenize, but chars is a cheap proxy
                    prompt = f"Summarize the following technical blog post in a dense, insight-focused paragraph. Ignore generic intro/outro. Focus on the core technical details:\n\n{content.text[:15000]}"
                    ai_summary = await app_context.generation_client.generate(prompt)
                    logger.info("AI summary generated", url=post.url)
                except Exception as e:
                    logger.warning("Failed to generate AI summary", url=post.url, error=str(e))

            # Generate embeddings
            text_embedding = await app_context.embedding_client.embed_text(content.text)
            
            # Generate image embedding if available
            image_embedding = None
            if screenshot_path and app_context.settings.embedding.image_model_name:
                image_embedding = await app_context.embedding_client.embed_image(screenshot_path)
            
            # Create embedding record
            record = EmbeddingRecord(
                id=post.id,
                url=post.url,
                title=post.title,
                publish_date=post.publish_date,
                text_embedding=text_embedding,
                image_embedding=image_embedding,
                metadata={
                    "source": post.source,
                    "author": content.author,
                    "summary": ai_summary or content.summary,
                    "screenshot_path": str(screenshot_path) if screenshot_path else None,
                    "word_count": content.word_count,
                    "tags": content.tags,
                    "ai_summary": ai_summary
                }
            )
            
            # Store in vector database
            await app_context.vector_db_client.upsert(record)
            
            logger.info("Post processed successfully", 
                        url=post.url,
                        title=post.title)
            
            return record
        
        except Exception as e:
            logger.exception("Error processing post", 
                            url=post.url,
                            error=str(e))
            raise


@asynccontextmanager
async def app_lifecycle(settings: Settings):
    """
    Context manager for the application lifecycle.
    
    This handles initialization and graceful shutdown of all components.
    """
    # Create app context
    app_context = AppContext(settings)
    
    try:
        # Initialize all components
        await app_context.initialize()
        
        # Start metrics server if enabled
        if settings.metrics.prometheus_enabled:
            start_http_server(settings.metrics.prometheus_port)
            logger.info("Prometheus metrics server started", 
                        port=settings.metrics.prometheus_port)
        
        # Yield the initialized app context
        yield app_context
    
    finally:
        # Ensure proper shutdown
        await app_context.shutdown()


def setup_logging(settings: Settings) -> None:
    """Set up structured logging based on configuration."""
    log_level = settings.metrics.log_level.value
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.metrics.structured_logging
            else structlog.dev.ConsoleRenderer()
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Set log level on the standard library root logger so that
    # libraries using logging propagate correctly.
    numeric_level = getattr(logging, log_level, logging.INFO)
    logging.getLogger().setLevel(numeric_level)
    
    logger.info("Logging initialized", level=log_level)


def setup_signal_handlers(loop: asyncio.AbstractEventLoop, app_context: AppContext) -> None:
    """Set up signal handlers for graceful shutdown."""
    # Define signal handler
    def signal_handler():
        logger.info("Received shutdown signal")
        if not app_context.shutdown_event.is_set():
            # Stop the event loop
            loop.stop()
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    logger.info("Signal handlers registered")


async def run_daemon(settings: Settings) -> None:
    """Run the application as a daemon that continues until stopped."""
    logger.info("Starting technical blog monitor daemon")
    
    async with app_lifecycle(settings) as app_context:
        # Get the event loop
        loop = asyncio.get_running_loop()
        
        # Set up signal handlers
        setup_signal_handlers(loop, app_context)
        
        try:
            # Keep running until shutdown is requested
            await app_context.shutdown_event.wait()
        
        except asyncio.CancelledError:
            logger.info("Main task cancelled")
        
        except Exception as e:
            logger.exception("Unhandled exception in daemon mode", error=str(e))
            raise
        
        finally:
            logger.info("Daemon shutting down")


async def run_once(settings: Settings) -> None:
    """Run a single iteration of the monitoring process and exit."""
    logger.info("Running technical blog monitor once")
    
    async with app_lifecycle(settings) as app_context:
        try:
            # Process each feed once
            tasks = []
            for feed in settings.feeds:
                if feed.enabled:
                    task = app_context.create_task(process_feed(app_context, feed.name))
                    tasks.append(task)
            
            if tasks:
                # Wait for all feed processing tasks to complete
                await asyncio.gather(*tasks)
            
            logger.info("One-time run completed successfully")
        
        except Exception as e:
            logger.exception("Error during one-time run", error=str(e))
            raise


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=_("Technical Blog Monitor - Track and embed technical blog posts")
    )
    
    parser.add_argument(
        "--config",
        help="Path to configuration file",
        default=None
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (don't run as daemon)"
    )
    
    parser.add_argument(
        "--feed",
        help="Process only the specified feed (by name)",
        default=None
    )
    
    parser.add_argument(
        "--log-level",
        choices=[level.value for level in LogLevel],
        default=None,
        help="Set the log level"
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entry point for the application."""
    try:
        # Parse command line arguments
        args = parse_args()
        
        # Load settings
        settings = load_settings()
        
        # Override settings with command line arguments
        if args.log_level:
            settings.metrics.log_level = LogLevel(args.log_level)
        
        # Set up logging
        setup_logging(settings)
        
        # Log startup information
        logger.info(
            "Technical Blog Monitor starting up",
            version=settings.version,
            environment=settings.environment.value,
            python_version=sys.version
        )
        
        # If a specific feed is specified, filter the feeds list
        if args.feed:
            feed = settings.get_feed_by_name(args.feed)
            if not feed:
                logger.error("Feed not found", feed_name=args.feed)
                return 1
            settings.feeds = [feed]
        
        # Run the appropriate mode
        if args.once:
            asyncio.run(run_once(settings))
        else:
            asyncio.run(run_daemon(settings))
        
        return 0
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    
    except Exception as e:
        logger.exception("Unhandled exception", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
