"""
Application context management.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from typing import Optional, Set

import structlog
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from monitor.config import Settings
from monitor.cache import get_cache_client
from monitor.fetcher.browser import BrowserPool
from monitor.embeddings import get_embedding_client
from monitor.llm import get_generation_client
from monitor.vectordb import get_vector_db_client

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
        self.active_tasks: Set[asyncio.Task] = set()
    
    async def initialize(self) -> None:
        """Initialize all components and resources."""
        print("DEBUG: Initializing application context", flush=True)
        logger.info("Initializing application context")
        
        # Set up thread pool for CPU-bound tasks
        self.thread_pool = ThreadPoolExecutor(
            max_workers=self.settings.max_concurrent_tasks,
            thread_name_prefix="monitor-worker"
        )
        
        # Initialize components
        print("DEBUG: Init cache...", flush=True)
        await self._init_cache()
        print("DEBUG: Init browser pool...", flush=True)
        await self._init_browser_pool()
        print("DEBUG: Init embedding...", flush=True)
        await self._init_embedding_client()
        print("DEBUG: Init generation...", flush=True)
        await self._init_generation_client()
        print("DEBUG: Init vector db...", flush=True)
        await self._init_vector_db()
        
        # Set up scheduler
        print("DEBUG: Init scheduler...", flush=True)
        await self._init_scheduler()
        print("DEBUG: Init complete.", flush=True)
        
        logger.info("Application context initialized")
    
    async def _init_cache(self) -> None:
        """Initialize the cache client."""
        logger.info("Initializing cache client")
        self.cache_client = await get_cache_client(self.settings.cache, self.settings.vector_db)
        await self.exit_stack.enter_async_context(self.cache_client)
        logger.info("Cache client initialized", type=type(self.cache_client).__name__)
    
    async def _init_browser_pool(self) -> None:
        """Initialize the browser pool."""
        logger.info("Initializing browser pool")
        self.browser_pool = BrowserPool(self.settings.browser)
        await self.exit_stack.enter_async_context(self.browser_pool)
        logger.info("Browser pool initialized", 
                    max_browsers=self.settings.browser.max_concurrent_browsers)
    
    async def _init_embedding_client(self) -> None:
        """Initialize the embedding client."""
        logger.info("Initializing embedding client")
        self.embedding_client = await get_embedding_client(self.settings.embedding)
        await self.exit_stack.enter_async_context(self.embedding_client)
        logger.info("Embedding client initialized", 
                    text_model=self.settings.embedding.text_model_name,
                    image_model=self.settings.embedding.image_model_name)
    
    async def _init_generation_client(self) -> None:
        """Initialize the generation client."""
        logger.info("Initializing generation client")
        self.generation_client = get_generation_client(self.settings.llm)
        await self.exit_stack.enter_async_context(self.generation_client)
        logger.info("Generation client initialized", 
                    provider=self.settings.llm.provider.value,
                    model=self.settings.llm.model_name)

    async def _init_vector_db(self) -> None:
        """Initialize the vector database client."""
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
