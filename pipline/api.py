"""
FastAPI application for Nurliya Pipeline.
Provides REST API for scraping, job tracking, and review analysis.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from uuid import UUID

from database import Place, Review, ReviewAnalysis, Job, ScrapeJob, get_session, create_tables
from orchestrator import (
    create_scrape_job,
    get_scrape_job_progress,
    run_scrape_pipeline,
)
from scraper_client import ScraperClient

app = FastAPI(
    title="Nurliya API",
    description="AI-powered sentiment analysis for Saudi business reviews",
    version="1.0.0",
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


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup."""
    create_tables()


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


# Scrape endpoints
@app.post("/api/scrape", response_model=ScrapeResponse)
async def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Start a new scrape job.

    This will:
    1. Create a scrape job record
    2. Start the Google Maps scraper in the background
    3. Automatically process results when scraping completes
    """
    # Create job record
    job = create_scrape_job(request.query, notification_email=request.notification_email)

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
async def list_jobs(limit: int = 20, offset: int = 0):
    """List recent scrape jobs."""
    session = get_session()
    try:
        jobs = (
            session.query(ScrapeJob)
            .order_by(ScrapeJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = session.query(ScrapeJob).count()

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


if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT

    uvicorn.run(app, host=API_HOST, port=API_PORT)
