"""
Task definitions for the technical blog monitor.

This module contains the main processing logic for feeds and posts,
separated from the application entry point to avoid circular imports.
"""
import asyncio
import traceback
from typing import TYPE_CHECKING

import structlog
from prometheus_client import Counter

if TYPE_CHECKING:
    from monitor.context import AppContext

# Set up structured logger
logger = structlog.get_logger()

# Define metrics
FEEDS_PROCESSED_TOTAL = Counter('feeds_processed_total', 'Total number of feeds processed', ['feed_name', 'status'])
FEED_ERRORS_TOTAL = Counter('feed_errors_total', 'Total number of feed processing errors', ['feed_name', 'error_type'])


async def process_feed(app_context: 'AppContext', feed_name: str) -> None:
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
        FEEDS_PROCESSED_TOTAL.labels(feed_name=feed_name, status="config_error").inc()
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
            FEEDS_PROCESSED_TOTAL.labels(feed_name=feed_name, status="no_new_posts").inc()
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
            # Use return_exceptions=True so one failure doesn't crash the entire feed
            captured = await asyncio.gather(*[_capture(p) for p in new_posts], return_exceptions=True)
            
            # Filter out any exceptions and log failures
            failed_count = 0
            new_posts = []
            for result in captured:
                if isinstance(result, Exception):
                    failed_count += 1
                    logger.warning(
                        "Article capture failed",
                        feed_name=feed_name,
                        error=str(result),
                    )
                else:
                    new_posts.append(result)
            
            logger.info(
                "Full article capture complete",
                feed_name=feed_name,
                succeeded=len(new_posts),
                failed=failed_count,
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
            failures = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failures += 1
                    logger.error("Error processing post", 
                                feed_name=feed_name,
                                post_url=new_posts[i].url,
                                error=str(result))
            
            if failures > 0:
                FEEDS_PROCESSED_TOTAL.labels(feed_name=feed_name, status="partial_failure").inc()
            else:
                FEEDS_PROCESSED_TOTAL.labels(feed_name=feed_name, status="success").inc()
        
        logger.info("Feed processing complete", feed_name=feed_name)
    
    except Exception as e:
        logger.exception("Error processing feed", 
                        feed_name=feed_name,
                        error=str(e))
        
        # Increment error metric
        FEED_ERRORS_TOTAL.labels(feed_name=feed_name, error_type=type(e).__name__).inc()
        FEEDS_PROCESSED_TOTAL.labels(feed_name=feed_name, status="error").inc()
        
        # Log to exception queue
        if app_context.vector_db_client and hasattr(app_context.vector_db_client, 'log_error'):
            await app_context.vector_db_client.log_error(
                feed_name=feed_name,
                feed_url=feed_config.url,
                error_message=str(e),
                traceback_str=traceback.format_exc()
            )


async def process_post(app_context: 'AppContext', post, semaphore: asyncio.Semaphore) -> None:
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
            final_summary = ai_summary or content.summary
            record = EmbeddingRecord(
                id=post.id,
                url=post.url,
                title=post.title,
                publish_date=post.publish_date,
                text_embedding=text_embedding,
                image_embedding=image_embedding,
                summary=final_summary,  # Store in top-level field
                author=content.author,  # Store in top-level field
                source=post.source,  # Store in top-level field
                content_snippet=content.summary,
                metadata={
                    "source": post.source,
                    "author": content.author,
                    "summary": final_summary,
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
