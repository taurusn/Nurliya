"""
Producer for queuing reviews for analysis.
Parses CSV files and publishes review messages to RabbitMQ.
"""

import argparse
from datetime import datetime

from logging_config import get_logger
from csv_parser import parse_csv, save_place_and_reviews
from rabbitmq import get_producer_channel, publish_message
from database import Job, get_session

logger = get_logger(__name__, service="producer")


def create_job(place_id: str, total_reviews: int) -> Job:
    """Create a new job record."""
    session = get_session()
    try:
        job = Job(
            place_id=place_id,
            status="pending",
            total_reviews=total_reviews,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        logger.debug("Created job", extra={"extra_data": {"job_id": str(job.id), "place_id": place_id, "total_reviews": total_reviews}})
        return job
    finally:
        session.close()


def update_job_status(job_id: str, status: str):
    """Update job status."""
    session = get_session()
    try:
        job = session.query(Job).filter_by(id=job_id).first()
        if job:
            job.status = status
            if status == "completed":
                job.completed_at = datetime.utcnow()
            session.commit()
            logger.debug("Updated job status", extra={"extra_data": {"job_id": job_id, "status": status}})
    finally:
        session.close()


def run_producer(csv_path: str):
    """Parse CSV, save to DB, and queue reviews for analysis."""
    logger.info("Starting producer", extra={"extra_data": {"csv_path": csv_path}})

    # Parse CSV
    places = parse_csv(csv_path)
    logger.info("CSV parsed", extra={"extra_data": {"places_count": len(places)}})

    # Connect to RabbitMQ
    connection, channel = get_producer_channel()

    total_queued = 0

    for place_data in places:
        logger.info("Processing place", extra={"extra_data": {"name": place_data['name']}})

        # Save place and reviews to DB (returns IDs)
        place_id, review_ids = save_place_and_reviews(place_data)

        if not review_ids:
            logger.debug("No reviews to process", extra={"extra_data": {"place_name": place_data['name']}})
            continue

        # Create job
        job = create_job(place_id=place_id, total_reviews=len(review_ids))

        # Update reviews with job_id and queue them
        session = get_session()
        try:
            from database import Review
            for review_id in review_ids:
                # Update review with job_id
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
                total_queued += 1
        finally:
            session.close()

        # Update job status
        update_job_status(str(job.id), "queued")
        logger.info(
            "Queued reviews for place",
            extra={"extra_data": {"place_name": place_data['name'], "job_id": str(job.id), "reviews_queued": len(review_ids)}}
        )

    connection.close()
    logger.info("Producer complete", extra={"extra_data": {"total_queued": total_queued}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse CSV and queue reviews")
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    args = parser.parse_args()

    run_producer(args.csv)
