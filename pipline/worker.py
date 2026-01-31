"""
Queue worker for processing review analysis tasks.
Consumes messages from RabbitMQ and analyzes reviews using LLM.
"""

import json
import time
import signal
import sys
from datetime import datetime
from sqlalchemy import text

from logging_config import get_logger
from rabbitmq import get_consumer_channel, QUEUE_NAME
from llm_client import analyze_review
from database import Review, ReviewAnalysis, Job, ScrapeJob, Place, get_session
from email_service import send_completion_report, gather_scrape_job_stats
from activity_logger import (
    log_review_analyzed, log_job_completed, log_worker_started,
    log_worker_stopped, log_rate_limited, log_system_error
)

logger = get_logger(__name__, service="worker")

# Graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    logger.info("Shutdown signal received, finishing current task...")
    shutdown_requested = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def update_job_progress(job_id: str):
    """Increment processed_reviews count and check for scrape job completion."""
    session = get_session()
    job_completed = False
    place_name = None
    total_reviews = 0
    try:
        job = session.query(Job).filter_by(id=job_id).first()
        if job:
            job.processed_reviews += 1
            total_reviews = job.total_reviews
            # Get place name for logging
            if job.place_id:
                place = session.query(Place).filter_by(id=job.place_id).first()
                if place:
                    place_name = place.name

            if job.processed_reviews >= job.total_reviews:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                job_completed = True
                logger.info(
                    "Job completed",
                    extra={"extra_data": {"job_id": job_id, "total_reviews": job.total_reviews}}
                )
            else:
                job.status = "processing"
            session.commit()
    finally:
        session.close()

    # Log job completion
    if job_completed and place_name:
        log_job_completed(job_id, place_name, total_reviews)

    # If this job just completed, check if the parent scrape job is done
    if job_completed:
        check_and_send_scrape_job_report(job_id)


def check_and_send_scrape_job_report(completed_job_id: str):
    """
    Check if all pipeline jobs for a scrape job are complete,
    and send the email report exactly once using advisory locks.
    """
    session = get_session()
    try:
        # Find the parent ScrapeJob that contains this pipeline job
        completed_job = session.query(Job).filter_by(id=completed_job_id).first()
        if not completed_job:
            return

        # Find scrape job that has this pipeline job in its list
        scrape_job = (
            session.query(ScrapeJob)
            .filter(ScrapeJob.pipeline_job_ids.any(completed_job.id))
            .first()
        )

        if not scrape_job:
            return

        # No email configured
        if not scrape_job.notification_email:
            return

        # Use the scrape job's UUID integer value as lock key
        # UUID.int gives a deterministic 128-bit integer, we take modulo to fit PostgreSQL's bigint
        lock_key = scrape_job.id.int % (2**63 - 1)

        # Try to acquire advisory lock (non-blocking)
        lock_result = session.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": lock_key}
        ).scalar()

        if not lock_result:
            # Another worker has the lock, they'll handle it
            logger.debug("Advisory lock not acquired, another worker handling email")
            return

        try:
            # Re-fetch scrape job within lock to get fresh state
            session.refresh(scrape_job)

            # Check if email already sent
            if scrape_job.email_sent_at is not None:
                return

            # Check if ALL pipeline jobs are completed
            all_completed = True
            if scrape_job.pipeline_job_ids:
                for pipeline_job_id in scrape_job.pipeline_job_ids:
                    pipeline_job = session.query(Job).filter_by(id=pipeline_job_id).first()
                    if not pipeline_job or pipeline_job.status != "completed":
                        all_completed = False
                        break

            if not all_completed:
                return

            # Mark email as sent BEFORE actually sending (prevents duplicates)
            scrape_job.email_sent_at = datetime.utcnow()
            session.commit()

        finally:
            # Release advisory lock
            session.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": lock_key}
            )

        # Send email OUTSIDE the transaction/lock
        # Gather stats and send
        report_data = gather_scrape_job_stats(str(scrape_job.id))
        if report_data:
            send_completion_report(
                to_email=scrape_job.notification_email,
                report_data=report_data,
            )
            logger.info(
                "Email report sent",
                extra={"extra_data": {
                    "scrape_job_id": str(scrape_job.id),
                    "email": scrape_job.notification_email
                }}
            )

    except Exception as e:
        logger.error(
            "Error checking scrape job completion",
            extra={"extra_data": {"completed_job_id": completed_job_id}},
            exc_info=True
        )
    finally:
        session.close()


def save_analysis(review_id: str, analysis: dict):
    """Save analysis result to database."""
    session = get_session()
    try:
        # Check if already analyzed
        existing = session.query(ReviewAnalysis).filter_by(review_id=review_id).first()
        if existing:
            logger.debug("Review already analyzed, skipping", extra={"extra_data": {"review_id": review_id}})
            return

        review_analysis = ReviewAnalysis(
            review_id=review_id,
            sentiment=analysis.get("sentiment"),
            score=analysis.get("score"),
            topics_positive=analysis.get("topics_positive", []),
            topics_negative=analysis.get("topics_negative", []),
            language=analysis.get("language"),
            urgent=analysis.get("urgent", False),
            summary_ar=analysis.get("summary_ar"),
            summary_en=analysis.get("summary_en"),
            suggested_reply_ar=analysis.get("suggested_reply_ar"),
            raw_response=analysis,
        )
        session.add(review_analysis)
        session.commit()
    finally:
        session.close()


def process_message(ch, method, properties, body):
    """Process a single review message."""
    global shutdown_requested

    try:
        message = json.loads(body)
        review_id = message["review_id"]
        job_id = message["job_id"]

        logger.info("Processing review", extra={"extra_data": {"review_id": review_id, "job_id": job_id}})

        # Fetch review from DB
        session = get_session()
        place_name = None
        try:
            review = session.query(Review).filter_by(id=review_id).first()
            if not review:
                logger.warning("Review not found, acknowledging", extra={"extra_data": {"review_id": review_id}})
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            review_text = review.text
            review_rating = review.rating

            # Get place name for activity logging
            if review.place:
                place_name = review.place.name
        finally:
            session.close()

        if not review_text:
            logger.debug("Empty review text, skipping", extra={"extra_data": {"review_id": review_id}})
            ch.basic_ack(delivery_tag=method.delivery_tag)
            update_job_progress(job_id)
            return

        # Call LLM API with retry logic
        max_retries = 3
        retry_delay = 30  # seconds

        for attempt in range(max_retries):
            try:
                analysis = analyze_review(review_text, review_rating)
                break
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "ResourceExhausted" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(
                            "Rate limited, retrying",
                            extra={"extra_data": {"wait_seconds": wait_time, "attempt": attempt + 1}}
                        )
                        log_rate_limited("LLM", wait_time)
                        time.sleep(wait_time)
                    else:
                        logger.error("Rate limit exceeded, requeueing", extra={"extra_data": {"review_id": review_id}})
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        return
                else:
                    logger.error(
                        "LLM analysis error",
                        extra={"extra_data": {"review_id": review_id, "attempt": attempt + 1, "error": error_msg}}
                    )
                    if attempt < max_retries - 1:
                        time.sleep(5)
                    else:
                        # Dead letter after max retries
                        logger.error("Max retries reached, dead-lettering", extra={"extra_data": {"review_id": review_id}})
                        log_system_error("worker", f"Max retries for review {review_id}", {"review_id": review_id})
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                        return

        # Save analysis
        save_analysis(review_id, analysis)

        # Log activity
        sentiment = analysis.get("sentiment")
        score = analysis.get("score", 0)
        urgent = analysis.get("urgent", False)

        logger.info(
            "Analysis complete",
            extra={"extra_data": {
                "review_id": review_id,
                "sentiment": sentiment,
                "score": score,
                "urgent": urgent
            }}
        )

        # Log to activity logs (every 10th review to avoid too much noise, or if urgent)
        if urgent or (hash(review_id) % 10 == 0):
            log_review_analyzed(job_id, place_name or "Unknown", sentiment, score, urgent)

        # Update job progress
        update_job_progress(job_id)

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

        # Small delay between requests to avoid rate limits
        time.sleep(2)

    except Exception as e:
        logger.error("Unexpected error processing message", exc_info=True)
        log_system_error("worker", str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def run_worker():
    """Start consuming messages from queue."""
    global shutdown_requested

    logger.info("Connecting to RabbitMQ...")
    connection, channel = get_consumer_channel()

    logger.info(f"Worker started, listening on queue '{QUEUE_NAME}'")
    log_worker_started()

    # Set up consumer
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

    try:
        while not shutdown_requested:
            connection.process_data_events(time_limit=1)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Closing connection...")
        connection.close()
        logger.info("Worker stopped")
        log_worker_stopped()


if __name__ == "__main__":
    run_worker()
