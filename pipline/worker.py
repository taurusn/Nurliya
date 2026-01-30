import json
import time
import signal
import sys
from datetime import datetime
from rabbitmq import get_consumer_channel, QUEUE_NAME
from llm_client import analyze_review
from database import Review, ReviewAnalysis, Job, get_session


# Graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    global shutdown_requested
    print("\nShutdown requested, finishing current task...")
    shutdown_requested = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def update_job_progress(job_id: str):
    """Increment processed_reviews count."""
    session = get_session()
    try:
        job = session.query(Job).filter_by(id=job_id).first()
        if job:
            job.processed_reviews += 1
            if job.processed_reviews >= job.total_reviews:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
            else:
                job.status = "processing"
            session.commit()
    finally:
        session.close()


def save_analysis(review_id: str, analysis: dict):
    """Save analysis result to database."""
    session = get_session()
    try:
        # Check if already analyzed
        existing = session.query(ReviewAnalysis).filter_by(review_id=review_id).first()
        if existing:
            print(f"  Review {review_id} already analyzed, skipping")
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

        print(f"Processing review: {review_id}")

        # Fetch review from DB
        session = get_session()
        try:
            review = session.query(Review).filter_by(id=review_id).first()
            if not review:
                print(f"  Review not found, acknowledging")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            review_text = review.text
            review_rating = review.rating
        finally:
            session.close()

        if not review_text:
            print(f"  Empty review text, skipping")
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
                        print(f"  Rate limited, waiting {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"  Rate limit exceeded, requeueing")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        return
                else:
                    print(f"  Error: {error_msg}")
                    if attempt < max_retries - 1:
                        time.sleep(5)
                    else:
                        # Dead letter after max retries
                        print(f"  Max retries reached, dead-lettering")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                        return

        # Save analysis
        save_analysis(review_id, analysis)
        print(f"  Sentiment: {analysis.get('sentiment')} ({analysis.get('score')})")

        # Update job progress
        update_job_progress(job_id)

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

        # Small delay between requests to avoid rate limits
        time.sleep(2)

    except Exception as e:
        print(f"  Unexpected error: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def run_worker():
    """Start consuming messages from queue."""
    global shutdown_requested

    print("Connecting to RabbitMQ...")
    connection, channel = get_consumer_channel()

    print(f"Waiting for messages on queue '{QUEUE_NAME}'...")
    print("Press Ctrl+C to stop\n")

    # Set up consumer
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

    try:
        while not shutdown_requested:
            connection.process_data_events(time_limit=1)
    except KeyboardInterrupt:
        pass
    finally:
        print("Closing connection...")
        connection.close()
        print("Worker stopped")


if __name__ == "__main__":
    run_worker()
