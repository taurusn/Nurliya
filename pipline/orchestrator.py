"""
Pipeline orchestrator for running the full scrape-to-analysis flow.
Handles: Scraper job → CSV download → Producer → Status updates
"""

import os
import uuid
import asyncio
from datetime import datetime
from typing import Optional

from scraper_client import ScraperClient
from csv_parser import parse_csv, save_place_and_reviews
from producer import create_job, update_job_status
from rabbitmq import get_producer_channel, publish_message
from database import ScrapeJob, get_session
from config import RESULTS_DIR


async def update_scrape_job(job_id: str, **kwargs):
    """Update a ScrapeJob record."""
    session = get_session()
    try:
        job = session.query(ScrapeJob).filter_by(id=job_id).first()
        if job:
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            session.commit()
    finally:
        session.close()


async def run_scrape_pipeline(
    query: str,
    scrape_job_id: str,
    depth: int = 10,
    lang: str = "en",
    max_time: int = 300,
) -> dict:
    """
    Run the full scrape-to-analysis pipeline.

    1. Create scraper job via Web API
    2. Poll until scraper completes
    3. Download CSV
    4. Run producer (parse CSV, save to DB, queue reviews)
    5. Update ScrapeJob status

    Args:
        query: Search query for Google Maps
        scrape_job_id: Our internal ScrapeJob ID
        depth: Scroll depth for scraper
        lang: Language code
        max_time: Max scrape time in seconds

    Returns:
        Dict with pipeline results
    """
    client = ScraperClient()
    result = {
        "scrape_job_id": scrape_job_id,
        "status": "started",
        "places_found": 0,
        "reviews_total": 0,
        "pipeline_job_ids": [],
        "error": None,
    }

    try:
        # Step 1: Create scraper job
        await update_scrape_job(scrape_job_id, status="scraping")
        scraper_id = await client.create_job(
            query=query,
            depth=depth,
            lang=lang,
            max_time=max_time,
        )
        await update_scrape_job(scrape_job_id, scraper_job_id=scraper_id)

        # Step 2: Wait for scraper to complete
        scraper_status = await client.wait_for_completion(
            scraper_id,
            timeout=max_time + 60,  # Extra buffer for completion
        )

        # Step 3: Download CSV
        csv_filename = f"{scrape_job_id}.csv"
        csv_path = os.path.join(RESULTS_DIR, csv_filename)
        os.makedirs(RESULTS_DIR, exist_ok=True)
        await client.download_csv(scraper_id, csv_path)

        # Step 4: Run producer (parse + queue)
        await update_scrape_job(scrape_job_id, status="processing")
        pipeline_result = await run_producer_async(csv_path)

        # Step 5: Update final status
        result["status"] = "completed"
        result["places_found"] = pipeline_result["places_count"]
        result["reviews_total"] = pipeline_result["reviews_total"]
        result["pipeline_job_ids"] = pipeline_result["job_ids"]

        await update_scrape_job(
            scrape_job_id,
            status="completed",
            places_found=result["places_found"],
            reviews_total=result["reviews_total"],
            pipeline_job_ids=result["pipeline_job_ids"],
            completed_at=datetime.utcnow(),
        )

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        await update_scrape_job(
            scrape_job_id,
            status="failed",
            error_message=str(e),
        )

    return result


async def run_producer_async(csv_path: str) -> dict:
    """
    Async wrapper for producer logic.
    Parses CSV, saves to DB, and queues reviews.
    """
    # Run in executor since producer uses sync DB operations
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_producer_sync, csv_path)


def run_producer_sync(csv_path: str) -> dict:
    """
    Synchronous producer logic.

    Returns:
        Dict with places_count, reviews_total, job_ids
    """
    from database import Review

    # Parse CSV
    places = parse_csv(csv_path)

    # Connect to RabbitMQ
    connection, channel = get_producer_channel()

    result = {
        "places_count": len(places),
        "reviews_total": 0,
        "job_ids": [],
    }

    for place_data in places:
        # Save place and reviews to DB
        place_id, review_ids = save_place_and_reviews(place_data)

        if not review_ids:
            continue

        # Create job
        job = create_job(place_id=place_id, total_reviews=len(review_ids))
        result["job_ids"].append(str(job.id))
        result["reviews_total"] += len(review_ids)

        # Update reviews with job_id and queue them
        session = get_session()
        try:
            for review_id in review_ids:
                db_review = session.query(Review).filter_by(id=review_id).first()
                if db_review:
                    db_review.job_id = job.id
                session.commit()

                # Queue for analysis
                message = {
                    "review_id": review_id,
                    "job_id": str(job.id),
                }
                publish_message(channel, message)
        finally:
            session.close()

        # Update job status
        update_job_status(str(job.id), "queued")

    connection.close()
    return result


def create_scrape_job(query: str) -> ScrapeJob:
    """Create a new ScrapeJob record."""
    session = get_session()
    try:
        job = ScrapeJob(
            query=query,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job
    finally:
        session.close()


def get_scrape_job(job_id: str) -> Optional[ScrapeJob]:
    """Get a ScrapeJob by ID."""
    session = get_session()
    try:
        return session.query(ScrapeJob).filter_by(id=job_id).first()
    finally:
        session.close()


def get_scrape_job_progress(job_id: str) -> dict:
    """Get detailed progress for a ScrapeJob."""
    from database import Job, Review, ReviewAnalysis

    session = get_session()
    try:
        scrape_job = session.query(ScrapeJob).filter_by(id=job_id).first()
        if not scrape_job:
            return None

        # Count processed reviews across all pipeline jobs
        reviews_processed = 0
        if scrape_job.pipeline_job_ids:
            for pipeline_job_id in scrape_job.pipeline_job_ids:
                job = session.query(Job).filter_by(id=pipeline_job_id).first()
                if job:
                    reviews_processed += job.processed_reviews

        return {
            "job_id": str(scrape_job.id),
            "query": scrape_job.query,
            "status": scrape_job.status,
            "scraper_job_id": scrape_job.scraper_job_id,
            "places_found": scrape_job.places_found or 0,
            "reviews_total": scrape_job.reviews_total or 0,
            "reviews_processed": reviews_processed,
            "error_message": scrape_job.error_message,
            "created_at": scrape_job.created_at.isoformat() if scrape_job.created_at else None,
            "completed_at": scrape_job.completed_at.isoformat() if scrape_job.completed_at else None,
        }
    finally:
        session.close()
