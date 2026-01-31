"""
Activity logger for tracking system events in the database.
Logs both activity events (jobs, analyses) and system events (errors, processing).
"""

from datetime import datetime
from typing import Optional, Dict, Any
from logging_config import get_logger

logger = get_logger(__name__, service="activity_logger")


def log_activity(
    category: str,
    action: str,
    message: str,
    level: str = "info",
    details: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    scrape_job_id: Optional[str] = None,
    place_id: Optional[str] = None,
):
    """
    Log an activity event to the database.

    Args:
        category: Event category (job, analysis, email, scraper, worker, system)
        action: Specific action (job_created, review_analyzed, email_sent, etc.)
        message: Human-readable message
        level: Log level (info, warning, error, success)
        details: Additional structured data
        job_id: Related job UUID (optional)
        scrape_job_id: Related scrape job UUID (optional)
        place_id: Related place UUID (optional)
    """
    from database import ActivityLog, get_session

    session = get_session()
    try:
        log_entry = ActivityLog(
            timestamp=datetime.utcnow(),
            level=level,
            category=category,
            action=action,
            message=message,
            details=details or {},
            job_id=job_id,
            scrape_job_id=scrape_job_id,
            place_id=place_id,
        )
        session.add(log_entry)
        session.commit()
        logger.debug(f"Activity logged: [{category}] {action} - {message}")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to log activity: {e}")
    finally:
        session.close()


# Convenience functions for common events

def log_scrape_started(scrape_job_id: str, query: str):
    """Log when a scrape job starts."""
    log_activity(
        category="scraper",
        action="scrape_started",
        message=f"Scrape started: {query}",
        level="info",
        details={"query": query},
        scrape_job_id=scrape_job_id,
    )


def log_scrape_completed(scrape_job_id: str, query: str, places_found: int, reviews_total: int):
    """Log when a scrape job completes."""
    log_activity(
        category="scraper",
        action="scrape_completed",
        message=f"Scrape completed: {query} ({places_found} places, {reviews_total} reviews)",
        level="success",
        details={"query": query, "places_found": places_found, "reviews_total": reviews_total},
        scrape_job_id=scrape_job_id,
    )


def log_scrape_failed(scrape_job_id: str, query: str, error: str):
    """Log when a scrape job fails."""
    log_activity(
        category="scraper",
        action="scrape_failed",
        message=f"Scrape failed: {query}",
        level="error",
        details={"query": query, "error": error},
        scrape_job_id=scrape_job_id,
    )


def log_review_analyzed(job_id: str, place_name: str, sentiment: str, score: float, urgent: bool = False):
    """Log when a review is analyzed."""
    level = "warning" if urgent else "info"
    log_activity(
        category="analysis",
        action="review_analyzed",
        message=f"Review analyzed: {place_name} ({sentiment}, {score:.2f})",
        level=level,
        details={"place_name": place_name, "sentiment": sentiment, "score": score, "urgent": urgent},
        job_id=job_id,
    )


def log_job_completed(job_id: str, place_name: str, total_reviews: int):
    """Log when a processing job completes."""
    log_activity(
        category="job",
        action="job_completed",
        message=f"Job completed: {place_name} ({total_reviews} reviews)",
        level="success",
        details={"place_name": place_name, "total_reviews": total_reviews},
        job_id=job_id,
    )


def log_email_sent(scrape_job_id: str, to_email: str, query: str):
    """Log when an email report is sent."""
    log_activity(
        category="email",
        action="email_sent",
        message=f"Report emailed to {to_email}",
        level="success",
        details={"to_email": to_email, "query": query},
        scrape_job_id=scrape_job_id,
    )


def log_email_failed(scrape_job_id: str, to_email: str, error: str):
    """Log when email sending fails."""
    log_activity(
        category="email",
        action="email_failed",
        message=f"Failed to email {to_email}",
        level="error",
        details={"to_email": to_email, "error": error},
        scrape_job_id=scrape_job_id,
    )


def log_worker_started(worker_id: str = None):
    """Log when a worker starts."""
    log_activity(
        category="worker",
        action="worker_started",
        message=f"Worker started" + (f" (ID: {worker_id})" if worker_id else ""),
        level="info",
        details={"worker_id": worker_id} if worker_id else None,
    )


def log_worker_stopped(worker_id: str = None):
    """Log when a worker stops."""
    log_activity(
        category="worker",
        action="worker_stopped",
        message=f"Worker stopped" + (f" (ID: {worker_id})" if worker_id else ""),
        level="info",
        details={"worker_id": worker_id} if worker_id else None,
    )


def log_system_error(component: str, error: str, details: Dict[str, Any] = None):
    """Log a system error."""
    log_activity(
        category="system",
        action="error",
        message=f"Error in {component}: {error}",
        level="error",
        details={"component": component, "error": error, **(details or {})},
    )


def log_rate_limited(service: str, wait_time: int = None):
    """Log when rate limiting occurs."""
    msg = f"Rate limited by {service}"
    if wait_time:
        msg += f", waiting {wait_time}s"
    log_activity(
        category="system",
        action="rate_limited",
        message=msg,
        level="warning",
        details={"service": service, "wait_time": wait_time},
    )
