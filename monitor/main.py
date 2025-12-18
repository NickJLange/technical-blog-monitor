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
from prometheus_client import start_http_server, Counter
from tenacity import retry, stop_after_attempt, wait_exponential

from monitor.config import LogLevel, Settings, load_settings
from monitor.i18n import _

# Set up structured logger
logger = structlog.get_logger()

# Import context and tasks
from monitor.context import AppContext
from monitor.tasks import process_feed





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
    # Ensure BROWSER environment variable does not interfere with Pydantic-settings
    os.environ.pop("BROWSER", None)
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
