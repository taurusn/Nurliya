import argparse
from datetime import datetime
from csv_parser import parse_csv, save_place_and_reviews
from rabbitmq import get_producer_channel, publish_message
from database import Job, get_session


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
    finally:
        session.close()


def run_producer(csv_path: str):
    """Parse CSV, save to DB, and queue reviews for analysis."""
    print(f"Parsing CSV: {csv_path}")

    # Parse CSV
    places = parse_csv(csv_path)
    print(f"Found {len(places)} places")

    # Connect to RabbitMQ
    connection, channel = get_producer_channel()

    total_queued = 0

    for place_data in places:
        print(f"\nProcessing: {place_data['name']}")

        # Save place and reviews to DB (returns IDs)
        place_id, review_ids = save_place_and_reviews(place_data)
        print(f"  Saved {len(review_ids)} reviews to DB")

        if not review_ids:
            print("  No reviews to process")
            continue

        # Create job
        job = create_job(place_id=place_id, total_reviews=len(review_ids))
        print(f"  Created job: {job.id}")

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
        print(f"  Queued {len(review_ids)} reviews")

    connection.close()
    print(f"\nDone! Total reviews queued: {total_queued}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse CSV and queue reviews")
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    args = parser.parse_args()

    run_producer(args.csv)
