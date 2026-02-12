"""
Queue worker for processing review analysis tasks.
Consumes messages from RabbitMQ and analyzes reviews using LLM.
"""

import json
import os
import time
import signal
import sys
import uuid as uuid_module
from datetime import datetime
from sqlalchemy import text

from logging_config import get_logger
from rabbitmq import get_consumer_channel, QUEUE_NAME, ANOMALY_QUEUE_NAME, TAXONOMY_CLUSTERING_QUEUE
from llm_client import analyze_review, generate_anomaly_insight, extract_mentions, analyze_with_taxonomy
from database import Review, ReviewAnalysis, Job, ScrapeJob, Place, AnomalyInsight, RawMention, PlaceTaxonomy, TaxonomyProduct, TaxonomyCategory, get_session
from uuid import UUID
from email_service import send_completion_report, gather_scrape_job_stats
from activity_logger import (
    log_review_analyzed, log_job_completed, log_worker_started,
    log_worker_stopped, log_rate_limited, log_system_error
)
import embedding_client
import vector_store
from vector_store import VectorPayload, MENTIONS_COLLECTION

logger = get_logger(__name__, service="worker")

# Entity resolution threshold for Qdrant similarity
ENTITY_RESOLUTION_THRESHOLD = 0.85


# Valid sentiment values for mentions
VALID_SENTIMENTS = {"positive", "negative", "neutral"}

# Sentiment to numeric mapping for averaging
SENTIMENT_VALUES = {"positive": 1.0, "negative": 0.0, "neutral": 0.5}

# Text matching minimum length (avoids false positives like "بن" matching "بنانا")
TEXT_MATCH_MIN_LENGTH = 3


def _text_matches_product(mention_text: str, canonical_text: str) -> bool:
    """
    Check if mention contains product name or vice versa.

    Used as fast path before vector search to catch obvious matches
    that vectors miss (e.g., "V60 جواتيمالا" contains "v60").
    """
    if not mention_text or not canonical_text:
        return False
    mention = mention_text.lower().strip()
    canonical = canonical_text.lower().strip()
    if len(canonical) >= TEXT_MATCH_MIN_LENGTH and canonical in mention:
        return True
    if len(mention) >= TEXT_MATCH_MIN_LENGTH and mention in canonical:
        return True
    return False


def _update_product_stats(session, product_id: UUID, sentiment: str):
    """
    Update product mention_count and avg_sentiment when a new mention is resolved.
    Uses incremental average formula: new_avg = old_avg + (new_value - old_avg) / new_count
    """
    product = session.query(TaxonomyProduct).filter_by(id=product_id).first()
    if not product:
        return

    sentiment_value = SENTIMENT_VALUES.get(sentiment, 0.5)
    old_count = product.mention_count or 0
    old_avg = float(product.avg_sentiment) if product.avg_sentiment is not None else 0.5

    new_count = old_count + 1
    # Incremental average formula
    new_avg = old_avg + (sentiment_value - old_avg) / new_count

    product.mention_count = new_count
    product.avg_sentiment = round(new_avg, 2)

    logger.debug("Updated product stats",
                extra={"extra_data": {
                    "product_id": str(product_id),
                    "mention_count": new_count,
                    "avg_sentiment": new_avg
                }})


def _update_category_stats(session, category_id: UUID, sentiment: str):
    """
    Update category mention_count and avg_sentiment when a new mention is resolved.
    Uses incremental average formula.
    """
    category = session.query(TaxonomyCategory).filter_by(id=category_id).first()
    if not category:
        return

    sentiment_value = SENTIMENT_VALUES.get(sentiment, 0.5)
    old_count = category.mention_count or 0
    old_avg = float(category.avg_sentiment) if category.avg_sentiment is not None else 0.5

    new_count = old_count + 1
    new_avg = old_avg + (sentiment_value - old_avg) / new_count

    category.mention_count = new_count
    category.avg_sentiment = round(new_avg, 2)

    logger.debug("Updated category stats",
                extra={"extra_data": {
                    "category_id": str(category_id),
                    "mention_count": new_count,
                    "avg_sentiment": new_avg
                }})


def get_active_taxonomy_for_place(session, place_id) -> PlaceTaxonomy:
    """Get the active (published) taxonomy for a place, if any."""
    return session.query(PlaceTaxonomy).filter_by(
        place_id=place_id,
        status="active"
    ).first()


def get_approved_products_for_taxonomy(session, taxonomy_id) -> list:
    """
    Get approved products for a taxonomy formatted for LLM prompt.

    Returns:
        List of dicts with {id, name, variants}
    """
    products = session.query(TaxonomyProduct).filter_by(
        taxonomy_id=taxonomy_id,
        is_approved=True
    ).all()

    return [
        {
            "id": str(p.id),
            "name": p.display_name or p.canonical_text,
            "variants": p.variants or []
        }
        for p in products
    ]


def get_approved_categories_for_taxonomy(session, taxonomy_id) -> list:
    """
    Get approved categories for a taxonomy formatted for LLM prompt.

    Returns:
        List of dicts with {id, name}
    """
    categories = session.query(TaxonomyCategory).filter_by(
        taxonomy_id=taxonomy_id,
        is_approved=True
    ).all()

    return [
        {
            "id": str(c.id),
            "name": c.display_name_en or c.name
        }
        for c in categories
    ]


# BUG-004 FIX: Removed _increment_product_stats() and _increment_category_stats()
# Stats are now computed ONLY via _aggregate_taxonomy_analytics() during publish.
# This ensures single source of truth (RawMention table) for all statistics.
# Live updates were causing conflicts with batch aggregation on re-publish.


def process_mentions(review_id: str, place_id, review_text: str, analysis: dict):
    """
    Extract mentions from review and save to RawMention table with entity resolution.

    This is non-blocking - failures are logged but don't affect review analysis.

    Args:
        review_id: UUID of the review
        place_id: UUID of the place
        review_text: Original review text
        analysis: Analysis result (reserved for future use - e.g., sentiment fallback)
    """
    try:
        # Check if mentions already extracted for this review (avoid duplicates on requeue)
        session = get_session()
        try:
            existing_count = session.query(RawMention).filter_by(review_id=review_id).count()
            if existing_count > 0:
                logger.debug("Mentions already exist for review, skipping",
                           extra={"extra_data": {"review_id": review_id, "count": existing_count}})
                return
        finally:
            session.close()

        # Extract mentions via LLM
        mentions_result = extract_mentions(review_text)

        products = mentions_result.get("products", [])
        aspects = mentions_result.get("aspects", [])

        if not products and not aspects:
            logger.debug("No mentions extracted", extra={"extra_data": {"review_id": review_id}})
            return

        # Combine all mentions for batch embedding
        all_mentions = []
        for p in products:
            sentiment = p["sentiment"] if p["sentiment"] in VALID_SENTIMENTS else "neutral"
            all_mentions.append({"text": p["text"], "sentiment": sentiment, "type": "product"})
        for a in aspects:
            sentiment = a["sentiment"] if a["sentiment"] in VALID_SENTIMENTS else "neutral"
            all_mentions.append({"text": a["text"], "sentiment": sentiment, "type": "aspect"})

        # Batch generate embeddings
        texts = [m["text"] for m in all_mentions]
        embeddings = embedding_client.generate_embeddings(texts, normalize=True)

        if embeddings is None:
            logger.warning("Embedding generation failed, skipping mention processing",
                         extra={"extra_data": {"review_id": review_id}})
            return

        # Process each mention: resolve entity, save to DB
        session = get_session()
        try:
            # Check once if active taxonomy exists for this place
            active_taxonomy_id = vector_store.get_active_taxonomy_id(str(place_id))

            for mention, embedding in zip(all_mentions, embeddings):
                if embedding is None or all(v == 0.0 for v in embedding):
                    logger.debug("Skipping mention with zero embedding",
                               extra={"extra_data": {"text": mention["text"]}})
                    continue

                qdrant_point_id = None
                mention_type = mention["type"]

                # Try entity resolution via Qdrant
                if vector_store.is_available():
                    # Search for similar existing mention
                    existing = vector_store.find_similar_mention(
                        text_embedding=embedding,
                        place_id=str(place_id),
                        mention_type=mention_type,
                        threshold=ENTITY_RESOLUTION_THRESHOLD,
                    )

                    if existing:
                        # Found similar - use existing canonical
                        qdrant_point_id = existing.payload.canonical_id or existing.id

                        # Increment mention count in Qdrant
                        sentiment_delta = 1.0 if mention["sentiment"] == "positive" else (-1.0 if mention["sentiment"] == "negative" else 0.0)
                        vector_store.increment_mention_count(
                            MENTIONS_COLLECTION,
                            qdrant_point_id,
                            sentiment_delta=sentiment_delta,
                        )

                        logger.debug("Resolved to existing mention",
                                   extra={"extra_data": {
                                       "text": mention["text"],
                                       "canonical": existing.payload.text,
                                       "score": existing.score
                                   }})
                    else:
                        # New mention - create canonical in Qdrant
                        qdrant_point_id = str(uuid_module.uuid4())

                        payload = VectorPayload(
                            text=mention["text"],
                            place_id=str(place_id),
                            mention_type=mention_type,
                            is_canonical=True,
                            canonical_id=qdrant_point_id,
                            sentiment_sum=1.0 if mention["sentiment"] == "positive" else (-1.0 if mention["sentiment"] == "negative" else 0.0),
                            mention_count=1,
                        )

                        success = vector_store.upsert_vector(
                            collection_name=MENTIONS_COLLECTION,
                            vector_id=qdrant_point_id,
                            vector=embedding,
                            payload=payload,
                        )

                        if not success:
                            # Queue for retry
                            vector_store.queue_for_retry(
                                "upsert",
                                (MENTIONS_COLLECTION, qdrant_point_id, embedding, payload),
                                {}
                            )
                            qdrant_point_id = None  # Will be set later when retry succeeds

                        logger.debug("Created new canonical mention",
                                   extra={"extra_data": {"text": mention["text"], "id": qdrant_point_id}})
                else:
                    # Qdrant unavailable - save without resolution
                    logger.debug("Qdrant unavailable, saving mention without resolution",
                               extra={"extra_data": {"text": mention["text"]}})

                # Resolve to active taxonomy if exists
                resolved_product_id = None
                resolved_category_id = None
                resolution_method = None

                if active_taxonomy_id:
                    mention_sentiment = mention.get("sentiment", "neutral")

                    # FAST PATH: Try text matching first (catches "V60 جواتيمالا" → "V60")
                    if mention_type == "product":
                        taxonomy_products = session.query(TaxonomyProduct).filter_by(
                            taxonomy_id=active_taxonomy_id
                        ).all()
                        for product in taxonomy_products:
                            if _text_matches_product(mention["text"], product.canonical_text):
                                resolved_product_id = product.id
                                resolved_category_id = product.assigned_category_id
                                resolution_method = "text"
                                _update_product_stats(session, resolved_product_id, mention_sentiment)
                                if resolved_category_id:
                                    _update_category_stats(session, resolved_category_id, mention_sentiment)
                                logger.debug("Text-matched mention to product",
                                           extra={"extra_data": {"text": mention["text"], "product": product.canonical_text}})
                                break

                    # FALLBACK: Vector similarity search (handles synonyms, misspellings)
                    if resolved_product_id is None and embedding is not None:
                        result = vector_store.find_matching_product(
                            text_embedding=embedding,
                            place_id=str(place_id),
                            mention_type=mention_type,
                        )

                        if result:
                            payload = result.payload
                            resolution_method = "vector"
                            if payload.entity_type == "product":
                                resolved_product_id = UUID(payload.entity_id)
                                if payload.category_id:
                                    resolved_category_id = UUID(payload.category_id)
                                _update_product_stats(session, resolved_product_id, mention_sentiment)
                                if resolved_category_id:
                                    _update_category_stats(session, resolved_category_id, mention_sentiment)
                                logger.debug("Vector-matched mention to product",
                                           extra={"extra_data": {"text": mention["text"], "product_id": str(resolved_product_id)}})
                            else:
                                resolved_category_id = UUID(payload.entity_id)
                                _update_category_stats(session, resolved_category_id, mention_sentiment)
                                logger.debug("Vector-matched mention to category",
                                           extra={"extra_data": {"text": mention["text"], "category_id": str(resolved_category_id)}})

                # Save RawMention to database
                raw_mention = RawMention(
                    review_id=review_id,
                    place_id=place_id,
                    mention_text=mention["text"],
                    mention_type=mention_type,
                    sentiment=mention["sentiment"],
                    qdrant_point_id=qdrant_point_id,
                    resolved_product_id=resolved_product_id,
                    resolved_category_id=resolved_category_id,
                )
                session.add(raw_mention)

            session.commit()
            logger.info("Mentions processed",
                       extra={"extra_data": {
                           "review_id": review_id,
                           "products": len(products),
                           "aspects": len(aspects)
                       }})

        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

    except Exception as e:
        # Non-blocking - log and continue
        logger.warning(f"Mention extraction failed for review {review_id}: {e}",
                      extra={"extra_data": {"review_id": review_id, "error": str(e)}})


# Graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    logger.info("Shutdown signal received, finishing current task...")
    shutdown_requested = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def detect_and_queue_anomalies(job_id: str):
    """
    Detect sentiment anomalies for a completed job's place and queue LLM insight generation.
    Called automatically when a job completes.
    """
    import statistics
    from collections import defaultdict
    from rabbitmq import get_channel

    session = get_session()
    try:
        # Get the job and place
        job = session.query(Job).filter_by(id=job_id).first()
        if not job or not job.place_id:
            return

        place_id = job.place_id

        # Get all reviews for this place with analyses
        reviews = session.query(Review).filter_by(place_id=place_id).all()
        if not reviews:
            return

        review_ids = [r.id for r in reviews]
        analyses = session.query(ReviewAnalysis).filter(ReviewAnalysis.review_id.in_(review_ids)).all()
        analysis_map = {a.review_id: a for a in analyses}

        # Parse review dates
        def parse_review_date(date_str):
            if not date_str:
                return None
            try:
                parts = date_str.split('-')
                if len(parts) == 3:
                    return datetime(int(parts[0]), int(parts[1]), int(parts[2])).date()
            except:
                pass
            return None

        # Build daily aggregation for ALL historical data
        daily_data = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "total": 0, "reviews": []})

        for r in reviews:
            review_date = parse_review_date(r.review_date)
            analysis = analysis_map.get(r.id)
            if not review_date or not analysis:
                continue

            date_key = review_date.isoformat()
            daily_data[date_key]["total"] += 1
            daily_data[date_key]["reviews"].append({
                "id": str(r.id),
                "text": r.text[:200] if r.text else "",
                "rating": r.rating,
                "sentiment": analysis.sentiment,
                "topics_positive": analysis.topics_positive or [],
                "topics_negative": analysis.topics_negative or [],
            })

            if analysis.sentiment == "positive":
                daily_data[date_key]["positive"] += 1
            elif analysis.sentiment == "negative":
                daily_data[date_key]["negative"] += 1
            else:
                daily_data[date_key]["neutral"] += 1

        if not daily_data:
            return

        # Calculate positive percentages
        trend_data = []
        for date_key, data in sorted(daily_data.items()):
            if data["total"] > 0:
                positive_pct = round(data["positive"] / data["total"] * 100)
                trend_data.append({
                    "date": date_key,
                    "positive_pct": positive_pct,
                    "total": data["total"],
                    "reviews": data["reviews"],
                    "positive": data["positive"],
                    "negative": data["negative"],
                })

        if len(trend_data) < 3:
            return

        # Statistical anomaly detection (2σ)
        positive_pcts = [p["positive_pct"] for p in trend_data]
        mean_pct = statistics.mean(positive_pcts)
        try:
            std_pct = statistics.stdev(positive_pcts)
        except statistics.StatisticsError:
            return

        if std_pct == 0:
            return

        # Find anomalies and queue insight generation
        channel = None
        for point in trend_data:
            z_score = (point["positive_pct"] - mean_pct) / std_pct

            if abs(z_score) > 2:
                anomaly_type = "spike" if z_score > 0 else "drop"
                magnitude = round(point["positive_pct"] - mean_pct, 1)

                # Check if insight already exists
                existing = session.query(AnomalyInsight).filter(
                    AnomalyInsight.date == point["date"],
                    AnomalyInsight.place_id == place_id,
                    AnomalyInsight.topic.is_(None)
                ).first()

                if existing:
                    continue

                # Build context for LLM
                topic_counts = defaultdict(lambda: {"positive": 0, "negative": 0})
                for rd in point["reviews"]:
                    for t in rd.get("topics_positive", []):
                        topic_counts[t]["positive"] += 1
                    for t in rd.get("topics_negative", []):
                        topic_counts[t]["negative"] += 1

                topic_comp = "\n".join([
                    f"- {t}: +{c['positive']} positive, -{c['negative']} negative"
                    for t, c in sorted(topic_counts.items(), key=lambda x: -(x[1]['positive'] + x[1]['negative']))[:5]
                ]) or "No specific topics identified"

                reviews_summary = "\n".join([
                    f"- [{rd['sentiment']}] \"{rd['text'][:100]}...\" (Rating: {rd.get('rating', 'N/A')})"
                    for rd in point["reviews"][:5]
                ]) or "No reviews available"

                # Generate reason
                reason_parts = []
                if anomaly_type == "drop":
                    neg_topics = sorted(topic_counts.items(), key=lambda x: -x[1]["negative"])
                    if neg_topics and neg_topics[0][1]["negative"] > 0:
                        reason_parts.append(f"'{neg_topics[0][0]}' complaints: {neg_topics[0][1]['negative']}")
                else:
                    pos_topics = sorted(topic_counts.items(), key=lambda x: -x[1]["positive"])
                    if pos_topics and pos_topics[0][1]["positive"] > 0:
                        reason_parts.append(f"'{pos_topics[0][0]}' praised: {pos_topics[0][1]['positive']}x")

                reason = f"Sentiment {'dropped' if anomaly_type == 'drop' else 'spiked'} {abs(magnitude):.0f}%"
                if reason_parts:
                    reason += f" - {', '.join(reason_parts)}"

                # Queue for LLM processing
                task_data = {
                    "type": "anomaly_insight",
                    "date": point["date"],
                    "place_id": str(place_id),
                    "topic": None,
                    "anomaly_type": anomaly_type,
                    "magnitude": magnitude,
                    "reason": reason,
                    "topic_comparison": topic_comp,
                    "reviews_summary": reviews_summary,
                    "review_ids": [rd["id"] for rd in point["reviews"]]
                }

                try:
                    if channel is None:
                        channel = get_channel()
                    channel.basic_publish(
                        exchange='',
                        routing_key='anomaly_insights',
                        body=json.dumps(task_data)
                    )
                    logger.info(f"Queued anomaly insight for {point['date']}", extra={"extra_data": {"place_id": str(place_id), "type": anomaly_type}})
                except Exception as e:
                    logger.warning(f"Failed to queue anomaly insight: {e}")

    except Exception as e:
        logger.error(f"Error detecting anomalies for job {job_id}: {e}", exc_info=True)
    finally:
        session.close()


def update_job_progress(job_id: str):
    """Increment processed_reviews count and check for scrape job completion."""
    session = get_session()
    job_completed = False
    place_name = None
    total_reviews = 0
    try:
        # Atomic increment to avoid race condition with multiple workers
        session.query(Job).filter_by(id=job_id).update(
            {Job.processed_reviews: Job.processed_reviews + 1},
            synchronize_session=False
        )
        session.commit()

        # Re-read to check completion
        job = session.query(Job).filter_by(id=job_id).first()
        if job:
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
            elif job.status != "processing":
                job.status = "processing"
            session.commit()
    finally:
        session.close()

    # Log job completion
    if job_completed and place_name:
        log_job_completed(job_id, place_name, total_reviews)

    # If this job just completed, run anomaly detection for this place
    if job_completed:
        detect_and_queue_anomalies(job_id)
        check_and_send_scrape_job_report(job_id)
        # Trigger taxonomy clustering if conditions are met
        from clustering_job import trigger_taxonomy_clustering
        trigger_taxonomy_clustering(job_id)
        # Invalidate insights cache so next request gets fresh data
        try:
            from redis_client import invalidate_insights
            s = get_session()
            try:
                job_obj = s.query(Job).filter_by(id=job_id).first()
                if job_obj and job_obj.place_id:
                    invalidate_insights(str(job_obj.place_id))
            finally:
                s.close()
        except Exception as e:
            logger.warning(f"Failed to invalidate insights cache: {e}")


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
            needs_action=analysis.get("needs_action", False),
            action_ar=analysis.get("action_ar"),
            action_en=analysis.get("action_en"),
            raw_response=analysis,
        )
        session.add(review_analysis)
        session.commit()
    finally:
        session.close()


def process_message(ch, method, properties, body):
    """
    Process a single review message.

    Supports three modes via message["mode"]:
    - "extraction": Only extract mentions (no sentiment analysis)
    - "sentiment": Only sentiment analysis (uses taxonomy if available)
    - "full" (default): Both extraction and sentiment analysis
    """
    global shutdown_requested

    try:
        message = json.loads(body)
        review_id = message["review_id"]
        job_id = message["job_id"]
        mode = message.get("mode", "full")  # "extraction" | "sentiment" | "full"

        logger.info("Processing review", extra={"extra_data": {"review_id": review_id, "job_id": job_id, "mode": mode}})

        # Fetch review from DB
        session = get_session()
        place_name = None
        place_id = None
        try:
            review = session.query(Review).filter_by(id=review_id).first()
            if not review:
                logger.warning("Review not found, acknowledging", extra={"extra_data": {"review_id": review_id}})
                ch.basic_ack(delivery_tag=method.delivery_tag)
                update_job_progress(job_id)  # BUG FIX: Must update progress even for missing reviews
                return

            review_text = review.text
            review_rating = review.rating
            place_id = review.place_id

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

        # Determine processing mode
        # Environment variable overrides "full" mode only — explicit "sentiment" from publish is never blocked
        extraction_only_env = os.environ.get("EXTRACTION_ONLY_MODE", "").lower() == "true"
        if extraction_only_env and mode == "full":
            mode = "extraction"

        # Mode: extraction - Only extract mentions, skip sentiment analysis
        # Used when building taxonomy before running full analysis
        if mode == "extraction":
            if place_id:
                process_mentions(review_id, place_id, review_text, {})
            logger.info("Extraction complete (no analysis)", extra={"extra_data": {"review_id": review_id}})
            ch.basic_ack(delivery_tag=method.delivery_tag)
            update_job_progress(job_id)
            return

        # Mode: sentiment or full - Run sentiment analysis
        # Check if we have an active taxonomy for taxonomy-aware analysis
        taxonomy = None
        approved_products = []
        approved_categories = []

        if place_id:
            session = get_session()
            try:
                taxonomy = get_active_taxonomy_for_place(session, place_id)
                if taxonomy:
                    approved_products = get_approved_products_for_taxonomy(session, taxonomy.id)
                    approved_categories = get_approved_categories_for_taxonomy(session, taxonomy.id)
                    logger.debug("Using taxonomy-aware analysis",
                               extra={"extra_data": {
                                   "taxonomy_id": str(taxonomy.id),
                                   "products": len(approved_products),
                                   "categories": len(approved_categories)
                               }})
            finally:
                session.close()

        # Call LLM API with retry logic
        max_retries = 3
        retry_delay = 30  # seconds
        analysis = None

        for attempt in range(max_retries):
            try:
                # Use taxonomy-aware analysis if taxonomy exists
                if taxonomy and (approved_products or approved_categories):
                    analysis = analyze_with_taxonomy(
                        review_text,
                        approved_products,
                        approved_categories,
                        review_rating
                    )
                else:
                    # Fallback to original analysis (no taxonomy)
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
                        update_job_progress(job_id)  # BUG FIX: Must update progress even for dead-lettered reviews
                        return

        # Save analysis
        save_analysis(review_id, analysis)

        # Mode: full - Also extract and save mentions
        # Skip extraction for "sentiment" mode (mentions already extracted)
        if mode == "full" and place_id:
            process_mentions(review_id, place_id, review_text, analysis)

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


def process_anomaly_insight(ch, method, properties, body):
    """Process an anomaly insight generation request."""
    try:
        message = json.loads(body)

        date = message["date"]
        place_id = message.get("place_id")
        topic = message.get("topic")
        anomaly_type = message["anomaly_type"]
        magnitude = message["magnitude"]
        reason = message["reason"]
        topic_comparison = message["topic_comparison"]
        reviews_summary = message["reviews_summary"]
        review_ids = message.get("review_ids", [])

        logger.info(f"Generating anomaly insight for {date}", extra={"extra_data": {"date": date, "type": anomaly_type}})

        session = get_session()
        try:
            # Check if already exists (avoid duplicates)
            existing = session.query(AnomalyInsight).filter(
                AnomalyInsight.date == date,
                AnomalyInsight.place_id == place_id if place_id else AnomalyInsight.place_id.is_(None),
                AnomalyInsight.topic == topic if topic else AnomalyInsight.topic.is_(None)
            ).first()

            if existing:
                logger.debug(f"Anomaly insight already exists for {date}, skipping")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Generate LLM insight
            insight = generate_anomaly_insight(
                anomaly_date=date,
                anomaly_type=anomaly_type,
                magnitude=magnitude,
                topic_comparison=topic_comparison,
                reviews_summary=reviews_summary
            )

            # Convert review_ids to UUIDs
            import uuid
            review_uuid_list = []
            for rid in review_ids:
                try:
                    review_uuid_list.append(uuid.UUID(rid) if isinstance(rid, str) else rid)
                except:
                    pass

            # Save to database
            anomaly_insight = AnomalyInsight(
                place_id=uuid.UUID(place_id) if place_id else None,
                date=date,
                topic=topic,
                anomaly_type=anomaly_type,
                magnitude=magnitude,
                reason=reason,
                analysis=insight.get("analysis"),
                analysis_ar=insight.get("analysis_ar"),
                recommendation=insight.get("recommendation"),
                recommendation_ar=insight.get("recommendation_ar"),
                review_ids=review_uuid_list if review_uuid_list else None
            )
            session.add(anomaly_insight)
            session.commit()

            logger.info(f"Anomaly insight saved for {date}", extra={"extra_data": {"date": date}})
            ch.basic_ack(delivery_tag=method.delivery_tag)

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error processing anomaly insight: {e}", exc_info=True)
        # Requeue for retry
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        time.sleep(5)


def run_worker():
    """Start consuming messages from queue."""
    global shutdown_requested

    logger.info("Connecting to RabbitMQ...")
    connection, channel = get_consumer_channel()

    # Initialize Qdrant collections for taxonomy system (non-blocking)
    if vector_store.is_available():
        vector_store.initialize_collections()
    else:
        logger.warning("Qdrant not available at startup, mentions will queue for retry")

    logger.info(f"Worker started, listening on queues: '{QUEUE_NAME}', '{ANOMALY_QUEUE_NAME}', '{TAXONOMY_CLUSTERING_QUEUE}'")
    log_worker_started()

    # Set up consumers for all queues
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)
    channel.basic_consume(queue=ANOMALY_QUEUE_NAME, on_message_callback=process_anomaly_insight)
    # Taxonomy clustering consumer
    from clustering_job import process_clustering_message
    channel.basic_consume(queue=TAXONOMY_CLUSTERING_QUEUE, on_message_callback=process_clustering_message)

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
