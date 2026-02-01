"""
FastAPI application for Nurliya Pipeline.
Provides REST API for scraping, job tracking, and review analysis.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Set
from uuid import UUID
from sqlalchemy import func, text

from logging_config import get_logger
from database import Place, Review, ReviewAnalysis, Job, ScrapeJob, ActivityLog, User, get_session, create_tables
from config import RABBITMQ_URL, QUEUE_NAME
from scraper_client import ScraperClient
from auth import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    register_user, authenticate_user, create_access_token,
    get_current_user, get_optional_user
)

logger = get_logger(__name__, service="api")


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.last_analysis_id: Optional[str] = None
        self.last_log_id: Optional[str] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.active_connections.discard(conn)


manager = ConnectionManager()


# Background task for polling new analyses
async def poll_database():
    """Poll database for new analyses and broadcast to WebSocket clients."""
    while True:
        try:
            if manager.active_connections:
                session = get_session()
                try:
                    # Get latest analysis
                    latest = (
                        session.query(ReviewAnalysis)
                        .order_by(ReviewAnalysis.analyzed_at.desc())
                        .first()
                    )

                    if latest and str(latest.id) != manager.last_analysis_id:
                        manager.last_analysis_id = str(latest.id)

                        # Get place name through review
                        place_name = None
                        if latest.review and latest.review.place:
                            place_name = latest.review.place.name

                        # Broadcast new analysis
                        await manager.broadcast({
                            "type": "analysis",
                            "data": {
                                "review_id": str(latest.review_id),
                                "place_name": place_name,
                                "sentiment": latest.sentiment,
                                "score": float(latest.score) if latest.score else None,
                                "summary_en": latest.summary_en,
                                "analyzed_at": latest.analyzed_at.isoformat() if latest.analyzed_at else None,
                            }
                        })

                    # Broadcast stats update
                    places_count = session.query(Place).count()
                    reviews_count = session.query(Review).count()
                    analyses_count = session.query(ReviewAnalysis).count()

                    # Get job status counts
                    job_statuses = (
                        session.query(ScrapeJob.status, func.count(ScrapeJob.id))
                        .group_by(ScrapeJob.status)
                        .all()
                    )
                    scrape_jobs = {status: count for status, count in job_statuses}

                    # Get active jobs
                    active_jobs = (
                        session.query(ScrapeJob)
                        .filter(ScrapeJob.status.in_(["pending", "scraping", "processing"]))
                        .all()
                    )

                    await manager.broadcast({
                        "type": "stats",
                        "data": {
                            "places_count": places_count,
                            "reviews_count": reviews_count,
                            "analyses_count": analyses_count,
                            "pending_analyses": reviews_count - analyses_count,
                            "scrape_jobs": {
                                "pending": scrape_jobs.get("pending", 0),
                                "scraping": scrape_jobs.get("scraping", 0),
                                "processing": scrape_jobs.get("processing", 0),
                                "completed": scrape_jobs.get("completed", 0),
                                "failed": scrape_jobs.get("failed", 0),
                            },
                            "active_jobs": [
                                {
                                    "id": str(job.id),
                                    "query": job.query,
                                    "status": job.status,
                                    "places_found": job.places_found or 0,
                                    "reviews_total": job.reviews_total or 0,
                                    "reviews_processed": job.reviews_processed or 0,
                                }
                                for job in active_jobs
                            ]
                        }
                    })

                    # Broadcast new activity logs
                    latest_log = (
                        session.query(ActivityLog)
                        .order_by(ActivityLog.timestamp.desc())
                        .first()
                    )

                    if latest_log and str(latest_log.id) != manager.last_log_id:
                        manager.last_log_id = str(latest_log.id)

                        # Get recent logs (last 5 new ones)
                        recent_logs = (
                            session.query(ActivityLog)
                            .order_by(ActivityLog.timestamp.desc())
                            .limit(5)
                            .all()
                        )

                        await manager.broadcast({
                            "type": "logs",
                            "data": [
                                {
                                    "id": str(log.id),
                                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                                    "level": log.level,
                                    "category": log.category,
                                    "action": log.action,
                                    "message": log.message,
                                    "details": log.details,
                                }
                                for log in recent_logs
                            ]
                        })
                finally:
                    session.close()
        except Exception as e:
            logger.error("WebSocket poll error", exc_info=True)

        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Nurliya API...")
    create_tables()
    # Start background polling task
    poll_task = asyncio.create_task(poll_database())
    logger.info("API started successfully")
    yield
    logger.info("Shutting down API...")
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass
    logger.info("API shutdown complete")


from orchestrator import (
    create_scrape_job,
    get_scrape_job_progress,
    run_scrape_pipeline,
)

app = FastAPI(
    title="Nurliya API",
    description="AI-powered sentiment analysis for Saudi business reviews",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class ScrapeRequest(BaseModel):
    query: str = Field(..., description="Search query (e.g., 'coffee shops in Riyadh')")
    depth: int = Field(10, ge=1, le=50, description="Scroll depth for results")
    lang: str = Field("en", description="Language code (en, ar)")
    max_time: int = Field(300, ge=60, le=1800, description="Max scrape time in seconds")
    notification_email: Optional[EmailStr] = Field(None, description="Email address for completion report")


class ScrapeResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobProgressResponse(BaseModel):
    job_id: str
    query: str
    status: str
    scraper_job_id: Optional[str]
    places_found: int
    reviews_total: int
    reviews_processed: int
    error_message: Optional[str]
    created_at: Optional[str]
    completed_at: Optional[str]


class PlaceSummary(BaseModel):
    id: str
    name: str
    category: Optional[str]
    address: Optional[str]
    rating: Optional[float]
    review_count: int
    analyzed_count: int


class PlacesListResponse(BaseModel):
    places: List[PlaceSummary]
    total: int


class ReviewAnalysisData(BaseModel):
    sentiment: Optional[str]
    score: Optional[float]
    topics_positive: List[str]
    topics_negative: List[str]
    language: Optional[str]
    urgent: bool
    summary_ar: Optional[str]
    summary_en: Optional[str]
    suggested_reply_ar: Optional[str]


class ReviewWithAnalysis(BaseModel):
    id: str
    author: Optional[str]
    rating: Optional[int]
    text: Optional[str]
    review_date: Optional[str]
    analysis: Optional[ReviewAnalysisData]


class PlaceDetailResponse(BaseModel):
    id: str
    name: str
    category: Optional[str]
    address: Optional[str]
    rating: Optional[float]
    review_count: int
    metadata: Optional[dict]


class PlaceReviewsResponse(BaseModel):
    place: PlaceDetailResponse
    reviews: List[ReviewWithAnalysis]
    total: int


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers."""
    # Check scraper availability
    client = ScraperClient()
    scraper_healthy = await client.health_check()

    return {
        "status": "healthy",
        "scraper": "connected" if scraper_healthy else "disconnected",
    }


# Auth endpoints
@app.post("/api/auth/register", response_model=TokenResponse)
async def api_register(data: UserCreate):
    """Register a new user account."""
    user = register_user(data)
    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            created_at=user.created_at.isoformat() if user.created_at else None,
        )
    )


@app.post("/api/auth/login", response_model=TokenResponse)
async def api_login(data: UserLogin):
    """Login and get access token."""
    user = authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )
    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            created_at=user.created_at.isoformat() if user.created_at else None,
        )
    )


@app.get("/api/auth/me", response_model=UserResponse)
async def api_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
    )


# Scrape endpoints
@app.post("/api/scrape", response_model=ScrapeResponse)
async def start_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Start a new scrape job for the authenticated user.

    This will:
    1. Create a scrape job record
    2. Start the Google Maps scraper in the background
    3. Automatically process results when scraping completes
    """
    # Create job record with user_id
    job = create_scrape_job(
        request.query,
        notification_email=request.notification_email,
        user_id=str(current_user.id)
    )

    # Start background task
    background_tasks.add_task(
        run_scrape_pipeline,
        query=request.query,
        scrape_job_id=str(job.id),
        depth=request.depth,
        lang=request.lang,
        max_time=request.max_time,
    )

    return ScrapeResponse(
        job_id=str(job.id),
        status="started",
        message=f"Scrape job created for query: {request.query}",
    )


@app.get("/api/jobs/{job_id}", response_model=JobProgressResponse)
async def get_job_status(job_id: str):
    """Get the status and progress of a scrape job."""
    progress = get_scrape_job_progress(job_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Job not found")
    return progress


@app.get("/api/jobs")
async def list_jobs(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """List scrape jobs for the authenticated user."""
    session = get_session()
    try:
        query = session.query(ScrapeJob).filter(ScrapeJob.user_id == current_user.id)
        jobs = (
            query
            .order_by(ScrapeJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = query.count()

        return {
            "jobs": [
                {
                    "id": str(job.id),
                    "query": job.query,
                    "status": job.status,
                    "places_found": job.places_found or 0,
                    "reviews_total": job.reviews_total or 0,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                }
                for job in jobs
            ],
            "total": total,
        }
    finally:
        session.close()


# Places endpoints
@app.get("/api/places", response_model=PlacesListResponse)
async def list_places(limit: int = 20, offset: int = 0):
    """List all scraped places with review counts."""
    session = get_session()
    try:
        places = (
            session.query(Place)
            .order_by(Place.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = session.query(Place).count()

        result = []
        for place in places:
            # Count analyzed reviews
            analyzed = (
                session.query(ReviewAnalysis)
                .join(Review)
                .filter(Review.place_id == place.id)
                .count()
            )
            result.append(
                PlaceSummary(
                    id=str(place.id),
                    name=place.name,
                    category=place.category,
                    address=place.address,
                    rating=float(place.rating) if place.rating else None,
                    review_count=place.review_count or 0,
                    analyzed_count=analyzed,
                )
            )

        return PlacesListResponse(places=result, total=total)
    finally:
        session.close()


@app.get("/api/places/{place_id}", response_model=PlaceDetailResponse)
async def get_place(place_id: str):
    """Get details for a specific place."""
    session = get_session()
    try:
        place = session.query(Place).filter_by(id=place_id).first()
        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        return PlaceDetailResponse(
            id=str(place.id),
            name=place.name,
            category=place.category,
            address=place.address,
            rating=float(place.rating) if place.rating else None,
            review_count=place.review_count or 0,
            metadata=place.metadata_,
        )
    finally:
        session.close()


@app.get("/api/places/{place_id}/reviews", response_model=PlaceReviewsResponse)
async def get_place_reviews(place_id: str, limit: int = 50, offset: int = 0):
    """Get reviews with analysis for a specific place."""
    session = get_session()
    try:
        place = session.query(Place).filter_by(id=place_id).first()
        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        reviews = (
            session.query(Review)
            .filter_by(place_id=place_id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = session.query(Review).filter_by(place_id=place_id).count()

        review_list = []
        for review in reviews:
            analysis_data = None
            if review.analysis:
                analysis_data = ReviewAnalysisData(
                    sentiment=review.analysis.sentiment,
                    score=float(review.analysis.score) if review.analysis.score else None,
                    topics_positive=review.analysis.topics_positive or [],
                    topics_negative=review.analysis.topics_negative or [],
                    language=review.analysis.language,
                    urgent=review.analysis.urgent or False,
                    summary_ar=review.analysis.summary_ar,
                    summary_en=review.analysis.summary_en,
                    suggested_reply_ar=review.analysis.suggested_reply_ar,
                )

            review_list.append(
                ReviewWithAnalysis(
                    id=str(review.id),
                    author=review.author,
                    rating=review.rating,
                    text=review.text,
                    review_date=review.review_date,
                    analysis=analysis_data,
                )
            )

        return PlaceReviewsResponse(
            place=PlaceDetailResponse(
                id=str(place.id),
                name=place.name,
                category=place.category,
                address=place.address,
                rating=float(place.rating) if place.rating else None,
                review_count=place.review_count or 0,
                metadata=place.metadata_,
            ),
            reviews=review_list,
            total=total,
        )
    finally:
        session.close()


@app.get("/api/places/{place_id}/stats")
async def get_place_stats(place_id: str):
    """Get sentiment statistics for a place."""
    session = get_session()
    try:
        place = session.query(Place).filter_by(id=place_id).first()
        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        # Get all analyses for this place
        analyses = (
            session.query(ReviewAnalysis)
            .join(Review)
            .filter(Review.place_id == place_id)
            .all()
        )

        # Calculate stats
        total = len(analyses)
        if total == 0:
            return {
                "place_id": place_id,
                "total_analyzed": 0,
                "sentiment": {"positive": 0, "neutral": 0, "negative": 0},
                "urgent_count": 0,
                "top_positive_topics": [],
                "top_negative_topics": [],
            }

        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        urgent_count = 0
        positive_topics = {}
        negative_topics = {}

        for analysis in analyses:
            # Count sentiments
            if analysis.sentiment in sentiment_counts:
                sentiment_counts[analysis.sentiment] += 1

            # Count urgent
            if analysis.urgent:
                urgent_count += 1

            # Count topics
            for topic in analysis.topics_positive or []:
                positive_topics[topic] = positive_topics.get(topic, 0) + 1
            for topic in analysis.topics_negative or []:
                negative_topics[topic] = negative_topics.get(topic, 0) + 1

        # Sort topics by frequency
        top_positive = sorted(positive_topics.items(), key=lambda x: -x[1])[:5]
        top_negative = sorted(negative_topics.items(), key=lambda x: -x[1])[:5]

        return {
            "place_id": place_id,
            "place_name": place.name,
            "total_analyzed": total,
            "sentiment": sentiment_counts,
            "sentiment_percentages": {
                k: round(v / total * 100, 1) for k, v in sentiment_counts.items()
            },
            "urgent_count": urgent_count,
            "top_positive_topics": [{"topic": t, "count": c} for t, c in top_positive],
            "top_negative_topics": [{"topic": t, "count": c} for t, c in top_negative],
        }
    finally:
        session.close()


# Dashboard API endpoints
@app.get("/api/stats")
async def get_stats():
    """Get system-wide statistics for the dashboard."""
    session = get_session()
    try:
        places_count = session.query(Place).count()
        reviews_count = session.query(Review).count()
        analyses_count = session.query(ReviewAnalysis).count()

        # Job status counts
        job_statuses = (
            session.query(ScrapeJob.status, func.count(ScrapeJob.id))
            .group_by(ScrapeJob.status)
            .all()
        )
        scrape_jobs = {status: count for status, count in job_statuses}

        return {
            "places_count": places_count,
            "reviews_count": reviews_count,
            "analyses_count": analyses_count,
            "pending_analyses": reviews_count - analyses_count,
            "scrape_jobs": {
                "pending": scrape_jobs.get("pending", 0),
                "scraping": scrape_jobs.get("scraping", 0),
                "processing": scrape_jobs.get("processing", 0),
                "completed": scrape_jobs.get("completed", 0),
                "failed": scrape_jobs.get("failed", 0),
            }
        }
    finally:
        session.close()


@app.get("/api/overview")
async def get_overview(current_user: User = Depends(get_current_user)):
    """
    Get comprehensive overview data for the client portal.
    Returns all metrics, charts, and insights for the authenticated user.
    """
    from datetime import datetime, timedelta
    from collections import defaultdict

    session = get_session()
    try:
        # Get user's scrape jobs
        user_jobs = session.query(ScrapeJob).filter(ScrapeJob.user_id == current_user.id).all()
        user_job_ids = [job.id for job in user_jobs]

        # Get places from user's jobs (through pipeline_job_ids)
        user_place_ids = []
        for job in user_jobs:
            if job.pipeline_job_ids:
                # Get places from pipeline jobs
                pipeline_jobs = session.query(Job).filter(Job.id.in_(job.pipeline_job_ids)).all()
                user_place_ids.extend([pj.place_id for pj in pipeline_jobs if pj.place_id])

        user_place_ids = list(set(user_place_ids))  # Remove duplicates

        # If user has no places yet, return empty data
        if not user_place_ids:
            return {
                "metrics": {
                    "average_rating": None,
                    "positive_percentage": 0,
                    "reviews_count": 0,
                    "urgent_count": 0,
                    "pending_analyses": 0,
                },
                "sentiment_trend": [],
                "rating_distribution": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0},
                "top_positive_topics": [],
                "top_negative_topics": [],
                "whats_hot": [],
                "whats_not": [],
                "alerts": [],
                "places_count": 0,
            }

        # Get all reviews for user's places
        reviews = session.query(Review).filter(Review.place_id.in_(user_place_ids)).all()
        review_ids = [r.id for r in reviews]
        reviews_count = len(reviews)

        # Get all analyses for user's reviews
        analyses = []
        if review_ids:
            analyses = session.query(ReviewAnalysis).filter(ReviewAnalysis.review_id.in_(review_ids)).all()
        analyses_count = len(analyses)

        # Calculate metrics
        # 1. Average rating
        ratings = [r.rating for r in reviews if r.rating is not None]
        average_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

        # 2. Positive percentage
        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        urgent_count = 0
        positive_topics = defaultdict(int)
        negative_topics = defaultdict(int)

        for analysis in analyses:
            if analysis.sentiment in sentiment_counts:
                sentiment_counts[analysis.sentiment] += 1
            if analysis.urgent:
                urgent_count += 1
            for topic in (analysis.topics_positive or []):
                positive_topics[topic] += 1
            for topic in (analysis.topics_negative or []):
                negative_topics[topic] += 1

        total_sentiment = sum(sentiment_counts.values())
        positive_percentage = round(sentiment_counts["positive"] / total_sentiment * 100) if total_sentiment > 0 else 0

        # 3. Rating distribution
        rating_dist = {str(i): 0 for i in range(1, 6)}
        for r in reviews:
            if r.rating and 1 <= r.rating <= 5:
                rating_dist[str(r.rating)] += 1

        # Convert to percentages
        rating_distribution = {}
        total_ratings = sum(rating_dist.values())
        for star, count in rating_dist.items():
            rating_distribution[star] = round(count / total_ratings * 100) if total_ratings > 0 else 0

        # 4. Sentiment trend (last 7 days)
        today = datetime.utcnow().date()
        sentiment_trend = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_start = datetime.combine(day, datetime.min.time())
            day_end = datetime.combine(day, datetime.max.time())

            day_analyses = [
                a for a in analyses
                if a.analyzed_at and day_start <= a.analyzed_at <= day_end
            ]

            day_positive = sum(1 for a in day_analyses if a.sentiment == "positive")
            day_total = len(day_analyses)

            sentiment_trend.append({
                "date": day.isoformat(),
                "day": day.strftime("%a"),
                "positive": round(day_positive / day_total * 100) if day_total > 0 else 0,
                "count": day_total,
            })

        # 5. Top topics
        top_positive = sorted(positive_topics.items(), key=lambda x: -x[1])[:5]
        top_negative = sorted(negative_topics.items(), key=lambda x: -x[1])[:5]

        # Calculate percentages for topics
        whats_hot = []
        for topic, count in top_positive:
            pct = round(count / total_sentiment * 100) if total_sentiment > 0 else 0
            whats_hot.append({"item": topic, "score": f"{pct}%", "mentions": count})

        whats_not = []
        for topic, count in top_negative:
            pct = round(count / total_sentiment * 100) if total_sentiment > 0 else 0
            whats_not.append({"item": topic, "score": f"{pct}%", "mentions": count})

        # 6. Alerts
        alerts = []
        if urgent_count > 0:
            alerts.append({
                "type": "urgent",
                "icon": "⚠️",
                "message": f"{urgent_count} urgent reviews need immediate attention",
                "count": urgent_count,
            })

        pending_analyses = reviews_count - analyses_count
        if pending_analyses > 0:
            alerts.append({
                "type": "pending",
                "icon": "💬",
                "message": f"{pending_analyses} reviews awaiting analysis",
                "count": pending_analyses,
            })

        active_jobs = [j for j in user_jobs if j.status in ("scraping", "processing")]
        if active_jobs:
            alerts.append({
                "type": "processing",
                "icon": "⏳",
                "message": f"{len(active_jobs)} jobs currently processing",
                "count": len(active_jobs),
            })

        # Negative sentiment trend alert
        if sentiment_counts["negative"] > sentiment_counts["positive"] * 0.5:
            alerts.append({
                "type": "warning",
                "icon": "📉",
                "message": f"High negative sentiment: {sentiment_counts['negative']} negative reviews",
                "count": sentiment_counts["negative"],
            })

        return {
            "metrics": {
                "average_rating": average_rating,
                "positive_percentage": positive_percentage,
                "reviews_count": reviews_count,
                "urgent_count": urgent_count,
                "pending_analyses": pending_analyses,
            },
            "sentiment_trend": sentiment_trend,
            "rating_distribution": rating_distribution,
            "top_positive_topics": [{"topic": t, "count": c} for t, c in top_positive],
            "top_negative_topics": [{"topic": t, "count": c} for t, c in top_negative],
            "whats_hot": whats_hot,
            "whats_not": whats_not,
            "alerts": alerts,
            "places_count": len(user_place_ids),
            "sentiment_counts": sentiment_counts,
            "scrape_jobs": {
                "pending": len([j for j in user_jobs if j.status == "pending"]),
                "scraping": len([j for j in user_jobs if j.status == "scraping"]),
                "processing": len([j for j in user_jobs if j.status == "processing"]),
                "completed": len([j for j in user_jobs if j.status == "completed"]),
                "failed": len([j for j in user_jobs if j.status == "failed"]),
            }
        }
    finally:
        session.close()


@app.get("/api/queue-status")
async def get_queue_status():
    """Get RabbitMQ queue status."""
    try:
        import pika
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()

        # Declare queue to get its status (won't create if exists)
        queue = channel.queue_declare(queue=QUEUE_NAME, passive=True)
        message_count = queue.method.message_count
        consumer_count = queue.method.consumer_count

        connection.close()

        return {
            "queue_name": QUEUE_NAME,
            "messages_ready": message_count,
            "consumers": consumer_count,
            "status": "connected"
        }
    except Exception as e:
        return {
            "queue_name": QUEUE_NAME,
            "messages_ready": 0,
            "consumers": 0,
            "status": "disconnected",
            "error": str(e)
        }


@app.get("/api/recent-analyses")
async def get_recent_analyses(limit: int = 10):
    """Get the most recent review analyses."""
    session = get_session()
    try:
        analyses = (
            session.query(ReviewAnalysis)
            .order_by(ReviewAnalysis.analyzed_at.desc())
            .limit(limit)
            .all()
        )

        result = []
        for analysis in analyses:
            place_name = None
            review_text = None
            if analysis.review:
                review_text = analysis.review.text
                if analysis.review.place:
                    place_name = analysis.review.place.name

            result.append({
                "review_id": str(analysis.review_id),
                "place_name": place_name,
                "sentiment": analysis.sentiment,
                "score": float(analysis.score) if analysis.score else None,
                "summary_en": analysis.summary_en,
                "review_text": review_text[:100] if review_text else None,
                "analyzed_at": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
            })

        return {"analyses": result}
    finally:
        session.close()


@app.get("/api/system-health")
async def get_system_health():
    """Get health status of all system components."""
    # Check scraper
    client = ScraperClient()
    scraper_ok = await client.health_check()

    # Check database
    db_ok = False
    try:
        session = get_session()
        session.execute(text("SELECT 1"))
        session.close()
        db_ok = True
    except Exception:
        pass

    # Check RabbitMQ
    rabbit_ok = False
    try:
        import pika
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        connection.close()
        rabbit_ok = True
    except Exception:
        pass

    # Check vLLM (via config)
    vllm_ok = False
    try:
        import httpx
        from config import VLLM_BASE_URL, VLLM_API_KEY
        headers = {"Authorization": f"Bearer {VLLM_API_KEY}"}
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.get(f"{VLLM_BASE_URL}/models", headers=headers)
            vllm_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "api": True,
        "scraper": scraper_ok,
        "database": db_ok,
        "rabbitmq": rabbit_ok,
        "vllm": vllm_ok,
    }


@app.get("/api/logs")
async def get_logs(
    page: int = 1,
    limit: int = 10,
    category: Optional[str] = None,
    level: Optional[str] = None,
):
    """
    Get paginated activity logs.

    Args:
        page: Page number (1-indexed)
        limit: Items per page (default 10, max 100)
        category: Filter by category (job, analysis, email, scraper, worker, system)
        level: Filter by level (info, warning, error, success)

    Returns:
        Paginated logs with metadata
    """
    # Validate pagination
    page = max(1, page)
    limit = min(max(1, limit), 100)
    offset = (page - 1) * limit

    session = get_session()
    try:
        # Build query
        query = session.query(ActivityLog)

        # Apply filters
        if category:
            query = query.filter(ActivityLog.category == category)
        if level:
            query = query.filter(ActivityLog.level == level)

        # Get total count
        total = query.count()

        # Get paginated results
        logs = (
            query
            .order_by(ActivityLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Calculate pagination metadata
        total_pages = (total + limit - 1) // limit
        has_next = page < total_pages
        has_prev = page > 1

        return {
            "logs": [
                {
                    "id": str(log.id),
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "level": log.level,
                    "category": log.category,
                    "action": log.action,
                    "message": log.message,
                    "details": log.details,
                    "job_id": str(log.job_id) if log.job_id else None,
                    "scrape_job_id": str(log.scrape_job_id) if log.scrape_job_id else None,
                    "place_id": str(log.place_id) if log.place_id else None,
                }
                for log in logs
            ],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
            }
        }
    finally:
        session.close()


# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    logger.info("WebSocket client connected", extra={"extra_data": {"total_connections": len(manager.active_connections)}})
    try:
        while True:
            # Keep connection alive, receive any client messages
            data = await websocket.receive_text()
            # Could handle client commands here if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected", extra={"extra_data": {"total_connections": len(manager.active_connections)}})


if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT

    uvicorn.run(app, host=API_HOST, port=API_PORT)
