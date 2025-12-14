"""
Scheduler module for the technical blog monitor.

This module handles setting up APScheduler jobs for feed monitoring
with configurable intervals and job management.
"""
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from monitor.config import FeedConfig

# Set up structured logger
logger = structlog.get_logger()


def schedule_feed_jobs(scheduler: AsyncIOScheduler, feeds: List[FeedConfig]) -> None:
    """
    Schedule monitoring jobs for all enabled feeds.
    
    Args:
        scheduler: The APScheduler instance to use
        feeds: List of feed configurations to schedule
    """
    if not feeds:
        logger.warning("No feeds configured, no jobs will be scheduled")
        return

    for feed in feeds:
        if not feed.enabled:
            logger.info("Feed disabled, skipping job scheduling", feed_name=feed.name)
            continue

        # Create a job ID based on the feed name
        job_id = f"feed_monitor_{feed.name}"

        # Remove any existing job with the same ID
        existing_job = scheduler.get_job(job_id)
        if existing_job:
            logger.debug("Removing existing job", job_id=job_id)
            scheduler.remove_job(job_id)

        # Schedule the job with the appropriate interval
        interval_minutes = max(1, feed.check_interval_minutes)  # Ensure at least 1 minute

        # Import here to avoid circular imports
        from monitor.main import process_feed

        # Get the app context from the scheduler's metadata
        app_context = scheduler.app_context if hasattr(scheduler, "app_context") else None

        if not app_context:
            logger.error("App context not available in scheduler", feed_name=feed.name)
            continue

        # Schedule the job
        scheduler.add_job(
            process_feed,
            trigger=IntervalTrigger(minutes=interval_minutes),
            args=[app_context, feed.name],
            id=job_id,
            name=f"Monitor {feed.name}",
            replace_existing=True,
            next_run_time=datetime.now() + timedelta(seconds=10),  # Start soon but not immediately
            misfire_grace_time=300,  # Allow 5 minutes of misfire grace time
            max_instances=1,  # Only one instance of each job can run at a time
            coalesce=True,  # Coalesce missed runs
        )

        logger.info(
            "Scheduled feed monitoring job",
            feed_name=feed.name,
            interval_minutes=interval_minutes,
            job_id=job_id
        )


def schedule_one_time_job(
    scheduler: AsyncIOScheduler,
    func: Callable,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    run_date: Optional[datetime] = None,
    delay_seconds: Optional[int] = None,
) -> str:
    """
    Schedule a one-time job to run once at a specific time or after a delay.
    
    Args:
        scheduler: The APScheduler instance to use
        func: The function to run
        args: Positional arguments to pass to the function
        kwargs: Keyword arguments to pass to the function
        job_id: Optional job ID, will be generated if not provided
        run_date: Specific datetime to run the job
        delay_seconds: Number of seconds to wait before running the job
        
    Returns:
        str: The job ID
    """
    if run_date is None and delay_seconds is None:
        # Default to running immediately
        run_date = datetime.now()
    elif delay_seconds is not None:
        # Calculate run date from delay
        run_date = datetime.now() + timedelta(seconds=delay_seconds)

    # Generate a job ID if not provided
    if job_id is None:
        job_id = f"one_time_{func.__name__}_{datetime.now().timestamp()}"

    # Schedule the job
    scheduler.add_job(
        func,
        trigger="date",
        run_date=run_date,
        args=args or [],
        kwargs=kwargs or {},
        id=job_id,
        name=f"One-time {func.__name__}",
        replace_existing=True,
    )

    logger.debug(
        "Scheduled one-time job",
        job_id=job_id,
        func=func.__name__,
        run_date=run_date
    )

    return job_id


def schedule_cron_job(
    scheduler: AsyncIOScheduler,
    func: Callable,
    cron_expression: str,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    timezone: Optional[str] = None,
) -> str:
    """
    Schedule a job to run on a cron schedule.
    
    Args:
        scheduler: The APScheduler instance to use
        func: The function to run
        cron_expression: Cron expression (e.g., "0 */6 * * *" for every 6 hours)
        args: Positional arguments to pass to the function
        kwargs: Keyword arguments to pass to the function
        job_id: Optional job ID, will be generated if not provided
        timezone: Timezone for the cron expression
        
    Returns:
        str: The job ID
    """
    # Generate a job ID if not provided
    if job_id is None:
        job_id = f"cron_{func.__name__}_{datetime.now().timestamp()}"

    # Parse the cron expression
    trigger = CronTrigger.from_crontab(cron_expression, timezone=timezone)

    # Schedule the job
    scheduler.add_job(
        func,
        trigger=trigger,
        args=args or [],
        kwargs=kwargs or {},
        id=job_id,
        name=f"Cron {func.__name__}",
        replace_existing=True,
    )

    logger.debug(
        "Scheduled cron job",
        job_id=job_id,
        func=func.__name__,
        cron_expression=cron_expression,
        timezone=timezone
    )

    return job_id


def cancel_job(scheduler: AsyncIOScheduler, job_id: str) -> bool:
    """
    Cancel a scheduled job.
    
    Args:
        scheduler: The APScheduler instance to use
        job_id: The ID of the job to cancel
        
    Returns:
        bool: True if the job was found and canceled, False otherwise
    """
    job = scheduler.get_job(job_id)
    if job:
        scheduler.remove_job(job_id)
        logger.debug("Canceled job", job_id=job_id)
        return True

    logger.warning("Job not found for cancellation", job_id=job_id)
    return False


def pause_job(scheduler: AsyncIOScheduler, job_id: str) -> bool:
    """
    Pause a scheduled job.
    
    Args:
        scheduler: The APScheduler instance to use
        job_id: The ID of the job to pause
        
    Returns:
        bool: True if the job was found and paused, False otherwise
    """
    job = scheduler.get_job(job_id)
    if job:
        scheduler.pause_job(job_id)
        logger.debug("Paused job", job_id=job_id)
        return True

    logger.warning("Job not found for pausing", job_id=job_id)
    return False


def resume_job(scheduler: AsyncIOScheduler, job_id: str) -> bool:
    """
    Resume a paused job.
    
    Args:
        scheduler: The APScheduler instance to use
        job_id: The ID of the job to resume
        
    Returns:
        bool: True if the job was found and resumed, False otherwise
    """
    job = scheduler.get_job(job_id)
    if job:
        scheduler.resume_job(job_id)
        logger.debug("Resumed job", job_id=job_id)
        return True

    logger.warning("Job not found for resuming", job_id=job_id)
    return False


def reschedule_job(
    scheduler: AsyncIOScheduler,
    job_id: str,
    trigger: Union[str, IntervalTrigger, CronTrigger],
    **trigger_args
) -> bool:
    """
    Reschedule an existing job with a new trigger.
    
    Args:
        scheduler: The APScheduler instance to use
        job_id: The ID of the job to reschedule
        trigger: The new trigger (e.g., 'interval', 'cron', or a trigger instance)
        **trigger_args: Arguments for the trigger
        
    Returns:
        bool: True if the job was found and rescheduled, False otherwise
    """
    job = scheduler.get_job(job_id)
    if job:
        scheduler.reschedule_job(job_id, trigger=trigger, **trigger_args)
        logger.debug("Rescheduled job", job_id=job_id)
        return True

    logger.warning("Job not found for rescheduling", job_id=job_id)
    return False


def get_all_jobs(scheduler: AsyncIOScheduler) -> List[Dict[str, Any]]:
    """
    Get information about all scheduled jobs.
    
    Args:
        scheduler: The APScheduler instance to use
        
    Returns:
        List[Dict[str, Any]]: List of job information dictionaries
    """
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        jobs.append({
            "id": job.id,
            "name": job.name,
            "function": job.func.__name__,
            "next_run_time": next_run,
            "trigger": str(job.trigger),
        })

    return jobs


def get_feed_job_id(feed_name: str) -> str:
    """
    Get the job ID for a feed monitoring job.
    
    Args:
        feed_name: The name of the feed
        
    Returns:
        str: The job ID
    """
    return f"feed_monitor_{feed_name}"
