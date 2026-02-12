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
from typing import Optional, List, Set, Dict
import uuid
from uuid import UUID
from sqlalchemy import func, text, case, or_

from logging_config import get_logger
import embedding_client
import vector_store
from database import (
    Place, Review, ReviewAnalysis, Job, ScrapeJob, ActivityLog, User, AnomalyInsight,
    PlaceTaxonomy, TaxonomyCategory, TaxonomyProduct, RawMention, TaxonomyAuditLog,
    PlaceMenuImage, TaxonomyArchive,
    get_session, create_tables
)
from datetime import datetime
from config import RABBITMQ_URL, QUEUE_NAME
from rabbitmq import get_channel, publish_message
from scraper_client import ScraperClient
from auth import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    register_user, authenticate_user, create_access_token,
    get_current_user, get_optional_user
)
from mention_grouping import MentionData, group_mentions

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
                    analyzable_count = session.query(Review).filter(
                        Review.text.isnot(None), Review.text != ''
                    ).count()
                    analyses_count = session.query(ReviewAnalysis).count()
                    mentions_count = session.query(RawMention).count()

                    # Get RabbitMQ queue status
                    queue_messages = 0
                    queue_consumers = 0
                    try:
                        import pika
                        params = pika.URLParameters(RABBITMQ_URL)
                        connection = pika.BlockingConnection(params)
                        channel = connection.channel()
                        queue = channel.queue_declare(queue=QUEUE_NAME, passive=True)
                        queue_messages = queue.method.message_count
                        queue_consumers = queue.method.consumer_count
                        connection.close()
                    except Exception:
                        pass  # Queue stats unavailable

                    # Get job status counts
                    job_statuses = (
                        session.query(ScrapeJob.status, func.count(ScrapeJob.id))
                        .group_by(ScrapeJob.status)
                        .all()
                    )
                    scrape_jobs = {status: count for status, count in job_statuses}

                    # Get active jobs with extraction stats
                    active_jobs = (
                        session.query(ScrapeJob)
                        .filter(ScrapeJob.status.in_(["pending", "scraping", "processing"]))
                        .all()
                    )

                    # Build active jobs with extraction progress
                    active_jobs_data = []
                    for job in active_jobs:
                        # Get places for this job
                        job_places = session.query(Place.id).join(Job).filter(
                            Job.id.in_(job.pipeline_job_ids or [])
                        ).all() if job.pipeline_job_ids else []
                        place_ids = [p[0] for p in job_places]

                        # Count mentions extracted for these places
                        mentions_extracted = 0
                        if place_ids:
                            mentions_extracted = session.query(RawMention).filter(
                                RawMention.place_id.in_(place_ids)
                            ).count()

                        active_jobs_data.append({
                            "id": str(job.id),
                            "query": job.query,
                            "status": job.status,
                            "places_found": job.places_found or 0,
                            "reviews_total": job.reviews_total or 0,
                            "reviews_processed": job.reviews_processed or 0,
                            "mentions_extracted": mentions_extracted,
                        })

                    await manager.broadcast({
                        "type": "stats",
                        "data": {
                            "places_count": places_count,
                            "reviews_count": reviews_count,
                            "analyses_count": analyses_count,
                            "mentions_count": mentions_count,
                            "pending_analyses": max(0, analyzable_count - analyses_count),
                            "queue_messages": queue_messages,
                            "queue_consumers": queue_consumers,
                            "scrape_jobs": {
                                "pending": scrape_jobs.get("pending", 0),
                                "scraping": scrape_jobs.get("scraping", 0),
                                "processing": scrape_jobs.get("processing", 0),
                                "completed": scrape_jobs.get("completed", 0),
                                "failed": scrape_jobs.get("failed", 0),
                            },
                            "active_jobs": active_jobs_data
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
    # Pre-load embedding model to avoid cold start on first request
    try:
        from embedding_client import _get_model
        _get_model()
        logger.info("Embedding model pre-loaded")
    except Exception as e:
        logger.warning(f"Failed to pre-load embedding model: {e}")
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


# Helper to resolve short URLs
async def resolve_short_url(url: str) -> str:
    """Resolve a short URL to its final destination."""
    import httpx
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.head(url)
            return str(resp.url)
    except Exception as e:
        logger.warning("Failed to resolve short URL", extra={"extra_data": {"url": url, "error": str(e)}})
        return url


# Helper to extract place name from Google Maps URL
def extract_place_from_url(url: str) -> Optional[str]:
    """Extract place name from Google Maps URL."""
    import re
    from urllib.parse import unquote

    # Pattern: google.com/maps/place/PLACE_NAME/...
    place_match = re.search(r'google\.com/maps/place/([^/@]+)', url)
    if place_match:
        place_name = unquote(place_match.group(1).replace('+', ' '))
        return place_name

    return None


def is_google_maps_url(text: str) -> bool:
    """Check if text is a Google Maps URL."""
    patterns = [
        r'google\.com/maps',
        r'maps\.google\.com',
        r'goo\.gl/maps',
        r'maps\.app\.goo\.gl',
    ]
    import re
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def is_short_url(url: str) -> bool:
    """Check if URL is a short URL that needs resolving."""
    return 'goo.gl' in url.lower()


# Request/Response Models
class ScrapeRequest(BaseModel):
    query: str = Field(..., description="Search query or Google Maps URL")
    depth: int = Field(10, ge=1, le=50, description="Scroll depth for results (1 for single place URL)")
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
    needs_action: bool = False
    action_ar: Optional[str]
    action_en: Optional[str]


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


# =============================================================================
# ONBOARDING API MODELS
# =============================================================================

# --- Request Models ---

class CategoryUpdateRequest(BaseModel):
    """Request to update a taxonomy category."""
    action: str = Field(..., description="Action: approve, reject, move, rename")
    rejection_reason: Optional[str] = Field(None, description="Required if action=reject")
    parent_id: Optional[UUID] = Field(None, description="New parent ID if action=move")
    display_name_en: Optional[str] = Field(None, description="New English name if action=rename")
    display_name_ar: Optional[str] = Field(None, description="New Arabic name if action=rename")


class ProductUpdateRequest(BaseModel):
    """Request to update a taxonomy product."""
    action: str = Field(..., description="Action: approve, reject, move, add_variant, remove_variant, set_variants")
    rejection_reason: Optional[str] = Field(None, description="Required if action=reject")
    assigned_category_id: Optional[UUID] = Field(None, description="Category ID if action=move (None=standalone)")
    variant: Optional[str] = Field(None, description="Variant text if action=add_variant or remove_variant")
    variants: Optional[List[str]] = Field(None, description="Full variant list if action=set_variants")


class CategoryCreateRequest(BaseModel):
    """Request to create a new category manually."""
    taxonomy_id: UUID
    parent_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=100)
    display_name_en: str = Field(..., min_length=1, max_length=100)
    display_name_ar: Optional[str] = Field(None, max_length=100)
    has_products: bool = True


class ProductCreateRequest(BaseModel):
    """Request to create a new product manually."""
    taxonomy_id: UUID
    assigned_category_id: Optional[UUID] = None
    display_name: str = Field(..., min_length=1, max_length=200)
    variants: List[str] = []


# --- Response Models ---

class PendingTaxonomyResponse(BaseModel):
    """Summary of a taxonomy pending review."""
    id: str
    place_id: str
    place_name: str
    place_category: Optional[str]
    status: str
    reviews_sampled: int
    categories_count: int
    products_count: int
    approved_categories: int
    approved_products: int
    discovered_at: Optional[str]


class PendingListResponse(BaseModel):
    """List of pending taxonomies."""
    taxonomies: List[PendingTaxonomyResponse]
    total: int


class TaxonomyCategoryResponse(BaseModel):
    """Category in taxonomy detail response."""
    id: str
    parent_id: Optional[str]
    name: str
    display_name_en: Optional[str]
    display_name_ar: Optional[str]
    has_products: bool
    is_approved: bool
    approved_by: Optional[str]
    approved_at: Optional[str]
    rejection_reason: Optional[str]
    discovered_mention_count: int
    mention_count: int
    avg_sentiment: Optional[float]


class TaxonomyProductResponse(BaseModel):
    """Product in taxonomy detail response."""
    id: str
    discovered_category_id: Optional[str]
    assigned_category_id: Optional[str]
    canonical_text: str
    display_name: Optional[str]
    variants: List[str]
    is_approved: bool
    approved_by: Optional[str]
    approved_at: Optional[str]
    rejection_reason: Optional[str]
    discovered_mention_count: int
    mention_count: int
    avg_sentiment: Optional[float]


class TaxonomyDetailResponse(BaseModel):
    """Full taxonomy detail for editor."""
    id: str
    place_id: str
    place_name: str
    place_category: Optional[str]
    status: str
    reviews_sampled: int
    entities_discovered: int
    discovered_at: Optional[str]
    published_at: Optional[str]
    published_by: Optional[str]
    categories: List[TaxonomyCategoryResponse]
    products: List[TaxonomyProductResponse]


class ActionResponse(BaseModel):
    """Generic success response."""
    success: bool
    message: str


class MergeRequest(BaseModel):
    """Request to merge one item into another (source absorbed into target)."""
    source_id: UUID = Field(..., description="ID of item to be absorbed and deleted")
    target_id: UUID = Field(..., description="ID of item that survives and absorbs source")


class MergeResponse(BaseModel):
    """Response for merge operations."""
    success: bool
    message: str
    target_id: str  # ID of the surviving item
    merged_mention_count: int = 0
    merged_variant_count: int = 0


class ImportProductItem(BaseModel):
    """A product within an imported category."""
    name: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=200)
    variants: List[str] = Field(default_factory=list)


class ImportCategoryItem(BaseModel):
    """A category in a taxonomy import."""
    name: str = Field(..., min_length=1, max_length=100)
    display_name_en: str = Field(..., min_length=1, max_length=100)
    display_name_ar: Optional[str] = Field(None, max_length=100)
    is_aspect: bool = True
    is_parent: Optional[bool] = Field(None, description="True for parent/container categories")
    parent: Optional[str] = Field(None, description="Parent category name for hierarchy")
    examples: List[str] = Field(default_factory=list)
    products: List[ImportProductItem] = Field(default_factory=list)


class TaxonomyImportRequest(BaseModel):
    """Request body for importing a taxonomy."""
    categories: List[ImportCategoryItem] = Field(..., min_length=1)


class TaxonomyImportResponse(BaseModel):
    """Response for taxonomy import with new taxonomy ID."""
    success: bool
    message: str
    new_taxonomy_id: Optional[str] = None  # New taxonomy ID after re-clustering
    archived_taxonomy_id: Optional[str] = None  # ID of archived old taxonomy


# --- Audit Logging Helper ---

def log_taxonomy_action(
    session,
    taxonomy_id,
    user_id,
    action: str,
    entity_type: str,
    entity_id,
    old_value: dict = None,
    new_value: dict = None
):
    """Log an action to TaxonomyAuditLog."""
    log = TaxonomyAuditLog(
        taxonomy_id=taxonomy_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(log)


# =============================================================================
# ONBOARDING API ENDPOINTS
# =============================================================================

@app.get("/api/onboarding/pending", response_model=PendingListResponse)
async def get_pending_taxonomies(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get list of taxonomies pending review.
    Default: returns draft and review status taxonomies.
    """
    session = get_session()
    try:
        query = session.query(PlaceTaxonomy).join(Place)

        if status:
            query = query.filter(PlaceTaxonomy.status == status)
        else:
            query = query.filter(PlaceTaxonomy.status.in_(["draft", "review"]))

        taxonomies = query.order_by(PlaceTaxonomy.discovered_at.desc()).all()

        result = []
        for tax in taxonomies:
            categories = session.query(TaxonomyCategory).filter_by(taxonomy_id=tax.id).all()
            products = session.query(TaxonomyProduct).filter_by(taxonomy_id=tax.id).all()

            result.append(PendingTaxonomyResponse(
                id=str(tax.id),
                place_id=str(tax.place_id),
                place_name=tax.place.name if tax.place else "Unknown",
                place_category=tax.place.category if tax.place else None,
                status=tax.status,
                reviews_sampled=tax.reviews_sampled or 0,
                categories_count=len(categories),
                products_count=len(products),
                approved_categories=len([c for c in categories if c.is_approved]),
                approved_products=len([p for p in products if p.is_approved]),
                discovered_at=tax.discovered_at.isoformat() if tax.discovered_at else None,
            ))

        return PendingListResponse(taxonomies=result, total=len(result))
    finally:
        session.close()


@app.get("/api/onboarding/taxonomies/{taxonomy_id}", response_model=TaxonomyDetailResponse)
async def get_taxonomy_detail(
    taxonomy_id: UUID,
    current_user: User = Depends(get_current_user)
):
    """Get full taxonomy detail for editor."""
    session = get_session()
    try:
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        categories = session.query(TaxonomyCategory).filter_by(taxonomy_id=taxonomy_id).all()
        products = session.query(TaxonomyProduct).filter_by(taxonomy_id=taxonomy_id).all()

        return TaxonomyDetailResponse(
            id=str(taxonomy.id),
            place_id=str(taxonomy.place_id),
            place_name=taxonomy.place.name if taxonomy.place else "Unknown",
            place_category=taxonomy.place.category if taxonomy.place else None,
            status=taxonomy.status,
            reviews_sampled=taxonomy.reviews_sampled or 0,
            entities_discovered=taxonomy.entities_discovered or 0,
            discovered_at=taxonomy.discovered_at.isoformat() if taxonomy.discovered_at else None,
            published_at=taxonomy.published_at.isoformat() if taxonomy.published_at else None,
            published_by=str(taxonomy.published_by) if taxonomy.published_by else None,
            categories=[
                TaxonomyCategoryResponse(
                    id=str(c.id),
                    parent_id=str(c.parent_id) if c.parent_id else None,
                    name=c.name,
                    display_name_en=c.display_name_en,
                    display_name_ar=c.display_name_ar,
                    has_products=c.has_products,
                    is_approved=c.is_approved,
                    approved_by=str(c.approved_by) if c.approved_by else None,
                    approved_at=c.approved_at.isoformat() if c.approved_at else None,
                    rejection_reason=c.rejection_reason,
                    discovered_mention_count=c.discovered_mention_count or 0,
                    mention_count=c.mention_count or 0,
                    avg_sentiment=float(c.avg_sentiment) if c.avg_sentiment else None,
                ) for c in categories
            ],
            products=[
                TaxonomyProductResponse(
                    id=str(p.id),
                    discovered_category_id=str(p.discovered_category_id) if p.discovered_category_id else None,
                    assigned_category_id=str(p.assigned_category_id) if p.assigned_category_id else None,
                    canonical_text=p.canonical_text,
                    display_name=p.display_name,
                    variants=p.variants or [],
                    is_approved=p.is_approved,
                    approved_by=str(p.approved_by) if p.approved_by else None,
                    approved_at=p.approved_at.isoformat() if p.approved_at else None,
                    rejection_reason=p.rejection_reason,
                    discovered_mention_count=p.discovered_mention_count or 0,
                    mention_count=p.mention_count or 0,
                    avg_sentiment=float(p.avg_sentiment) if p.avg_sentiment else None,
                ) for p in products
            ],
        )
    finally:
        session.close()


@app.patch("/api/onboarding/categories/{category_id}", response_model=ActionResponse)
async def update_category(
    category_id: UUID,
    request: CategoryUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update a taxonomy category (approve, reject, move, rename)."""
    session = get_session()
    try:
        category = session.query(TaxonomyCategory).filter_by(id=category_id).first()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        old_value = {
            "is_approved": category.is_approved,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "display_name_en": category.display_name_en,
            "display_name_ar": category.display_name_ar,
            "rejection_reason": category.rejection_reason,
        }

        if request.action == "approve":
            category.is_approved = True
            category.approved_by = current_user.id
            category.approved_at = datetime.utcnow()
            category.rejection_reason = None
            message = f"Category '{category.name}' approved"

        elif request.action == "reject":
            if not request.rejection_reason:
                raise HTTPException(status_code=400, detail="Rejection reason required")
            category.is_approved = False
            category.rejection_reason = request.rejection_reason
            message = f"Category '{category.name}' rejected"

            # Clean up anchor examples created from this taxonomy
            try:
                from anchor_manager import remove_anchor_examples_for_taxonomy, normalize_business_type
                taxonomy = category.taxonomy
                if taxonomy and taxonomy.place:
                    bt = normalize_business_type(taxonomy.place.category)
                    removed = remove_anchor_examples_for_taxonomy(
                        session, category.name, category.taxonomy_id, bt
                    )
                    if removed > 0:
                        message += f" ({removed} anchor examples cleaned)"
            except Exception as e:
                logger.warning(f"Failed to clean anchor on rejection: {e}")

        elif request.action == "move":
            category.parent_id = request.parent_id
            message = f"Category '{category.name}' moved"

        elif request.action == "rename":
            if request.display_name_en:
                category.display_name_en = request.display_name_en
            if request.display_name_ar:
                category.display_name_ar = request.display_name_ar
            message = f"Category '{category.name}' renamed"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        new_value = {
            "is_approved": category.is_approved,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "display_name_en": category.display_name_en,
            "display_name_ar": category.display_name_ar,
            "rejection_reason": category.rejection_reason,
        }

        log_taxonomy_action(
            session, category.taxonomy_id, current_user.id,
            request.action, "category", category_id, old_value, new_value
        )

        session.commit()
        return ActionResponse(success=True, message=message)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.patch("/api/onboarding/products/{product_id}", response_model=ActionResponse)
async def update_product(
    product_id: UUID,
    request: ProductUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update a taxonomy product (approve, reject, move, add_variant)."""
    session = get_session()
    try:
        product = session.query(TaxonomyProduct).filter_by(id=product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        old_value = {
            "is_approved": product.is_approved,
            "assigned_category_id": str(product.assigned_category_id) if product.assigned_category_id else None,
            "variants": product.variants or [],
            "rejection_reason": product.rejection_reason,
        }

        if request.action == "approve":
            product.is_approved = True
            product.approved_by = current_user.id
            product.approved_at = datetime.utcnow()
            product.rejection_reason = None
            # If no assigned category, use discovered category
            if not product.assigned_category_id and product.discovered_category_id:
                product.assigned_category_id = product.discovered_category_id
            message = f"Product '{product.display_name or product.canonical_text}' approved"

        elif request.action == "reject":
            if not request.rejection_reason:
                raise HTTPException(status_code=400, detail="Rejection reason required")
            product.is_approved = False
            product.rejection_reason = request.rejection_reason
            message = f"Product '{product.display_name or product.canonical_text}' rejected"

            # Clean up anchor examples for the product's category
            try:
                from anchor_manager import remove_anchor_examples_for_taxonomy, normalize_business_type
                if product.assigned_category_id:
                    cat = session.query(TaxonomyCategory).filter_by(id=product.assigned_category_id).first()
                    if cat:
                        taxonomy = session.query(PlaceTaxonomy).filter_by(id=product.taxonomy_id).first()
                        if taxonomy and taxonomy.place:
                            bt = normalize_business_type(taxonomy.place.category)
                            removed = remove_anchor_examples_for_taxonomy(
                                session, cat.name, product.taxonomy_id, bt
                            )
                            if removed > 0:
                                message += f" ({removed} anchor examples cleaned)"
            except Exception as e:
                logger.warning(f"Failed to clean anchor on product rejection: {e}")

        elif request.action == "move":
            old_category_id = product.assigned_category_id
            product.assigned_category_id = request.assigned_category_id

            # BUG-009 FIX: Cascade update to RawMentions that reference this product
            # Their resolved_category_id should follow the product to the new category
            updated_mentions = session.query(RawMention).filter(
                RawMention.resolved_product_id == product.id
            ).update(
                {RawMention.resolved_category_id: request.assigned_category_id},
                synchronize_session=False
            )
            if updated_mentions > 0:
                logger.info(f"Cascaded category update to {updated_mentions} mentions",
                           extra={"extra_data": {
                               "product_id": str(product.id),
                               "old_category": str(old_category_id) if old_category_id else None,
                               "new_category": str(request.assigned_category_id) if request.assigned_category_id else None
                           }})

            message = f"Product '{product.display_name or product.canonical_text}' moved"
            if updated_mentions > 0:
                message += f" ({updated_mentions} mentions updated)"

        elif request.action == "add_variant":
            if not request.variant:
                raise HTTPException(status_code=400, detail="Variant text required")
            variants = product.variants or []
            if request.variant not in variants:
                variants.append(request.variant)
                product.variants = variants
            message = f"Variant '{request.variant}' added"

        elif request.action == "remove_variant":
            if not request.variant:
                raise HTTPException(status_code=400, detail="Variant text required")
            variants = product.variants or []
            if request.variant in variants:
                variants.remove(request.variant)
                product.variants = variants
                message = f"Variant '{request.variant}' removed"
            else:
                raise HTTPException(status_code=400, detail=f"Variant '{request.variant}' not found in product variants")

        elif request.action == "set_variants":
            if request.variants is None:
                raise HTTPException(status_code=400, detail="Variants list required")
            product.variants = request.variants
            message = f"Variants updated ({len(request.variants)} variants)"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        new_value = {
            "is_approved": product.is_approved,
            "assigned_category_id": str(product.assigned_category_id) if product.assigned_category_id else None,
            "variants": product.variants or [],
            "rejection_reason": product.rejection_reason,
        }

        log_taxonomy_action(
            session, product.taxonomy_id, current_user.id,
            request.action, "product", product_id, old_value, new_value
        )

        session.commit()
        return ActionResponse(success=True, message=message)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/onboarding/categories", response_model=TaxonomyCategoryResponse)
async def create_category(
    request: CategoryCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new category manually."""
    session = get_session()
    try:
        # Verify taxonomy exists
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=request.taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        category = TaxonomyCategory(
            taxonomy_id=request.taxonomy_id,
            parent_id=request.parent_id,
            name=request.name.lower().replace(" ", "_"),
            display_name_en=request.display_name_en,
            display_name_ar=request.display_name_ar,
            has_products=request.has_products,
            is_approved=True,  # Manually created = auto-approved
            approved_by=current_user.id,
            approved_at=datetime.utcnow(),
        )
        session.add(category)
        session.flush()

        log_taxonomy_action(
            session, request.taxonomy_id, current_user.id,
            "create", "category", category.id,
            None, {"name": category.name, "display_name_en": category.display_name_en}
        )

        session.commit()

        return TaxonomyCategoryResponse(
            id=str(category.id),
            parent_id=str(category.parent_id) if category.parent_id else None,
            name=category.name,
            display_name_en=category.display_name_en,
            display_name_ar=category.display_name_ar,
            has_products=category.has_products,
            is_approved=category.is_approved,
            approved_by=str(category.approved_by) if category.approved_by else None,
            approved_at=category.approved_at.isoformat() if category.approved_at else None,
            rejection_reason=None,
            discovered_mention_count=0,
            mention_count=0,
            avg_sentiment=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/onboarding/products", response_model=TaxonomyProductResponse)
async def create_product(
    request: ProductCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new product manually."""
    session = get_session()
    try:
        # Verify taxonomy exists
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=request.taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        product = TaxonomyProduct(
            taxonomy_id=request.taxonomy_id,
            assigned_category_id=request.assigned_category_id,
            canonical_text=request.display_name.lower(),
            display_name=request.display_name,
            variants=request.variants,
            is_approved=True,  # Manually created = auto-approved
            approved_by=current_user.id,
            approved_at=datetime.utcnow(),
        )
        session.add(product)
        session.flush()

        log_taxonomy_action(
            session, request.taxonomy_id, current_user.id,
            "create", "product", product.id,
            None, {"display_name": product.display_name}
        )

        session.commit()

        return TaxonomyProductResponse(
            id=str(product.id),
            discovered_category_id=None,
            assigned_category_id=str(product.assigned_category_id) if product.assigned_category_id else None,
            canonical_text=product.canonical_text,
            display_name=product.display_name,
            variants=product.variants or [],
            is_approved=product.is_approved,
            approved_by=str(product.approved_by) if product.approved_by else None,
            approved_at=product.approved_at.isoformat() if product.approved_at else None,
            rejection_reason=None,
            discovered_mention_count=0,
            mention_count=0,
            avg_sentiment=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# --- Merge Endpoints ---

@app.post("/api/onboarding/products/merge", response_model=MergeResponse)
async def merge_products(
    request: MergeRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Merge one product into another (source -> target).

    - Target product survives (keeps its name, display_name)
    - Source product's variants are added to target
    - Source product's mentions are reassigned to target
    - Source product is deleted
    """
    session = get_session()
    try:
        source = session.query(TaxonomyProduct).filter_by(id=request.source_id).first()
        target = session.query(TaxonomyProduct).filter_by(id=request.target_id).first()

        if not source:
            raise HTTPException(status_code=404, detail="Source product not found")
        if not target:
            raise HTTPException(status_code=404, detail="Target product not found")
        if source.taxonomy_id != target.taxonomy_id:
            raise HTTPException(status_code=400, detail="Products must be in the same taxonomy")
        if source.id == target.id:
            raise HTTPException(status_code=400, detail="Cannot merge product into itself")

        # Merge variants (deduplicate)
        source_variants = source.variants or []
        target_variants = target.variants or []
        # Add source canonical_text as variant too
        merged_variants = list(set(target_variants + source_variants + [source.canonical_text]))
        # Remove target's canonical_text from variants if present
        merged_variants = [v for v in merged_variants if v != target.canonical_text]
        merged_variant_count = len(merged_variants) - len(target_variants)
        target.variants = merged_variants

        # Reassign mentions from source to target
        merged_mention_count = session.query(RawMention).filter(
            RawMention.resolved_product_id == source.id
        ).update(
            {RawMention.resolved_product_id: target.id},
            synchronize_session=False
        )

        # Also update discovered_product_id references
        session.query(RawMention).filter(
            RawMention.discovered_product_id == source.id
        ).update(
            {RawMention.discovered_product_id: target.id},
            synchronize_session=False
        )

        # Update mention counts
        target.discovered_mention_count = (target.discovered_mention_count or 0) + (source.discovered_mention_count or 0)
        target.mention_count = (target.mention_count or 0) + (source.mention_count or 0)

        # Log the merge
        log_taxonomy_action(
            session, target.taxonomy_id, current_user.id,
            "merge", "product", target.id,
            {"source_id": str(source.id), "source_name": source.display_name or source.canonical_text},
            {"merged_variants": merged_variant_count, "merged_mentions": merged_mention_count}
        )

        # Delete source product
        session.delete(source)
        session.commit()

        return MergeResponse(
            success=True,
            message=f"Merged '{source.display_name or source.canonical_text}' into '{target.display_name or target.canonical_text}'",
            target_id=str(target.id),
            merged_mention_count=merged_mention_count,
            merged_variant_count=merged_variant_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to merge products: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/onboarding/categories/merge", response_model=MergeResponse)
async def merge_categories(
    request: MergeRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Merge one category into another (source -> target).

    - Target category survives (keeps its name, display_names, parent)
    - Source category's products are moved to target
    - Source category's mentions are reassigned to target
    - Child categories of source are reparented to target
    - Source category is deleted
    """
    session = get_session()
    try:
        source = session.query(TaxonomyCategory).filter_by(id=request.source_id).first()
        target = session.query(TaxonomyCategory).filter_by(id=request.target_id).first()

        if not source:
            raise HTTPException(status_code=404, detail="Source category not found")
        if not target:
            raise HTTPException(status_code=404, detail="Target category not found")
        if source.taxonomy_id != target.taxonomy_id:
            raise HTTPException(status_code=400, detail="Categories must be in the same taxonomy")
        if source.id == target.id:
            raise HTTPException(status_code=400, detail="Cannot merge category into itself")

        # Check for circular reference (target is child of source)
        if target.parent_id == source.id:
            raise HTTPException(status_code=400, detail="Cannot merge parent into its child")

        merged_mention_count = 0
        merged_product_count = 0

        # Move products from source to target
        products_moved = session.query(TaxonomyProduct).filter(
            TaxonomyProduct.assigned_category_id == source.id
        ).update(
            {TaxonomyProduct.assigned_category_id: target.id},
            synchronize_session=False
        )
        merged_product_count += products_moved

        # Also update discovered_category_id references
        session.query(TaxonomyProduct).filter(
            TaxonomyProduct.discovered_category_id == source.id
        ).update(
            {TaxonomyProduct.discovered_category_id: target.id},
            synchronize_session=False
        )

        # Reassign mentions from source to target
        merged_mention_count += session.query(RawMention).filter(
            RawMention.resolved_category_id == source.id
        ).update(
            {RawMention.resolved_category_id: target.id},
            synchronize_session=False
        )

        # Also update discovered_category_id references in mentions
        session.query(RawMention).filter(
            RawMention.discovered_category_id == source.id
        ).update(
            {RawMention.discovered_category_id: target.id},
            synchronize_session=False
        )

        # Reparent child categories of source to target
        children_reparented = session.query(TaxonomyCategory).filter(
            TaxonomyCategory.parent_id == source.id
        ).update(
            {TaxonomyCategory.parent_id: target.id},
            synchronize_session=False
        )

        # Update mention counts
        target.discovered_mention_count = (target.discovered_mention_count or 0) + (source.discovered_mention_count or 0)
        target.mention_count = (target.mention_count or 0) + (source.mention_count or 0)

        # If target didn't have products but source did, update has_products
        if source.has_products and not target.has_products:
            target.has_products = True

        # Log the merge
        log_taxonomy_action(
            session, target.taxonomy_id, current_user.id,
            "merge", "category", target.id,
            {"source_id": str(source.id), "source_name": source.display_name_en or source.name},
            {"merged_products": merged_product_count, "merged_mentions": merged_mention_count, "children_reparented": children_reparented}
        )

        source_name = source.display_name_en or source.name
        target_name = target.display_name_en or target.name

        # Delete source category
        session.delete(source)
        session.commit()

        return MergeResponse(
            success=True,
            message=f"Merged '{source_name}' into '{target_name}' ({merged_product_count} products, {merged_mention_count} mentions)",
            target_id=str(target.id),
            merged_mention_count=merged_mention_count,
            merged_variant_count=merged_product_count,  # Using variant_count field for products
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to merge categories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# --- Mention Endpoints for Onboarding Audit ---

# BUG-014 FIX: Helper functions to get embeddings for vector similarity search

def _get_product_embedding(session, product: TaxonomyProduct) -> Optional[List[float]]:
    """
    Get embedding for a product from PRODUCTS_COLLECTION or generate from text.

    BUG-014 FIX: Used for finding similar mentions below threshold.

    Checks in order:
    1. PRODUCTS_COLLECTION (indexed during publish)
    2. Generate from canonical_text + variants
    """
    # Try to get from PRODUCTS_COLLECTION
    if product.vector_id:
        client = vector_store._get_client()
        if client:
            try:
                points = client.retrieve(
                    collection_name=vector_store.PRODUCTS_COLLECTION,
                    ids=[product.vector_id],
                    with_vectors=True
                )
                if points and points[0].vector:
                    return points[0].vector
            except Exception as e:
                logger.debug(f"Could not retrieve product embedding from Qdrant: {e}")

    # Fallback: Generate from canonical_text + variants
    texts = [product.canonical_text] + (product.variants or [])[:2]
    embeddings = embedding_client.generate_embeddings(texts, normalize=True)
    if embeddings:
        import numpy as np
        # Average the embeddings for canonical + variants
        avg_embedding = np.mean(embeddings, axis=0).tolist()
        return avg_embedding

    return None


def _get_category_embedding(session, category: TaxonomyCategory) -> Optional[List[float]]:
    """
    Get embedding for a category from centroid_embedding or generate from name.

    BUG-014 FIX: Used for finding similar mentions below threshold.
    """
    # Use stored centroid from clustering (BUG-006 fix)
    if category.centroid_embedding:
        return category.centroid_embedding

    # Fallback: Generate from category name
    embeddings = embedding_client.generate_embeddings([category.name], normalize=True)
    return embeddings[0] if embeddings else None


class MentionResponse(BaseModel):
    id: str
    mention_text: str
    mention_type: str
    sentiment: Optional[str]
    review_id: str
    review_text: str
    review_author: Optional[str]
    review_rating: Optional[float]
    review_date: Optional[str]
    similarity_score: Optional[float] = None


class MentionListResponse(BaseModel):
    mentions: List[MentionResponse]
    total: int
    matched_count: int
    below_threshold_count: int


@app.get("/api/onboarding/products/{product_id}/mentions", response_model=MentionListResponse)
async def get_product_mentions(
    product_id: str,
    include_below_threshold: bool = True,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get mentions linked to a specific product, including near-misses below threshold.

    BUG-014 FIX: Now uses vector similarity search to find mentions SIMILAR to this
    specific product, instead of returning all unresolved mentions.
    """
    session = get_session()
    try:
        product_uuid = UUID(product_id)
        product = session.query(TaxonomyProduct).filter_by(id=product_uuid).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Check if taxonomy is draft (not yet published)
        is_draft = product.taxonomy and product.taxonomy.status != 'active'

        # For draft: use discovered_product_id (set during clustering)
        # For published: use resolved_product_id (set during publish)
        if is_draft:
            matched_mentions = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.discovered_product_id == product_uuid
            ).all()
        else:
            matched_mentions = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.resolved_product_id == product_uuid
            ).all()

        # BUG-014 FIX: Get below-threshold mentions using vector similarity search
        # These are mentions SIMILAR to this product but didn't pass the 0.80 threshold
        below_threshold_mentions = []
        if include_below_threshold and product.taxonomy:
            # FEATURE-001: Use all_place_ids for multi-branch taxonomy support
            place_ids = [str(p) for p in product.taxonomy.all_place_ids]

            # Get product embedding for similarity search
            product_embedding = _get_product_embedding(session, product)

            if product_embedding:
                # Search MENTIONS_COLLECTION for similar unresolved mentions
                # FEATURE-001: Search across ALL places in shared taxonomy
                similar_results = vector_store.search_similar(
                    collection_name=vector_store.MENTIONS_COLLECTION,
                    query_vector=product_embedding,
                    place_ids=place_ids,  # Multi-place support
                    mention_type='product',
                    limit=30,
                    score_threshold=0.55,  # Lower bound for "near miss"
                )

                if similar_results:
                    # Get IDs of already-matched mentions to exclude
                    matched_ids = {str(rm.id) for rm, _ in matched_mentions}

                    for result in similar_results:
                        # Filter: below 0.80 threshold (these are "near misses")
                        if result.score < 0.80:
                            # Find mention by qdrant_point_id
                            mention = session.query(RawMention).filter_by(
                                qdrant_point_id=result.id
                            ).first()

                            if mention and str(mention.id) not in matched_ids:
                                # Only include unresolved mentions
                                if mention.resolved_product_id is None:
                                    review = session.query(Review).filter_by(
                                        id=mention.review_id
                                    ).first()
                                    if review:
                                        below_threshold_mentions.append(
                                            (mention, review, result.score)
                                        )

                logger.debug(
                    f"BUG-014: Product {product.canonical_text} - found {len(below_threshold_mentions)} similar below-threshold mentions",
                    extra={"extra_data": {"product_id": product_id}}
                )
            else:
                # Fallback if no embedding available (shouldn't happen normally)
                logger.warning(
                    f"BUG-014: No embedding for product {product_id}, using fallback query",
                    extra={"extra_data": {"product_id": product_id}}
                )
                # FEATURE-001: Query across all places in shared taxonomy
                place_uuids = [UUID(p) if isinstance(p, str) else p for p in place_ids]
                unresolved = session.query(RawMention, Review).join(
                    Review, RawMention.review_id == Review.id
                ).filter(
                    RawMention.place_id.in_(place_uuids),
                    RawMention.mention_type == 'product',
                    RawMention.resolved_product_id.is_(None)
                ).limit(20).all()
                below_threshold_mentions = [(rm, rev, 0.0) for rm, rev in unresolved]

        # Build response
        mentions = []

        # Add matched mentions (similarity = 1.0)
        for rm, review in matched_mentions:
            mentions.append(MentionResponse(
                id=str(rm.id),
                mention_text=rm.mention_text,
                mention_type=rm.mention_type,
                sentiment=rm.sentiment,
                review_id=str(review.id),
                review_text=review.text or "",
                review_author=review.author,
                review_rating=float(review.rating) if review.rating else None,
                review_date=review.review_date if isinstance(review.review_date, str) else (review.review_date.isoformat() if review.review_date else None),
                similarity_score=1.0  # Matched
            ))

        # Add below-threshold mentions with actual similarity scores
        for rm, review, score in below_threshold_mentions:
            mentions.append(MentionResponse(
                id=str(rm.id),
                mention_text=rm.mention_text,
                mention_type=rm.mention_type,
                sentiment=rm.sentiment,
                review_id=str(review.id),
                review_text=review.text or "",
                review_author=review.author,
                review_rating=float(review.rating) if review.rating else None,
                review_date=review.review_date if isinstance(review.review_date, str) else (review.review_date.isoformat() if review.review_date else None),
                similarity_score=round(score, 3)  # Actual similarity score
            ))

        # Sort by similarity score descending (matched first, then by similarity)
        mentions.sort(key=lambda x: x.similarity_score or 0, reverse=True)

        # Apply pagination
        total = len(mentions)
        mentions = mentions[offset:offset + limit]

        return MentionListResponse(
            mentions=mentions,
            total=total,
            matched_count=len(matched_mentions),
            below_threshold_count=len(below_threshold_mentions)
        )
    finally:
        session.close()


@app.get("/api/onboarding/categories/{category_id}/mentions", response_model=MentionListResponse)
async def get_category_mentions(
    category_id: str,
    include_below_threshold: bool = True,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get mentions linked to a specific category, including near-misses below threshold.

    BUG-014 FIX: Now uses vector similarity search to find mentions SIMILAR to this
    specific category, instead of returning all unresolved mentions.

    DRAFT FIX: For draft taxonomies, use centroid embedding to show potential matches
    since resolved_category_id won't be set until publish.
    """
    session = get_session()
    try:
        category_uuid = UUID(category_id)
        category = session.query(TaxonomyCategory).filter_by(id=category_uuid).first()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        # Check if taxonomy is draft (not yet published)
        is_draft = category.taxonomy and category.taxonomy.status != 'active'

        # For draft: use discovered_category_id (set during clustering)
        # For published: use resolved_category_id (set during publish)
        if is_draft:
            matched_mentions = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.discovered_category_id == category_uuid
            ).all()
        else:
            matched_mentions = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.resolved_category_id == category_uuid
            ).all()

        # For draft taxonomies OR below-threshold search: use vector similarity
        similar_mentions = []
        if category.taxonomy and (is_draft or include_below_threshold):
            # FEATURE-001: Use all_place_ids for multi-branch taxonomy support
            place_ids = [str(p) for p in category.taxonomy.all_place_ids]

            # Get category embedding for similarity search
            category_embedding = _get_category_embedding(session, category)

            if category_embedding:
                # Search MENTIONS_COLLECTION for similar mentions
                # For draft: get all potential matches (>= 0.55)
                # For published: get below-threshold near-misses (0.55-0.80)
                search_limit = 100 if is_draft else 30
                similar_results = vector_store.search_similar(
                    collection_name=vector_store.MENTIONS_COLLECTION,
                    query_vector=category_embedding,
                    place_ids=place_ids,
                    mention_type='aspect',
                    limit=search_limit,
                    score_threshold=0.55,
                )

                if similar_results:
                    # Get IDs of already-matched mentions to exclude
                    matched_ids = {str(rm.id) for rm, _ in matched_mentions}

                    for result in similar_results:
                        # For draft: include ALL similar mentions as potential matches
                        # For published: only include below-threshold (< 0.80)
                        if is_draft or result.score < 0.80:
                            # Find mention by qdrant_point_id
                            mention = session.query(RawMention).filter_by(
                                qdrant_point_id=result.id
                            ).first()

                            if mention and str(mention.id) not in matched_ids:
                                review = session.query(Review).filter_by(
                                    id=mention.review_id
                                ).first()
                                if review:
                                    similar_mentions.append(
                                        (mention, review, result.score)
                                    )

                logger.debug(
                    f"Category {category.name} - found {len(similar_mentions)} similar mentions (draft={is_draft})",
                    extra={"extra_data": {"category_id": category_id}}
                )
            else:
                # Fallback if no embedding available - use text search
                logger.warning(
                    f"No embedding for category {category_id}, using fallback text search",
                    extra={"extra_data": {"category_id": category_id}}
                )
                # FEATURE-001: Query across all places in shared taxonomy
                place_uuids = [UUID(p) if isinstance(p, str) else p for p in place_ids]
                # Search for mentions containing category name keywords
                category_keywords = category.name.replace('_', ' ').replace('&', '').split()
                fallback_query = session.query(RawMention, Review).join(
                    Review, RawMention.review_id == Review.id
                ).filter(
                    RawMention.place_id.in_(place_uuids),
                    RawMention.mention_type == 'aspect',
                )
                if not is_draft:
                    fallback_query = fallback_query.filter(RawMention.resolved_category_id.is_(None))
                fallback_results = fallback_query.limit(50).all()
                similar_mentions = [(rm, rev, 0.5) for rm, rev in fallback_results]

        # Build response
        mentions = []

        # Add matched mentions (similarity = 1.0)
        for rm, review in matched_mentions:
            mentions.append(MentionResponse(
                id=str(rm.id),
                mention_text=rm.mention_text,
                mention_type=rm.mention_type,
                sentiment=rm.sentiment,
                review_id=str(review.id),
                review_text=review.text or "",
                review_author=review.author,
                review_rating=float(review.rating) if review.rating else None,
                review_date=review.review_date if isinstance(review.review_date, str) else (review.review_date.isoformat() if review.review_date else None),
                similarity_score=1.0  # Matched
            ))

        # Add similar mentions with actual similarity scores
        for rm, review, score in similar_mentions:
            mentions.append(MentionResponse(
                id=str(rm.id),
                mention_text=rm.mention_text,
                mention_type=rm.mention_type,
                sentiment=rm.sentiment,
                review_id=str(review.id),
                review_text=review.text or "",
                review_author=review.author,
                review_rating=float(review.rating) if review.rating else None,
                review_date=review.review_date if isinstance(review.review_date, str) else (review.review_date.isoformat() if review.review_date else None),
                similarity_score=round(score, 3)  # Actual similarity score
            ))

        # Sort by similarity score descending (matched first, then by similarity)
        mentions.sort(key=lambda x: x.similarity_score or 0, reverse=True)

        # Apply pagination
        total = len(mentions)
        mentions = mentions[offset:offset + limit]

        return MentionListResponse(
            mentions=mentions,
            total=total,
            matched_count=len(matched_mentions),
            below_threshold_count=len(similar_mentions)
        )
    finally:
        session.close()


class OrphanMentionResponse(BaseModel):
    id: str
    mention_text: str
    mention_type: str
    sentiment: Optional[str]
    review_id: str
    review_text: str
    review_author: Optional[str]
    review_rating: Optional[float]
    review_date: Optional[str]


class OrphanMentionsResponse(BaseModel):
    product_orphans: List[OrphanMentionResponse]
    category_orphans: List[OrphanMentionResponse]
    total_product_orphans: int
    total_category_orphans: int


# --- Grouped Mentions Models ---

class MentionGroupResponse(BaseModel):
    normalized_text: str
    display_text: str
    mention_ids: List[str]
    count: int
    sentiments: Dict[str, int]
    avg_similarity: Optional[float]
    sample_reviews: List[str]


class GroupedMentionsResponse(BaseModel):
    groups: List[MentionGroupResponse]
    total_mentions: int
    total_groups: int
    entity_id: str
    entity_name: str


class GroupedOrphansResponse(BaseModel):
    product_groups: List[MentionGroupResponse]
    category_groups: List[MentionGroupResponse]
    total_product_mentions: int
    total_category_mentions: int
    total_product_groups: int
    total_category_groups: int


class BulkMoveMentionsRequest(BaseModel):
    mention_ids: List[UUID]
    target_type: str = Field(..., description="'product' or 'category'")
    target_id: UUID


class BulkMoveMentionsResponse(BaseModel):
    success: bool
    moved_count: int
    message: str


@app.get("/api/onboarding/taxonomies/{taxonomy_id}/orphan-mentions", response_model=OrphanMentionsResponse)
async def get_orphan_mentions(
    taxonomy_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get orphan mentions that didn't cluster or resolve to any product/category."""
    session = get_session()
    try:
        taxonomy_uuid = UUID(taxonomy_id)
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_uuid).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        # PHASE 4: Support multi-place taxonomies
        place_ids = taxonomy.all_place_ids

        # Check if draft (use discovered_*) or published (use resolved_*)
        is_draft = taxonomy.status != 'active'

        if is_draft:
            # For DRAFT: orphans are those without discovered_product_id AND discovered_category_id
            # If a product mention was moved to a category, it's no longer orphaned
            product_orphans_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'product',
                RawMention.discovered_product_id.is_(None),
                RawMention.discovered_category_id.is_(None)
            ).limit(limit).all()

            category_orphans_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'aspect',
                RawMention.discovered_category_id.is_(None)
            ).limit(limit).all()

            total_product_orphans = session.query(RawMention).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'product',
                RawMention.discovered_product_id.is_(None),
                RawMention.discovered_category_id.is_(None)
            ).count()

            total_category_orphans = session.query(RawMention).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'aspect',
                RawMention.discovered_category_id.is_(None)
            ).count()
        else:
            # For PUBLISHED: orphans are those without resolved_product_id AND resolved_category_id
            # If a product mention was moved to a category, it's no longer orphaned
            product_orphans_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'product',
                RawMention.resolved_product_id.is_(None),
                RawMention.resolved_category_id.is_(None)
            ).limit(limit).all()

            category_orphans_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'aspect',
                RawMention.resolved_category_id.is_(None)
            ).limit(limit).all()

            total_product_orphans = session.query(RawMention).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'product',
                RawMention.resolved_product_id.is_(None),
                RawMention.resolved_category_id.is_(None)
            ).count()

            total_category_orphans = session.query(RawMention).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'aspect',
                RawMention.resolved_category_id.is_(None)
            ).count()

        # Build response
        product_orphans = []
        for rm, review in product_orphans_query:
            product_orphans.append(OrphanMentionResponse(
                id=str(rm.id),
                mention_text=rm.mention_text,
                mention_type=rm.mention_type,
                sentiment=rm.sentiment,
                review_id=str(review.id),
                review_text=review.text or "",
                review_author=review.author,
                review_rating=float(review.rating) if review.rating else None,
                review_date=review.review_date if isinstance(review.review_date, str) else (review.review_date.isoformat() if review.review_date else None),
            ))

        category_orphans = []
        for rm, review in category_orphans_query:
            category_orphans.append(OrphanMentionResponse(
                id=str(rm.id),
                mention_text=rm.mention_text,
                mention_type=rm.mention_type,
                sentiment=rm.sentiment,
                review_id=str(review.id),
                review_text=review.text or "",
                review_author=review.author,
                review_rating=float(review.rating) if review.rating else None,
                review_date=review.review_date if isinstance(review.review_date, str) else (review.review_date.isoformat() if review.review_date else None),
            ))

        return OrphanMentionsResponse(
            product_orphans=product_orphans,
            category_orphans=category_orphans,
            total_product_orphans=total_product_orphans,
            total_category_orphans=total_category_orphans,
        )
    finally:
        session.close()


# --- Grouped Mentions Endpoints ---

def _mentions_to_mention_data(mentions_with_reviews) -> List[MentionData]:
    """Convert query results to MentionData objects for grouping."""
    return [
        MentionData(
            id=str(rm.id),
            mention_text=rm.mention_text,
            sentiment=rm.sentiment,
            review_text=review.text or "",
            similarity_score=getattr(rm, '_similarity_score', None)
        )
        for rm, review in mentions_with_reviews
    ]


@app.get("/api/onboarding/products/{product_id}/mentions/grouped", response_model=GroupedMentionsResponse)
async def get_grouped_product_mentions(
    product_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get mentions for a product, grouped by normalized text with fuzzy merging."""
    session = get_session()
    try:
        product_uuid = UUID(product_id)
        product = session.query(TaxonomyProduct).filter_by(id=product_uuid).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Get taxonomy to determine draft vs published
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=product.taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        place_ids = taxonomy.all_place_ids
        is_draft = taxonomy.status != 'active'

        # Query mentions for this product
        if is_draft:
            mentions_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.discovered_product_id == product_uuid
            ).all()
        else:
            mentions_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.resolved_product_id == product_uuid
            ).all()

        # Convert to MentionData and group
        mention_data = _mentions_to_mention_data(mentions_query)
        groups, total_mentions, total_groups = group_mentions(mention_data)

        return GroupedMentionsResponse(
            groups=[MentionGroupResponse(**g.to_dict()) for g in groups],
            total_mentions=total_mentions,
            total_groups=total_groups,
            entity_id=str(product.id),
            entity_name=product.display_name or product.canonical_text,
        )
    finally:
        session.close()


@app.get("/api/onboarding/categories/{category_id}/mentions/grouped", response_model=GroupedMentionsResponse)
async def get_grouped_category_mentions(
    category_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get mentions for a category, grouped by normalized text with fuzzy merging."""
    session = get_session()
    try:
        category_uuid = UUID(category_id)
        category = session.query(TaxonomyCategory).filter_by(id=category_uuid).first()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        # Get taxonomy to determine draft vs published
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=category.taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        place_ids = taxonomy.all_place_ids
        is_draft = taxonomy.status != 'active'

        # Query mentions for this category
        if is_draft:
            mentions_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.discovered_category_id == category_uuid
            ).all()
        else:
            mentions_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.resolved_category_id == category_uuid
            ).all()

        # Convert to MentionData and group
        mention_data = _mentions_to_mention_data(mentions_query)
        groups, total_mentions, total_groups = group_mentions(mention_data)

        return GroupedMentionsResponse(
            groups=[MentionGroupResponse(**g.to_dict()) for g in groups],
            total_mentions=total_mentions,
            total_groups=total_groups,
            entity_id=str(category.id),
            entity_name=category.display_name_en or category.name,
        )
    finally:
        session.close()


@app.get("/api/onboarding/taxonomies/{taxonomy_id}/orphan-mentions/grouped", response_model=GroupedOrphansResponse)
async def get_grouped_orphan_mentions(
    taxonomy_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get orphan mentions grouped by normalized text with fuzzy merging."""
    session = get_session()
    try:
        taxonomy_uuid = UUID(taxonomy_id)
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_uuid).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        place_ids = taxonomy.all_place_ids
        is_draft = taxonomy.status != 'active'

        # Query product orphans (not assigned to product OR category)
        if is_draft:
            product_orphans_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'product',
                RawMention.discovered_product_id.is_(None),
                RawMention.discovered_category_id.is_(None)
            ).all()

            category_orphans_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'aspect',
                RawMention.discovered_category_id.is_(None)
            ).all()
        else:
            product_orphans_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'product',
                RawMention.resolved_product_id.is_(None),
                RawMention.resolved_category_id.is_(None)
            ).all()

            category_orphans_query = session.query(RawMention, Review).join(
                Review, RawMention.review_id == Review.id
            ).filter(
                RawMention.place_id.in_(place_ids),
                RawMention.mention_type == 'aspect',
                RawMention.resolved_category_id.is_(None)
            ).all()

        # Group product orphans
        product_data = _mentions_to_mention_data(product_orphans_query)
        product_groups, total_product, num_product_groups = group_mentions(product_data)

        # Group category orphans
        category_data = _mentions_to_mention_data(category_orphans_query)
        category_groups, total_category, num_category_groups = group_mentions(category_data)

        return GroupedOrphansResponse(
            product_groups=[MentionGroupResponse(**g.to_dict()) for g in product_groups],
            category_groups=[MentionGroupResponse(**g.to_dict()) for g in category_groups],
            total_product_mentions=total_product,
            total_category_mentions=total_category,
            total_product_groups=num_product_groups,
            total_category_groups=num_category_groups,
        )
    finally:
        session.close()


@app.post("/api/onboarding/mentions/move", response_model=BulkMoveMentionsResponse)
async def bulk_move_mentions(
    request: BulkMoveMentionsRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Bulk move mentions to a different product or category.

    For draft taxonomies: updates discovered_product_id or discovered_category_id
    For published taxonomies: updates resolved_product_id or resolved_category_id
    """
    session = get_session()
    try:
        if not request.mention_ids:
            raise HTTPException(status_code=400, detail="No mention IDs provided")

        if request.target_type not in ('product', 'category'):
            raise HTTPException(status_code=400, detail="target_type must be 'product' or 'category'")

        # Validate target exists and get its taxonomy
        if request.target_type == 'product':
            target = session.query(TaxonomyProduct).filter_by(id=request.target_id).first()
            if not target:
                raise HTTPException(status_code=404, detail="Target product not found")
            taxonomy = session.query(PlaceTaxonomy).filter_by(id=target.taxonomy_id).first()
        else:
            target = session.query(TaxonomyCategory).filter_by(id=request.target_id).first()
            if not target:
                raise HTTPException(status_code=404, detail="Target category not found")
            taxonomy = session.query(PlaceTaxonomy).filter_by(id=target.taxonomy_id).first()

        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        is_draft = taxonomy.status != 'active'

        # Snapshot source assignments BEFORE the move so we can decrement their counts
        mentions = session.query(RawMention).filter(
            RawMention.id.in_(request.mention_ids)
        ).all()

        if is_draft:
            source_product_counts = {}
            source_category_counts = {}
            for m in mentions:
                if m.discovered_product_id:
                    pid = m.discovered_product_id
                    source_product_counts[pid] = source_product_counts.get(pid, 0) + 1
                if m.discovered_category_id:
                    cid = m.discovered_category_id
                    source_category_counts[cid] = source_category_counts.get(cid, 0) + 1
        else:
            source_product_counts = {}
            source_category_counts = {}
            for m in mentions:
                if m.resolved_product_id:
                    pid = m.resolved_product_id
                    source_product_counts[pid] = source_product_counts.get(pid, 0) + 1
                if m.resolved_category_id:
                    cid = m.resolved_category_id
                    source_category_counts[cid] = source_category_counts.get(cid, 0) + 1

        # Update mentions
        # When moving to a category: update category AND clear product link
        # When moving to a product: update product AND set category to product's category
        if request.target_type == 'product':
            product_category_id = target.assigned_category_id or target.discovered_category_id
            if is_draft:
                moved_count = session.query(RawMention).filter(
                    RawMention.id.in_(request.mention_ids)
                ).update(
                    {
                        RawMention.discovered_product_id: request.target_id,
                        RawMention.discovered_category_id: product_category_id,
                    },
                    synchronize_session=False
                )
            else:
                moved_count = session.query(RawMention).filter(
                    RawMention.id.in_(request.mention_ids)
                ).update(
                    {
                        RawMention.resolved_product_id: request.target_id,
                        RawMention.resolved_category_id: product_category_id,
                    },
                    synchronize_session=False
                )
        else:
            if is_draft:
                moved_count = session.query(RawMention).filter(
                    RawMention.id.in_(request.mention_ids)
                ).update(
                    {
                        RawMention.discovered_category_id: request.target_id,
                        RawMention.discovered_product_id: None,
                    },
                    synchronize_session=False
                )
            else:
                moved_count = session.query(RawMention).filter(
                    RawMention.id.in_(request.mention_ids)
                ).update(
                    {
                        RawMention.resolved_category_id: request.target_id,
                        RawMention.resolved_product_id: None,
                    },
                    synchronize_session=False
                )

        # Decrement counts on sources
        for pid, count in source_product_counts.items():
            if pid != request.target_id:  # Don't decrement if moving within same product
                source_prod = session.query(TaxonomyProduct).filter_by(id=pid).first()
                if source_prod:
                    source_prod.discovered_mention_count = max(0, (source_prod.discovered_mention_count or 0) - count)

        for cid, count in source_category_counts.items():
            target_cat_id = request.target_id if request.target_type == 'category' else product_category_id
            if cid != target_cat_id:  # Don't decrement if moving within same category
                source_cat = session.query(TaxonomyCategory).filter_by(id=cid).first()
                if source_cat:
                    source_cat.discovered_mention_count = max(0, (source_cat.discovered_mention_count or 0) - count)

        # Increment count on target
        target.discovered_mention_count = (target.discovered_mention_count or 0) + moved_count

        # When moving to a product, also increment the product's category count
        # for mentions that came from a different category
        if request.target_type == 'product' and product_category_id:
            cat_increment = 0
            for cid, count in source_category_counts.items():
                if cid != product_category_id:
                    cat_increment += count
            # Also count mentions that had no source category
            cat_increment += moved_count - sum(source_category_counts.values())
            if cat_increment > 0:
                target_cat = session.query(TaxonomyCategory).filter_by(id=product_category_id).first()
                if target_cat:
                    target_cat.discovered_mention_count = (target_cat.discovered_mention_count or 0) + cat_increment

        # Log the action
        target_name = target.display_name if request.target_type == 'product' else (target.display_name_en or target.name)
        log_taxonomy_action(
            session, taxonomy.id, current_user.id,
            "bulk_move", "mention", None,
            {"target_type": request.target_type, "target_id": str(request.target_id), "target_name": target_name},
            {"moved_count": moved_count}
        )

        # Learn from corrections - add mention texts to anchor examples
        # This enables immediate anchor improvement without waiting for publish
        learned_count = 0
        if moved_count > 0:
            try:
                from anchor_manager import learn_from_corrections
                learned_count = learn_from_corrections(
                    session=session,
                    mention_ids=request.mention_ids,
                    target_type=request.target_type,
                    target_id=request.target_id,
                    taxonomy=taxonomy,
                )
            except Exception as e:
                # Log but don't fail the move operation
                logger.warning(f"Failed to learn from corrections: {e}")

        # Update Qdrant PRODUCTS_COLLECTION with correction vectors
        # Only for active taxonomies (draft has no published vectors)
        qdrant_updated = 0
        if moved_count > 0 and taxonomy.status == 'active':
            try:
                from anchor_manager import update_product_vectors_from_corrections
                qdrant_updated = update_product_vectors_from_corrections(
                    session=session,
                    mention_ids=request.mention_ids,
                    target_type=request.target_type,
                    target_id=request.target_id,
                    taxonomy=taxonomy,
                )
            except Exception as e:
                logger.warning(f"Failed to update product vectors: {e}")

        session.commit()

        message = f"Moved {moved_count} mentions to {target_name}"
        if learned_count > 0:
            message += f" (learned {learned_count} new patterns)"
        if qdrant_updated > 0:
            message += f" (+{qdrant_updated} vectors updated)"

        return BulkMoveMentionsResponse(
            success=True,
            moved_count=moved_count,
            message=message
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error bulk moving mentions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# --- Taxonomy Publish Helpers ---

def _index_taxonomy_vectors(session, place_id: str, taxonomy_id: str, products, categories) -> tuple:
    """
    Generate embeddings and index approved taxonomy items in Qdrant.

    BUG-003 FIX: Added validation and logging for embedding failures.

    Returns:
        tuple: (indexed_count, skipped_products, skipped_categories)
    """
    import numpy as np

    products_to_index = []
    categories_to_index = []
    skipped_products = []
    skipped_categories = []

    # Batch generate embeddings for all products
    if products:
        # Collect all texts with their product index
        all_texts = []
        product_text_ranges = []  # (product, start_idx, end_idx)

        for p in products:
            texts = [p.canonical_text] + (p.variants or [])[:3]
            start_idx = len(all_texts)
            all_texts.extend(texts)
            product_text_ranges.append((p, start_idx, len(all_texts)))

        # Single batch embedding call
        all_embeddings = embedding_client.generate_embeddings(all_texts, normalize=True)

        # BUG-003 FIX: Validate embedding generation result
        if all_embeddings is None:
            logger.error(
                "Embedding generation failed completely for products",
                extra={"extra_data": {
                    "place_id": place_id,
                    "taxonomy_id": taxonomy_id,
                    "product_count": len(products),
                    "text_count": len(all_texts)
                }}
            )
            skipped_products = [p.canonical_text for p in products]
        elif len(all_embeddings) != len(all_texts):
            logger.error(
                f"Embedding count mismatch: expected {len(all_texts)}, got {len(all_embeddings)}",
                extra={"extra_data": {
                    "place_id": place_id,
                    "taxonomy_id": taxonomy_id,
                    "expected": len(all_texts),
                    "actual": len(all_embeddings)
                }}
            )
            # Process what we can, but log the discrepancy
            all_embeddings = all_embeddings or []

        if all_embeddings:
            # BUG-008 FIX: Index each variant separately instead of averaging
            # This improves cross-lingual matching (Arabic variants match Arabic mentions)
            for p, start_idx, end_idx in product_text_ranges:
                # Check if we have embeddings for this product's range
                if end_idx <= len(all_embeddings):
                    texts = [p.canonical_text] + (p.variants or [])[:3]
                    product_embs = all_embeddings[start_idx:end_idx]
                    category_id = str(p.assigned_category_id) if p.assigned_category_id else None
                    product_id = str(p.id)
                    indexed_any = False

                    # Index each variant as a separate point with same entity_id
                    for i, (text, emb) in enumerate(zip(texts, product_embs)):
                        if emb is not None and not all(v == 0.0 for v in emb):
                            # Use product_id for canonical, uuid5 for variants (Qdrant requires valid UUIDs)
                            if i == 0:
                                point_id = product_id
                            else:
                                point_id = str(uuid.uuid5(uuid.UUID(product_id), f"v{i}"))
                            products_to_index.append((point_id, text, emb, product_id, category_id))
                            indexed_any = True

                    if indexed_any:
                        p.vector_id = product_id  # Reference to canonical point
                    else:
                        skipped_products.append(p.canonical_text)
                        logger.warning(
                            f"Skipping product with invalid embeddings: {p.canonical_text}",
                            extra={"extra_data": {"product_id": str(p.id)}}
                        )
                else:
                    skipped_products.append(p.canonical_text)
                    logger.warning(
                        f"Skipping product - embeddings out of range: {p.canonical_text}",
                        extra={"extra_data": {"product_id": str(p.id), "start": start_idx, "end": end_idx}}
                    )

    # Process aspect categories (has_products=False)
    # BUG-006 FIX: Use stored centroid embeddings when available, fallback to name-based
    aspect_categories = [c for c in categories if not c.has_products]
    if aspect_categories:
        # Separate categories with/without stored centroids
        cats_with_centroid = [c for c in aspect_categories if c.centroid_embedding]
        cats_without_centroid = [c for c in aspect_categories if not c.centroid_embedding]

        # Use stored centroids directly (BUG-006 FIX)
        for c in cats_with_centroid:
            emb = c.centroid_embedding
            if emb is not None and not all(v == 0.0 for v in emb):
                categories_to_index.append((str(c.id), c.name, emb))
                c.vector_id = str(c.id)
                logger.debug(f"Using stored centroid for category: {c.name}")
            else:
                skipped_categories.append(c.name)
                logger.warning(f"Stored centroid invalid for category: {c.name}")

        # Generate embeddings from name for categories without centroids (legacy data)
        if cats_without_centroid:
            cat_texts = [c.name for c in cats_without_centroid]
            cat_embeddings = embedding_client.generate_embeddings(cat_texts, normalize=True)

            # BUG-003 FIX: Validate category embedding generation
            if cat_embeddings is None:
                logger.error(
                    "Embedding generation failed for categories without centroids",
                    extra={"extra_data": {
                        "place_id": place_id,
                        "category_count": len(cats_without_centroid)
                    }}
                )
                skipped_categories.extend([c.name for c in cats_without_centroid])
            elif len(cat_embeddings) != len(cat_texts):
                logger.error(
                    f"Category embedding count mismatch: expected {len(cat_texts)}, got {len(cat_embeddings)}",
                    extra={"extra_data": {"place_id": place_id}}
                )
                cat_embeddings = cat_embeddings or []

            if cat_embeddings:
                for i, c in enumerate(cats_without_centroid):
                    if i < len(cat_embeddings):
                        emb = cat_embeddings[i]
                        if emb is not None and not all(v == 0.0 for v in emb):
                            categories_to_index.append((str(c.id), c.name, emb))
                            c.vector_id = str(c.id)
                            logger.debug(f"Generated embedding from name for category: {c.name}")
                        else:
                            skipped_categories.append(c.name)
                            logger.warning(f"Skipping category with invalid embedding: {c.name}")
                    else:
                        skipped_categories.append(c.name)

    # Log summary if any items were skipped
    if skipped_products or skipped_categories:
        logger.warning(
            f"Indexing incomplete: {len(skipped_products)} products and {len(skipped_categories)} categories skipped",
            extra={"extra_data": {
                "place_id": place_id,
                "taxonomy_id": taxonomy_id,
                "skipped_products": skipped_products[:10],  # Limit to first 10
                "skipped_categories": skipped_categories[:10]
            }}
        )

    indexed_count = vector_store.index_approved_taxonomy(
        place_id, taxonomy_id, products_to_index, categories_to_index
    )

    return indexed_count, len(skipped_products), len(skipped_categories)


def _resolve_mentions_batch(session, place_id: str, taxonomy_id: str = None) -> tuple:
    """
    Resolve RawMentions using vector similarity against approved taxonomy.

    BUG-005 FIX: Now resolves ALL mentions for the place, not just completely unresolved ones.
    This allows:
    - Re-resolution when new products are approved
    - Better matching when a mention was only category-resolved before

    Args:
        session: Database session
        place_id: Place UUID
        taxonomy_id: Optional taxonomy ID to limit resolution to specific taxonomy's products

    Returns:
        tuple: (products_resolved, categories_resolved)
    """
    from uuid import UUID as UUIDType
    from sqlalchemy import or_

    product_resolved = 0
    category_resolved = 0

    # Convert place_id to UUID for query if needed
    place_uuid = UUIDType(place_id) if isinstance(place_id, str) else place_id

    # BUG-005 FIX: Get ALL mentions for this place that could benefit from resolution
    # This includes:
    # 1. Completely unresolved (both NULL)
    # 2. Category-only resolved (product NULL) - might match a newly approved product
    # 3. Already resolved - might match a BETTER product in new taxonomy
    mentions = session.query(RawMention).filter(
        RawMention.place_id == place_uuid,
    ).all()

    if not mentions:
        return 0, 0

    # Track which mentions changed for logging
    newly_resolved = 0
    re_resolved = 0

    mention_texts = [m.mention_text for m in mentions]
    embeddings = embedding_client.generate_embeddings(mention_texts, normalize=True)

    if not embeddings:
        logger.warning("Batch embedding generation failed for mention resolution",
                      extra={"extra_data": {"place_id": place_id, "mention_count": len(mentions)}})
        return 0, 0

    for mention, emb in zip(mentions, embeddings):
        # Skip if embedding failed for this mention
        if emb is None or (hasattr(emb, '__len__') and len(emb) == 0):
            continue

        result = vector_store.find_matching_product(
            text_embedding=emb,
            place_id=place_id,
            mention_type=mention.mention_type,
        )

        if result:
            payload = result.payload
            was_unresolved = mention.resolved_product_id is None and mention.resolved_category_id is None

            if payload.entity_type == "product":
                new_product_id = UUID(payload.entity_id)
                new_category_id = UUID(payload.category_id) if payload.category_id else None

                # Only count as resolved if it changed
                if mention.resolved_product_id != new_product_id:
                    mention.resolved_product_id = new_product_id
                    mention.resolved_category_id = new_category_id
                    product_resolved += 1
                    if was_unresolved:
                        newly_resolved += 1
                    else:
                        re_resolved += 1
            else:
                new_category_id = UUID(payload.entity_id)
                # Only update category if not already product-resolved
                if mention.resolved_product_id is None and mention.resolved_category_id != new_category_id:
                    mention.resolved_category_id = new_category_id
                    category_resolved += 1
                    if was_unresolved:
                        newly_resolved += 1
                    else:
                        re_resolved += 1

    if re_resolved > 0:
        logger.info(f"Re-resolved {re_resolved} previously resolved mentions to better matches",
                   extra={"extra_data": {"place_id": place_id}})

    return product_resolved, category_resolved


def _aggregate_taxonomy_analytics(session, taxonomy_id: UUID):
    """
    Compute and store aggregated mention_count and avg_sentiment for this taxonomy's products/categories.

    BUG-002 FIX: Category stats now include both:
    1. Direct category mentions (aspects like "service was slow")
    2. Indirect mentions through products (e.g., "Spanish Latte" -> "Hot Coffee" category)
    """

    # Get approved products for this taxonomy (need full objects for category rollup)
    approved_products = session.query(TaxonomyProduct).filter_by(
        taxonomy_id=taxonomy_id, is_approved=True
    ).all()
    approved_product_ids = [p.id for p in approved_products]

    # Get approved category IDs for this taxonomy
    approved_category_ids = [
        c.id for c in session.query(TaxonomyCategory).filter_by(
            taxonomy_id=taxonomy_id, is_approved=True
        ).all()
    ]

    # Build product -> category mapping for rollup
    product_to_category = {
        p.id: p.assigned_category_id for p in approved_products if p.assigned_category_id
    }

    # Aggregate for products (only this taxonomy's products)
    product_stats_map = {}  # product_id -> (count, sentiment_sum)
    if approved_product_ids:
        product_stats = session.query(
            RawMention.resolved_product_id,
            func.count(RawMention.id).label('count'),
            func.avg(case(
                (RawMention.sentiment == 'positive', 1.0),
                (RawMention.sentiment == 'negative', -1.0),
                else_=0.0
            )).label('avg_sent')
        ).filter(
            RawMention.resolved_product_id.in_(approved_product_ids)
        ).group_by(RawMention.resolved_product_id).all()

        for product_id, count, avg_sent in product_stats:
            product = session.query(TaxonomyProduct).filter_by(id=product_id).first()
            if product:
                product.mention_count = count
                product.avg_sentiment = (avg_sent + 1) / 2 if avg_sent is not None else 0.5
                # Store for category rollup
                product_stats_map[product_id] = (count, avg_sent if avg_sent is not None else 0.0)

    # Aggregate for categories - TWO SOURCES:
    # 1. Direct category mentions (aspects)
    # 2. Rollup from products assigned to each category
    if approved_category_ids:
        # Initialize category stats with zeros
        category_totals = {cid: {'count': 0, 'sentiment_sum': 0.0} for cid in approved_category_ids}

        # Source 1: Direct category mentions (aspects like "service was slow")
        direct_category_stats = session.query(
            RawMention.resolved_category_id,
            func.count(RawMention.id).label('count'),
            func.sum(case(
                (RawMention.sentiment == 'positive', 1.0),
                (RawMention.sentiment == 'negative', -1.0),
                else_=0.0
            )).label('sent_sum')
        ).filter(
            RawMention.resolved_category_id.in_(approved_category_ids),
            RawMention.resolved_product_id.is_(None),  # Direct mentions only
        ).group_by(RawMention.resolved_category_id).all()

        for category_id, count, sent_sum in direct_category_stats:
            if category_id in category_totals:
                category_totals[category_id]['count'] += count
                category_totals[category_id]['sentiment_sum'] += (sent_sum or 0.0)

        # Source 2: Rollup from products in each category
        for product_id, (count, avg_sent) in product_stats_map.items():
            category_id = product_to_category.get(product_id)
            if category_id and category_id in category_totals:
                category_totals[category_id]['count'] += count
                # Convert avg back to sum: avg_sent * count = sum
                category_totals[category_id]['sentiment_sum'] += float(avg_sent or 0) * count

        # Update category records
        for category_id, totals in category_totals.items():
            category = session.query(TaxonomyCategory).filter_by(id=category_id).first()
            if category:
                count = totals['count']
                if count > 0:
                    avg_sent = totals['sentiment_sum'] / count
                    category.mention_count = count
                    category.avg_sentiment = (avg_sent + 1) / 2  # Normalize from [-1,1] to [0,1]
                else:
                    category.mention_count = 0
                    category.avg_sentiment = 0.5  # Neutral default


@app.post("/api/onboarding/taxonomies/{taxonomy_id}/import", response_model=TaxonomyImportResponse)
async def import_taxonomy(
    taxonomy_id: UUID,
    request: TaxonomyImportRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Import categories/products into a draft taxonomy and trigger re-clustering.

    This will:
    1. Validate taxonomy exists and is in draft status
    2. Archive the old taxonomy (for learning/comparison)
    3. Generate anchors from import data
    4. Run re-clustering synchronously
    5. Return the NEW taxonomy ID (re-clustering creates a new UUID)
    """
    from anchor_manager import generate_anchors_from_import
    from clustering_job import run_clustering_job

    session = get_session()
    try:
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        if taxonomy.status != "draft":
            raise HTTPException(status_code=400, detail="Can only import into draft taxonomies")

        place_id = str(taxonomy.place_id)
        place_name = taxonomy.place.name if taxonomy.place else "Unknown"

        # Step 1: Archive the old taxonomy before re-clustering
        categories = session.query(TaxonomyCategory).filter_by(taxonomy_id=taxonomy_id).all()
        products = session.query(TaxonomyProduct).filter_by(taxonomy_id=taxonomy_id).all()

        # Build snapshot
        snapshot = {
            "taxonomy": {
                "id": str(taxonomy.id),
                "place_id": str(taxonomy.place_id),
                "status": taxonomy.status,
                "reviews_sampled": taxonomy.reviews_sampled,
                "entities_discovered": taxonomy.entities_discovered,
                "created_at": taxonomy.created_at.isoformat() if taxonomy.created_at else None,
            },
            "categories": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "display_name_en": c.display_name_en,
                    "display_name_ar": c.display_name_ar,
                    "parent_id": str(c.parent_id) if c.parent_id else None,
                    "has_products": c.has_products,
                    "source": c.source,
                    "is_approved": c.is_approved,
                    "mention_count": c.mention_count,
                    "centroid_embedding": c.centroid_embedding,
                }
                for c in categories
            ],
            "products": [
                {
                    "id": str(p.id),
                    "canonical_text": p.canonical_text,
                    "display_name": p.display_name,
                    "assigned_category_id": str(p.assigned_category_id) if p.assigned_category_id else None,
                    "variants": p.variants,
                    "source": p.source,
                    "is_approved": p.is_approved,
                    "mention_count": p.mention_count,
                }
                for p in products
            ],
        }

        archive = TaxonomyArchive(
            original_taxonomy_id=taxonomy_id,
            place_id=taxonomy.place_id,
            place_name=place_name,
            archive_reason="import_recluster",
            archived_by=current_user.id,
            snapshot=snapshot,
            categories_count=len(categories),
            products_count=len(products),
            status_at_archive=taxonomy.status,
        )
        session.add(archive)
        session.flush()
        archive_id = str(archive.id)

        # Log archive action
        log_taxonomy_action(
            session, taxonomy_id, current_user.id,
            "archive", "taxonomy", taxonomy_id,
            None,
            {"archive_id": archive_id, "reason": "import_recluster"}
        )

        session.commit()

        # Clean up speculative correction examples from the old taxonomy
        try:
            from anchor_manager import cleanup_orphaned_examples
            cleaned = cleanup_orphaned_examples(session, taxonomy_id)
            if cleaned > 0:
                session.commit()
                logger.info(f"Cleaned {cleaned} correction examples before re-cluster")
        except Exception as e:
            logger.warning(f"Failed to clean orphaned examples: {e}")

        # Step 2: Generate anchors from import data (returns anchors + hierarchy info)
        import_dicts = [cat.model_dump() for cat in request.categories]
        import_anchors, hierarchy_info = generate_anchors_from_import(import_dicts)

        # Step 3: Run re-clustering synchronously to get new taxonomy ID
        # Note: This deletes the old taxonomy and creates a new one
        try:
            new_taxonomy_id = run_clustering_job(
                place_id=place_id,
                import_anchors=import_anchors,
                import_hierarchy=hierarchy_info,
                is_recluster=True,
            )
        except Exception as e:
            logger.error(f"Re-clustering failed after import: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Re-clustering failed: {e}")

        # Step 4: Update archive with new taxonomy ID and clear reclustering flag
        s = get_session()
        try:
            # Update archive with replacement ID
            arch = s.query(TaxonomyArchive).filter_by(id=archive.id).first()
            if arch and new_taxonomy_id:
                arch.replaced_by_taxonomy_id = uuid.UUID(new_taxonomy_id)

            # Clear re-clustering flag on new taxonomy
            if new_taxonomy_id:
                new_tax = s.query(PlaceTaxonomy).filter_by(id=new_taxonomy_id).first()
                if new_tax and new_tax.is_reclustering:
                    new_tax.is_reclustering = False

            s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()

        return TaxonomyImportResponse(
            success=True,
            message=f"Import complete. Old taxonomy archived, new taxonomy created with re-clustered data.",
            new_taxonomy_id=new_taxonomy_id,
            archived_taxonomy_id=archive_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to import taxonomy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


class MenuImageResponse(BaseModel):
    id: str
    image_url: str
    original_url: Optional[str]
    created_at: Optional[str]


class MenuImagesListResponse(BaseModel):
    images: List[MenuImageResponse]
    total: int
    place_name: Optional[str]


@app.get("/api/onboarding/taxonomies/{taxonomy_id}/menu-images", response_model=MenuImagesListResponse)
async def get_taxonomy_menu_images(
    taxonomy_id: UUID,
    current_user: User = Depends(get_current_user)
):
    """Get menu images for a taxonomy's place(s)."""
    session = get_session()
    try:
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        place_ids = taxonomy.all_place_ids
        images = session.query(PlaceMenuImage).filter(
            PlaceMenuImage.place_id.in_(place_ids)
        ).order_by(PlaceMenuImage.created_at.desc()).all()

        place_name = taxonomy.place.name if taxonomy.place else None

        return MenuImagesListResponse(
            images=[
                MenuImageResponse(
                    id=str(img.id),
                    image_url=img.image_url,
                    original_url=img.original_url,
                    created_at=img.created_at.isoformat() if img.created_at else None,
                )
                for img in images
            ],
            total=len(images),
            place_name=place_name,
        )
    finally:
        session.close()


# --- Taxonomy Archives Endpoints ---

class ArchiveSummary(BaseModel):
    """Summary of an archived taxonomy."""
    id: str
    original_taxonomy_id: str
    place_id: str
    place_name: Optional[str]
    archive_reason: str
    categories_count: int
    products_count: int
    status_at_archive: Optional[str]
    replaced_by_taxonomy_id: Optional[str]
    created_at: Optional[str]


class ArchiveListResponse(BaseModel):
    """List of archived taxonomies."""
    archives: List[ArchiveSummary]
    total: int


class ArchiveDetailResponse(BaseModel):
    """Full archive detail with snapshot."""
    id: str
    original_taxonomy_id: str
    place_id: str
    place_name: Optional[str]
    archive_reason: str
    categories_count: int
    products_count: int
    status_at_archive: Optional[str]
    replaced_by_taxonomy_id: Optional[str]
    snapshot: dict
    created_at: Optional[str]


@app.get("/api/onboarding/archives", response_model=ArchiveListResponse)
async def list_taxonomy_archives(
    place_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user)
):
    """List all archived taxonomies, optionally filtered by place."""
    session = get_session()
    try:
        query = session.query(TaxonomyArchive).order_by(TaxonomyArchive.created_at.desc())
        if place_id:
            query = query.filter_by(place_id=place_id)
        archives = query.all()

        return ArchiveListResponse(
            archives=[
                ArchiveSummary(
                    id=str(a.id),
                    original_taxonomy_id=str(a.original_taxonomy_id),
                    place_id=str(a.place_id),
                    place_name=a.place_name,
                    archive_reason=a.archive_reason,
                    categories_count=a.categories_count or 0,
                    products_count=a.products_count or 0,
                    status_at_archive=a.status_at_archive,
                    replaced_by_taxonomy_id=str(a.replaced_by_taxonomy_id) if a.replaced_by_taxonomy_id else None,
                    created_at=a.created_at.isoformat() if a.created_at else None,
                )
                for a in archives
            ],
            total=len(archives),
        )
    finally:
        session.close()


@app.get("/api/onboarding/archives/{archive_id}", response_model=ArchiveDetailResponse)
async def get_taxonomy_archive(
    archive_id: UUID,
    current_user: User = Depends(get_current_user)
):
    """Get full archive detail including snapshot."""
    session = get_session()
    try:
        archive = session.query(TaxonomyArchive).filter_by(id=archive_id).first()
        if not archive:
            raise HTTPException(status_code=404, detail="Archive not found")

        return ArchiveDetailResponse(
            id=str(archive.id),
            original_taxonomy_id=str(archive.original_taxonomy_id),
            place_id=str(archive.place_id),
            place_name=archive.place_name,
            archive_reason=archive.archive_reason,
            categories_count=archive.categories_count or 0,
            products_count=archive.products_count or 0,
            status_at_archive=archive.status_at_archive,
            replaced_by_taxonomy_id=str(archive.replaced_by_taxonomy_id) if archive.replaced_by_taxonomy_id else None,
            snapshot=archive.snapshot,
            created_at=archive.created_at.isoformat() if archive.created_at else None,
        )
    finally:
        session.close()


@app.post("/api/onboarding/taxonomies/{taxonomy_id}/publish", response_model=ActionResponse)
async def publish_taxonomy(
    taxonomy_id: UUID,
    current_user: User = Depends(get_current_user)
):
    """
    Publish a taxonomy (draft -> active) with vector-based resolution.

    This will:
    1. Set status to 'active'
    2. Index approved products/categories in Qdrant PRODUCTS_COLLECTION
    3. Resolve all RawMentions using vector similarity
    4. Aggregate mention_count and avg_sentiment on products/categories
    5. Log the publish action
    """
    session = get_session()
    lock_acquired = False
    try:
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        # BUG-007 FIX: Acquire advisory lock to prevent concurrent publish
        # Use taxonomy UUID's int representation as lock key
        lock_key = taxonomy_id.int % (2**31 - 1)  # PostgreSQL bigint limit
        session.execute(text(f"SELECT pg_advisory_lock({lock_key})"))
        lock_acquired = True

        # Re-check status after acquiring lock (another request may have published)
        session.refresh(taxonomy)
        if taxonomy.status == "active":
            raise HTTPException(status_code=400, detail="Taxonomy already published")

        place_id = str(taxonomy.place_id)

        # Get approved items
        approved_categories = session.query(TaxonomyCategory).filter_by(
            taxonomy_id=taxonomy_id, is_approved=True
        ).all()
        approved_products = session.query(TaxonomyProduct).filter_by(
            taxonomy_id=taxonomy_id, is_approved=True
        ).all()

        if not approved_categories and not approved_products:
            raise HTTPException(status_code=400, detail="No approved categories or products")

        # Update taxonomy status
        old_status = taxonomy.status
        taxonomy.status = "active"
        taxonomy.published_at = datetime.utcnow()
        taxonomy.published_by = current_user.id

        # Step 1: Index approved items in Qdrant
        indexed_count, skipped_products, skipped_categories = _index_taxonomy_vectors(
            session, place_id, str(taxonomy_id), approved_products, approved_categories
        )

        # BUG-003 FIX: Warn if significant items were skipped
        if skipped_products > 0 or skipped_categories > 0:
            logger.warning(
                f"Publish completed with skipped items: {skipped_products} products, {skipped_categories} categories",
                extra={"extra_data": {"taxonomy_id": str(taxonomy_id), "place_id": place_id}}
            )

        # Step 2: Resolve mentions using vector similarity
        products_resolved, categories_resolved = _resolve_mentions_batch(session, place_id)

        # Step 3: Aggregate analytics
        _aggregate_taxonomy_analytics(session, taxonomy_id)

        # Log publish action
        log_taxonomy_action(
            session, taxonomy_id, current_user.id,
            "publish", "taxonomy", taxonomy_id,
            {"status": old_status},
            {
                "status": "active",
                "indexed_vectors": indexed_count,
                "skipped_products": skipped_products,
                "skipped_categories": skipped_categories,
                "products_resolved": products_resolved,
                "categories_resolved": categories_resolved,
            }
        )

        session.commit()

        # Invalidate insights cache for all places in this taxonomy (non-blocking)
        try:
            from redis_client import invalidate_insights
            for pid in all_place_ids:
                invalidate_insights(str(pid))
        except Exception as e:
            logger.warning(f"Failed to invalidate insights cache: {e}")

        # Auto-learn anchors from approved categories (non-blocking)
        from anchor_manager import learn_from_approved_taxonomy
        try:
            learned_count = learn_from_approved_taxonomy(str(taxonomy_id))
            logger.info(f"Auto-learned {learned_count} examples from taxonomy {taxonomy_id}",
                       extra={"extra_data": {"taxonomy_id": str(taxonomy_id), "place_id": place_id}})
        except Exception as e:
            logger.warning(f"Auto-learning failed (non-blocking): {e}",
                         extra={"extra_data": {"taxonomy_id": str(taxonomy_id)}})

        # Queue reviews for sentiment analysis now that taxonomy is active
        # Fetch all reviews for ALL places in this taxonomy that don't have analysis yet
        all_place_ids = taxonomy.all_place_ids
        reviews_to_analyze = session.query(Review).filter(
            Review.place_id.in_(all_place_ids),
            Review.job_id.isnot(None)  # Must have a job_id
        ).outerjoin(ReviewAnalysis, Review.id == ReviewAnalysis.review_id).filter(
            ReviewAnalysis.id.is_(None)  # No existing analysis
        ).all()

        queued_count = 0
        if reviews_to_analyze:
            try:
                channel = get_channel()
                for review in reviews_to_analyze:
                    # Review already has job_id, no need to query Job
                    publish_message(channel, {
                        "review_id": str(review.id),
                        "job_id": str(review.job_id),
                        "mode": "sentiment"  # Only sentiment analysis, extraction already done
                    })
                    queued_count += 1
                logger.info(f"Queued {queued_count} reviews for sentiment analysis after publish",
                           extra={"extra_data": {"taxonomy_id": str(taxonomy_id), "place_id": place_id}})
            except Exception as e:
                logger.warning(f"Failed to queue reviews for sentiment analysis: {e}",
                             extra={"extra_data": {"taxonomy_id": str(taxonomy_id)}})

        # Build response message
        message = f"Taxonomy published. {indexed_count} items indexed, "
        message += f"{products_resolved} product mentions and {categories_resolved} category mentions resolved."
        if queued_count > 0:
            message += f" {queued_count} reviews queued for sentiment analysis."
        if skipped_products > 0 or skipped_categories > 0:
            message += f" Warning: {skipped_products} products and {skipped_categories} categories could not be indexed."

        return ActionResponse(
            success=True,
            message=message
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to publish taxonomy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # BUG-007 FIX: Release advisory lock
        if lock_acquired:
            try:
                lock_key = taxonomy_id.int % (2**31 - 1)
                session.execute(text(f"SELECT pg_advisory_unlock({lock_key})"))
            except Exception:
                pass  # Lock will be released when session closes anyway
        session.close()


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

    Accepts either:
    - A search query (e.g., "coffee shops in Riyadh")
    - A Google Maps URL (e.g., "https://google.com/maps/place/...")

    This will:
    1. Create a scrape job record
    2. Start the Google Maps scraper in the background
    3. Automatically process results when scraping completes
    """
    query = request.query.strip()
    depth = request.depth

    # Detect if input is a Google Maps URL
    if is_google_maps_url(query):
        original_url = query

        # Resolve short URLs first (goo.gl, maps.app.goo.gl, etc.)
        if is_short_url(query):
            logger.info("Resolving short URL", extra={"extra_data": {"url": query}})
            resolved_url = await resolve_short_url(query)
            logger.info("Short URL resolved", extra={"extra_data": {"original": query, "resolved": resolved_url}})
            query = resolved_url

        # Extract place name from URL for better search
        place_name = extract_place_from_url(query)
        if place_name:
            query = place_name
            depth = 1  # Single place, no need for deep scroll
            logger.info("Extracted place from URL", extra={"extra_data": {"original": original_url, "extracted": query}})
        else:
            # Can't extract name, use the full resolved URL
            logger.info("Could not extract place name from URL", extra={"extra_data": {"url": query}})
            depth = 1

    # Create job record with user_id
    job = create_scrape_job(
        query,
        notification_email=request.notification_email,
        user_id=str(current_user.id)
    )

    # Start background task
    background_tasks.add_task(
        run_scrape_pipeline,
        query=query,
        scrape_job_id=str(job.id),
        depth=depth,
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
async def get_stats(place_id: Optional[str] = None):
    """Get statistics for the dashboard, optionally filtered by place."""
    session = get_session()
    try:
        # Base queries - filter by place if specified
        if place_id:
            place_uuid = UUID(place_id)
            places_count = 1
            reviews_count = session.query(Review).join(Job).filter(Job.place_id == place_uuid).count()
            analyzable_count = session.query(Review).join(Job).filter(
                Job.place_id == place_uuid, Review.text.isnot(None), Review.text != ''
            ).count()
            analyses_count = session.query(ReviewAnalysis).join(Review).join(Job).filter(Job.place_id == place_uuid).count()
            mentions_count = session.query(RawMention).filter(RawMention.place_id == place_uuid).count()
        else:
            places_count = session.query(Place).count()
            reviews_count = session.query(Review).count()
            analyzable_count = session.query(Review).filter(
                Review.text.isnot(None), Review.text != ''
            ).count()
            analyses_count = session.query(ReviewAnalysis).count()
            mentions_count = session.query(RawMention).count()

        # Get RabbitMQ queue status
        queue_messages = 0
        queue_consumers = 0
        try:
            import pika
            params = pika.URLParameters(RABBITMQ_URL)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            queue = channel.queue_declare(queue=QUEUE_NAME, passive=True)
            queue_messages = queue.method.message_count
            queue_consumers = queue.method.consumer_count
            connection.close()
        except Exception:
            pass  # Queue stats unavailable

        # Job status counts
        job_statuses = (
            session.query(ScrapeJob.status, func.count(ScrapeJob.id))
            .group_by(ScrapeJob.status)
            .all()
        )
        scrape_jobs = {status: count for status, count in job_statuses}

        return {
            "place_id": place_id,
            "places_count": places_count,
            "reviews_count": reviews_count,
            "analyses_count": analyses_count,
            "mentions_count": mentions_count,
            "pending_analyses": max(0, analyzable_count - analyses_count),
            "queue_messages": queue_messages,
            "queue_consumers": queue_consumers,
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


@app.get("/api/pipeline-status")
async def get_pipeline_status(place_id: Optional[str] = None):
    """Get pipeline stage status for a place or all places."""
    session = get_session()
    try:
        if place_id:
            # Single place pipeline status
            place_uuid = UUID(place_id)
            place = session.query(Place).filter_by(id=place_uuid).first()
            if not place:
                raise HTTPException(status_code=404, detail="Place not found")

            return _get_place_pipeline_status(session, place)
        else:
            # All places pipeline status
            places = session.query(Place).order_by(Place.created_at.desc()).limit(20).all()
            return {
                "places": [_get_place_pipeline_status(session, p) for p in places]
            }
    finally:
        session.close()


def _get_place_pipeline_status(session, place) -> dict:
    """Calculate pipeline stage for a single place."""
    place_id = place.id

    # Count reviews (total and analyzable — reviews with text)
    reviews_count = session.query(Review).join(Job).filter(Job.place_id == place_id).count()
    analyzable_reviews = session.query(Review).join(Job).filter(
        Job.place_id == place_id,
        Review.text.isnot(None),
        Review.text != ''
    ).count()

    # Count mentions extracted
    mentions_count = session.query(RawMention).filter(RawMention.place_id == place_id).count()

    # Check taxonomy status
    # FEATURE-001: Check both place_id (legacy) and place_ids array (multi-branch)
    taxonomy = session.query(PlaceTaxonomy).filter(
        or_(
            PlaceTaxonomy.place_id == place_id,
            PlaceTaxonomy.place_ids.any(place_id)
        )
    ).order_by(PlaceTaxonomy.created_at.desc()).first()

    taxonomy_status = taxonomy.status if taxonomy else None

    # Count analyses
    analyses_count = session.query(ReviewAnalysis).join(Review).join(Job).filter(
        Job.place_id == place_id
    ).count()

    # Determine current stage
    # Stages: scraping → extracting → clustering → approving → analyzing → complete
    total_items = 0
    approved_items = 0
    if taxonomy:
        total_items = session.query(TaxonomyProduct).filter_by(taxonomy_id=taxonomy.id).count() + \
                     session.query(TaxonomyCategory).filter_by(taxonomy_id=taxonomy.id).count()
        approved_items = session.query(TaxonomyProduct).filter_by(taxonomy_id=taxonomy.id, is_approved=True).count() + \
                        session.query(TaxonomyCategory).filter_by(taxonomy_id=taxonomy.id, is_approved=True).count()

    if reviews_count == 0:
        stage = "scraping"
        stage_progress = 0
    elif mentions_count == 0:
        stage = "extracting"
        stage_progress = 0
    elif mentions_count < reviews_count * 0.3:  # Less than 30% extraction rate
        stage = "extracting"
        stage_progress = int((mentions_count / (reviews_count * 0.3)) * 100) if reviews_count > 0 else 0
    elif taxonomy_status is None:
        stage = "clustering"
        stage_progress = 50  # Waiting for clustering to run
    elif taxonomy_status == "draft":
        stage = "approving"
        stage_progress = int((approved_items / total_items) * 100) if total_items > 0 else 0
    elif taxonomy_status == "active" and analyses_count < analyzable_reviews:
        stage = "analyzing"
        stage_progress = int((analyses_count / analyzable_reviews) * 100) if analyzable_reviews > 0 else 0
    else:
        stage = "complete"
        stage_progress = 100

    return {
        "place_id": str(place_id),
        "place_name": place.name,
        "stage": stage,
        "stage_progress": stage_progress,
        "reviews_count": reviews_count,
        "mentions_count": mentions_count,
        "analyses_count": analyses_count,
        "analyzable_reviews": analyzable_reviews,
        "taxonomy_status": taxonomy_status,
        "taxonomy_id": str(taxonomy.id) if taxonomy else None,
        "stages": {
            "scraping": {"reviews": reviews_count},
            "extracting": {"mentions": mentions_count, "reviews": reviews_count},
            "clustering": {"mentions": mentions_count},
            "approving": {"approved": approved_items, "total": total_items},
            "analyzing": {"analyzed": analyses_count, "total": analyzable_reviews},
            "complete": {
                "reviews": reviews_count,
                "mentions": mentions_count,
                "analyzed": analyses_count,
            },
        },
    }


@app.get("/api/overview")
async def get_overview(
    place_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive overview data for the client portal.
    Returns all metrics, charts, and insights for the authenticated user.
    Optionally filter by place_id to get data for a specific place.
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

        # If place_id is specified, filter to just that place (must be in user's places)
        if place_id:
            if place_id not in [str(pid) for pid in user_place_ids]:
                raise HTTPException(status_code=404, detail="Place not found or not accessible")
            user_place_ids = [place_id]

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

        # Count reviews with text (only these need analysis)
        reviews_with_text = [r for r in reviews if r.text and r.text.strip()]
        analyzable_count = len(reviews_with_text)

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

        # 5. Top topics - Calculate net sentiment per topic
        # Combine all topics and calculate their positive vs negative ratio
        all_topics = set(positive_topics.keys()) | set(negative_topics.keys())

        topic_stats = []
        for topic in all_topics:
            pos_count = positive_topics.get(topic, 0)
            neg_count = negative_topics.get(topic, 0)
            total_mentions = pos_count + neg_count
            if total_mentions == 0:
                continue

            # Net sentiment: positive ratio (0-100%)
            positive_ratio = round(pos_count / total_mentions * 100)
            net_score = pos_count - neg_count  # For sorting

            topic_stats.append({
                "topic": topic,
                "positive": pos_count,
                "negative": neg_count,
                "total": total_mentions,
                "ratio": positive_ratio,
                "net": net_score,
            })

        # What's Hot: Topics with more positive than negative mentions (ratio > 50%)
        # Sorted by total mentions (most discussed first)
        hot_topics = [t for t in topic_stats if t["ratio"] > 50]
        hot_topics.sort(key=lambda x: -x["total"])

        whats_hot = []
        for t in hot_topics[:5]:
            whats_hot.append({
                "item": t["topic"],
                "score": f"{t['ratio']}% positive",
                "mentions": t["total"],
            })

        # What's Not: Topics with more negative than positive mentions (ratio <= 50%)
        # Sorted by total mentions (most discussed first)
        cold_topics = [t for t in topic_stats if t["ratio"] <= 50]
        cold_topics.sort(key=lambda x: -x["total"])

        whats_not = []
        for t in cold_topics[:5]:
            negative_ratio = 100 - t["ratio"]
            whats_not.append({
                "item": t["topic"],
                "score": f"{negative_ratio}% negative",
                "mentions": t["total"],
            })

        # Legacy format for backwards compatibility
        top_positive = sorted(positive_topics.items(), key=lambda x: -x[1])[:5]
        top_negative = sorted(negative_topics.items(), key=lambda x: -x[1])[:5]

        # 6. Alerts
        alerts = []
        if urgent_count > 0:
            alerts.append({
                "type": "urgent",
                "icon": "⚠️",
                "message": f"{urgent_count} urgent reviews need immediate attention",
                "count": urgent_count,
            })

        # Only count reviews with text as pending (rating-only reviews don't need analysis)
        pending_analyses = max(0, analyzable_count - analyses_count)
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


@app.get("/api/insights")
async def get_insights_endpoint(
    place_id: str,
    sections: Optional[str] = None,
    days: int = 90,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get business intelligence insights for a place.

    Parameters:
    - place_id: UUID of the place (required)
    - sections: Comma-separated section names (optional, default: all)
    - days: Time window for recent data (default: 90)
    - start_date: Filter reviews from this date (YYYY-MM-DD)
    - end_date: Filter reviews up to this date (YYYY-MM-DD)
    """
    from insights import get_insights

    session = get_session()
    try:
        # Validate place access (same pattern as /api/overview)
        user_jobs = session.query(ScrapeJob).filter(ScrapeJob.user_id == current_user.id).all()
        user_place_ids = []
        for job in user_jobs:
            if job.pipeline_job_ids:
                pipeline_jobs = session.query(Job).filter(Job.id.in_(job.pipeline_job_ids)).all()
                user_place_ids.extend([str(pj.place_id) for pj in pipeline_jobs if pj.place_id])
        user_place_ids = list(set(user_place_ids))

        if place_id not in user_place_ids:
            raise HTTPException(status_code=404, detail="Place not found or not accessible")

        section_list = None
        if sections:
            section_list = [s.strip() for s in sections.split(",") if s.strip()]

        result = get_insights(
            session=session,
            place_ids=[place_id],
            sections=section_list,
            days=days,
            start_date=start_date,
            end_date=end_date,
        )
        return result
    finally:
        session.close()


@app.get("/api/reviews/search")
async def search_reviews(
    place_id: str,
    ids: Optional[str] = None,
    product_id: Optional[str] = None,
    topic: Optional[str] = None,
    sentiment: Optional[str] = None,
    author: Optional[str] = None,
    day_of_week: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Flexible review search for drill-down from insight sections.
    Supports filtering by review IDs, product, topic, sentiment, author, day of week.
    """
    session = get_session()
    try:
        # Validate place access
        user_jobs = session.query(ScrapeJob).filter(ScrapeJob.user_id == current_user.id).all()
        user_place_ids = []
        for job in user_jobs:
            if job.pipeline_job_ids:
                pipeline_jobs = session.query(Job).filter(Job.id.in_(job.pipeline_job_ids)).all()
                user_place_ids.extend([str(pj.place_id) for pj in pipeline_jobs if pj.place_id])
        user_place_ids = list(set(user_place_ids))

        if place_id not in user_place_ids:
            raise HTTPException(status_code=404, detail="Place not found or not accessible")

        # Base query
        query = (
            session.query(Review, ReviewAnalysis)
            .outerjoin(ReviewAnalysis, Review.id == ReviewAnalysis.review_id)
            .filter(Review.place_id == place_id)
        )

        # Filter by specific IDs
        if ids:
            id_list = [i.strip() for i in ids.split(",") if i.strip()]
            query = query.filter(Review.id.in_(id_list))

        # Filter by product (via RawMention)
        if product_id:
            review_ids_with_product = (
                session.query(RawMention.review_id)
                .filter(
                    RawMention.place_id == place_id,
                    or_(
                        RawMention.resolved_product_id == product_id,
                        RawMention.discovered_product_id == product_id
                    )
                )
                .distinct()
                .all()
            )
            product_review_ids = [r[0] for r in review_ids_with_product]
            query = query.filter(Review.id.in_(product_review_ids))

        # Filter by sentiment
        if sentiment:
            query = query.filter(ReviewAnalysis.sentiment == sentiment)

        # Filter by author
        if author:
            query = query.filter(Review.author == author)

        # Get total before pagination
        total = query.count()

        # Get results
        results = query.order_by(Review.created_at.desc()).offset(offset).limit(min(limit, 50)).all()

        # Post-filter by topic and day_of_week (stored as strings/arrays, not SQL-filterable easily)
        review_list = []
        for review, analysis in results:
            # Day of week filter
            if day_of_week is not None and review.review_date:
                try:
                    parts = review.review_date.split("-")
                    from datetime import date as dt_date
                    d = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
                    if d.weekday() != day_of_week:
                        continue
                except (ValueError, IndexError):
                    continue

            # Topic filter
            if topic and analysis:
                all_topics = (analysis.topics_positive or []) + (analysis.topics_negative or [])
                if topic not in all_topics:
                    continue

            analysis_data = None
            if analysis:
                analysis_data = ReviewAnalysisData(
                    sentiment=analysis.sentiment,
                    score=float(analysis.score) if analysis.score else None,
                    topics_positive=analysis.topics_positive or [],
                    topics_negative=analysis.topics_negative or [],
                    language=analysis.language,
                    urgent=analysis.urgent or False,
                    summary_ar=analysis.summary_ar,
                    summary_en=analysis.summary_en,
                    suggested_reply_ar=analysis.suggested_reply_ar,
                    needs_action=analysis.needs_action or False,
                    action_ar=analysis.action_ar,
                    action_en=analysis.action_en,
                )

            review_list.append(ReviewWithAnalysis(
                id=str(review.id),
                author=review.author,
                rating=review.rating,
                text=review.text,
                review_date=review.review_date,
                analysis=analysis_data,
            ))

        # For topic/day_of_week post-filters, total is approximate
        if topic or day_of_week is not None:
            total = len(review_list)

        return {"reviews": review_list, "total": total}
    finally:
        session.close()


@app.get("/api/sentiment-trend")
async def get_sentiment_trend(
    period: str = "7d",
    zoom: str = "day",
    place_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    topic: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get sentiment trend data with anomaly detection.

    Parameters:
    - period: 7d, 30d, 90d, 1y, all, or 'custom' (requires start_date/end_date)
    - zoom: Aggregation level - 'day', 'week', 'month', 'year'
    - place_id: Filter to specific place
    - start_date: Custom range start (YYYY-MM-DD)
    - end_date: Custom range end (YYYY-MM-DD)
    - topic: Filter by topic (service, food, drinks, etc.)
    """
    from datetime import datetime, timedelta
    from collections import defaultdict
    import statistics

    session = get_session()
    try:
        # Get user's places
        user_jobs = session.query(ScrapeJob).filter(ScrapeJob.user_id == current_user.id).all()
        user_place_ids = []
        for job in user_jobs:
            if job.pipeline_job_ids:
                pipeline_jobs = session.query(Job).filter(Job.id.in_(job.pipeline_job_ids)).all()
                user_place_ids.extend([pj.place_id for pj in pipeline_jobs if pj.place_id])
        user_place_ids = list(set(user_place_ids))

        # If place_id is specified, filter to just that place
        if place_id:
            if place_id not in [str(pid) for pid in user_place_ids]:
                raise HTTPException(status_code=404, detail="Place not found or not accessible")
            user_place_ids = [place_id]

        empty_response = {
            "data": [],
            "anomalies": [],
            "topics_in_period": [],
            "baseline": {"avg_positive_pct": 0, "avg_daily_reviews": 0}
        }

        if not user_place_ids:
            return empty_response

        # Get reviews with their analyses
        reviews = session.query(Review).filter(Review.place_id.in_(user_place_ids)).all()
        review_ids = [r.id for r in reviews]

        if not review_ids:
            return empty_response

        # Create maps
        analyses = session.query(ReviewAnalysis).filter(ReviewAnalysis.review_id.in_(review_ids)).all()
        analysis_map = {a.review_id: a for a in analyses}
        review_obj_map = {r.id: r for r in reviews}

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

        # Build review data with parsed dates and topics
        review_data = []
        all_topics = set()

        for r in reviews:
            review_date = parse_review_date(r.review_date)
            analysis = analysis_map.get(r.id)
            if review_date and analysis:
                topics_pos = analysis.topics_positive or []
                topics_neg = analysis.topics_negative or []
                all_review_topics = set(topics_pos + topics_neg)
                all_topics.update(all_review_topics)

                # Filter by topic if specified
                if topic and topic not in all_review_topics:
                    continue

                review_data.append({
                    "id": str(r.id),
                    "date": review_date,
                    "sentiment": analysis.sentiment,
                    "topics_positive": topics_pos,
                    "topics_negative": topics_neg,
                    "text": r.text[:200] if r.text else "",
                    "rating": r.rating,
                })

        if not review_data:
            return empty_response

        # Determine date range
        today = datetime.utcnow().date()

        if period == "custom" and start_date and end_date:
            try:
                range_start = datetime.strptime(start_date, "%Y-%m-%d").date()
                range_end = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        elif period == "all":
            # No date restrictions - use all data
            all_dates = [rd["date"] for rd in review_data]
            if all_dates:
                range_start = min(all_dates)
                range_end = max(all_dates)
            else:
                range_start = today
                range_end = today
        else:
            # Preset periods
            period_days = {
                "7d": 7,
                "30d": 30,
                "90d": 90,
                "1y": 365,
                "2y": 730,
                "5y": 1825,
            }
            days = period_days.get(period, 7)
            range_start = today - timedelta(days=days - 1)
            range_end = today

        trend_data = []
        reviews_by_date = defaultdict(list)

        # Group reviews by date
        for rd in review_data:
            if range_start <= rd["date"] <= range_end:
                reviews_by_date[rd["date"]].append(rd)

        # Collect topics in period
        topics_in_period = set()
        for date_reviews in reviews_by_date.values():
            for rd in date_reviews:
                topics_in_period.update(rd["topics_positive"])
                topics_in_period.update(rd["topics_negative"])

        # Aggregation based on zoom level
        def get_bucket_key(date, zoom_level):
            if zoom_level == "year":
                return date.strftime("%Y")
            elif zoom_level == "month":
                return date.strftime("%Y-%m")
            elif zoom_level == "week":
                # ISO week format
                return f"{date.year}-W{date.isocalendar()[1]:02d}"
            else:  # day
                return date.isoformat()

        def get_bucket_label(key, zoom_level):
            if zoom_level == "year":
                return key  # "2026"
            elif zoom_level == "month":
                return datetime.strptime(key, "%Y-%m").strftime("%b %Y")  # "Jan 2026"
            elif zoom_level == "week":
                return key  # "2026-W05"
            else:  # day
                try:
                    return datetime.strptime(key, "%Y-%m-%d").strftime("%b %d")  # "Jan 26"
                except:
                    return key

        # Aggregate by zoom level
        buckets = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "total": 0, "reviews": []})

        for rd in review_data:
            if range_start <= rd["date"] <= range_end:
                bucket_key = get_bucket_key(rd["date"], zoom)
                buckets[bucket_key]["total"] += 1
                buckets[bucket_key]["reviews"].append(rd)
                if rd["sentiment"] == "positive":
                    buckets[bucket_key]["positive"] += 1
                elif rd["sentiment"] == "negative":
                    buckets[bucket_key]["negative"] += 1
                else:
                    buckets[bucket_key]["neutral"] += 1

        # Fill empty buckets so bar count matches the requested range
        def generate_all_keys(start, end, zoom_level):
            keys = []
            if zoom_level == "day":
                d = start
                while d <= end:
                    keys.append(d.isoformat())
                    d += timedelta(days=1)
            elif zoom_level == "week":
                d = start
                while d <= end:
                    keys.append(f"{d.year}-W{d.isocalendar()[1]:02d}")
                    d += timedelta(days=7)
            elif zoom_level == "month":
                d = datetime(start.year, start.month, 1).date()
                while d <= end:
                    keys.append(d.strftime("%Y-%m"))
                    if d.month == 12:
                        d = datetime(d.year + 1, 1, 1).date()
                    else:
                        d = datetime(d.year, d.month + 1, 1).date()
            else:  # year
                for y in range(start.year, end.year + 1):
                    keys.append(str(y))
            return keys

        all_keys = generate_all_keys(range_start, range_end, zoom)
        for k in all_keys:
            if k not in buckets:
                buckets[k] = {"positive": 0, "negative": 0, "neutral": 0, "total": 0, "reviews": []}

        sorted_keys = sorted(buckets.keys())

        for key in sorted_keys:
            data = buckets[key]
            total = data["total"]
            trend_data.append({
                "date": key,
                "label": get_bucket_label(key, zoom),
                "positive": data["positive"],
                "negative": data["negative"],
                "neutral": data["neutral"],
                "total": total,
                "positive_pct": round(data["positive"] / total * 100) if total > 0 else 0,
                "reviews": data["reviews"],
            })

        # Calculate baseline
        total_reviews = sum(p["total"] for p in trend_data)
        positive_reviews = sum(p["positive"] for p in trend_data)
        days_with_data = sum(1 for p in trend_data if p["total"] > 0)

        baseline = {
            "avg_positive_pct": round(positive_reviews / total_reviews * 100) if total_reviews > 0 else 0,
            "avg_daily_reviews": round(total_reviews / max(days_with_data, 1), 1)
        }

        # Anomaly detection using statistical approach (2σ)
        anomalies = []
        positive_pcts = [p["positive_pct"] for p in trend_data if p["total"] > 0]

        if len(positive_pcts) >= 3:
            mean_pct = statistics.mean(positive_pcts)
            try:
                std_pct = statistics.stdev(positive_pcts)
            except statistics.StatisticsError:
                std_pct = 0

            if std_pct > 0:
                for point in trend_data:
                    if point["total"] == 0:
                        continue

                    z_score = (point["positive_pct"] - mean_pct) / std_pct

                    if abs(z_score) > 2:
                        point["is_anomaly"] = True
                        point["anomaly_type"] = "spike" if z_score > 0 else "drop"
                        magnitude = round((point["positive_pct"] - mean_pct), 1)

                        # Generate statistical reason
                        day_reviews = point.get("reviews", [])
                        topic_counts = defaultdict(lambda: {"positive": 0, "negative": 0})

                        for rd in day_reviews:
                            for t in rd.get("topics_positive", []):
                                topic_counts[t]["positive"] += 1
                            for t in rd.get("topics_negative", []):
                                topic_counts[t]["negative"] += 1

                        # Find most changed topic
                        reason_parts = []
                        if point["anomaly_type"] == "drop":
                            neg_topics = sorted(topic_counts.items(), key=lambda x: -x[1]["negative"])
                            if neg_topics and neg_topics[0][1]["negative"] > 0:
                                reason_parts.append(f"'{neg_topics[0][0]}' complaints: {neg_topics[0][1]['negative']}")
                        else:
                            pos_topics = sorted(topic_counts.items(), key=lambda x: -x[1]["positive"])
                            if pos_topics and pos_topics[0][1]["positive"] > 0:
                                reason_parts.append(f"'{pos_topics[0][0]}' praised: {pos_topics[0][1]['positive']}x")

                        reason = f"Sentiment {'dropped' if point['anomaly_type'] == 'drop' else 'spiked'} {abs(magnitude):.0f}%"
                        if reason_parts:
                            reason += f" - {', '.join(reason_parts)}"

                        point["anomaly_reason"] = reason

                        # Check for cached LLM insight
                        llm_insight = None
                        review_id_list = [rd["id"] for rd in day_reviews]

                        # Determine place_id for cache lookup (use first place if multiple)
                        cache_place_id = user_place_ids[0] if len(user_place_ids) == 1 else None

                        # Build date filter based on zoom level
                        # Insights are stored by day, but we may be viewing by month/week/year
                        date_filter = None
                        if zoom == "day":
                            date_filter = AnomalyInsight.date == point["date"]
                        elif zoom == "month":
                            # Match any day in this month (2025-12 matches 2025-12-*)
                            date_filter = AnomalyInsight.date.like(f"{point['date']}%")
                        elif zoom == "week":
                            # For week, we need to find days in this ISO week
                            # point["date"] is like "2025-W52", find all matching days
                            week_dates = [rd["date"].isoformat() for rd in day_reviews]
                            if week_dates:
                                date_filter = AnomalyInsight.date.in_(week_dates)
                            else:
                                date_filter = AnomalyInsight.date == point["date"]
                        elif zoom == "year":
                            # Match any day in this year
                            date_filter = AnomalyInsight.date.like(f"{point['date']}%")
                        else:
                            date_filter = AnomalyInsight.date == point["date"]

                        # Query for cached insight
                        query = session.query(AnomalyInsight).filter(date_filter)
                        if cache_place_id:
                            query = query.filter(AnomalyInsight.place_id == cache_place_id)
                        if topic:
                            query = query.filter(AnomalyInsight.topic == topic)
                        else:
                            query = query.filter(AnomalyInsight.topic.is_(None))

                        cached = query.first()

                        if cached:
                            llm_insight = {
                                "analysis": cached.analysis,
                                "analysis_ar": getattr(cached, 'analysis_ar', None),
                                "recommendation": cached.recommendation,
                                "recommendation_ar": getattr(cached, 'recommendation_ar', None),
                            }
                        # Note: If not cached, insight was generated when job completed
                        # No queueing here - anomaly detection runs automatically on job completion

                        anomalies.append({
                            "date": point["date"],
                            "type": point["anomaly_type"],
                            "magnitude": magnitude,
                            "reason": reason,
                            "llm_insight": llm_insight,  # Will be null if not yet generated
                            "review_ids": review_id_list
                        })

        # Remove reviews from response (too large) and prepare final data
        final_data = []
        for point in trend_data:
            final_data.append({
                "date": point["date"],
                "label": point["label"],
                "positive": point["positive"],
                "negative": point["negative"],
                "neutral": point["neutral"],
                "total": point["total"],
                "positive_pct": point["positive_pct"],
                "is_anomaly": point.get("is_anomaly", False),
                "anomaly_type": point.get("anomaly_type"),
                "anomaly_reason": point.get("anomaly_reason"),
            })

        return {
            "data": final_data,
            "anomalies": anomalies,
            "topics_in_period": sorted(list(topics_in_period)),
            "baseline": baseline
        }
    finally:
        session.close()


@app.get("/api/sentiment-trend/{date}/reviews")
async def get_date_reviews(
    date: str,
    topic: Optional[str] = None,
    sentiment: Optional[str] = None,
    place_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get reviews for a specific date/period with optional filters.

    Parameters:
    - date: Date in various formats:
        - YYYY-MM-DD for specific day
        - YYYY-MM for month
        - YYYY-Wxx for week
        - YYYY for year
    - topic: Filter by topic
    - sentiment: Filter by sentiment (positive, negative, neutral)
    - place_id: Filter by place
    """
    from datetime import datetime, timedelta

    session = get_session()
    try:
        # Parse the date - support multiple formats based on zoom level
        date_filter_type = None
        target_year = None
        target_month = None
        target_week = None
        target_date = None

        if len(date) == 10 and date[4] == '-' and date[7] == '-':
            # YYYY-MM-DD format (day zoom)
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
                date_filter_type = "day"
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format")
        elif len(date) == 7 and date[4] == '-':
            # YYYY-MM format (month zoom)
            try:
                target_year = int(date[:4])
                target_month = int(date[5:7])
                date_filter_type = "month"
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
        elif 'W' in date.upper():
            # YYYY-Wxx format (week zoom)
            try:
                parts = date.upper().split('-W')
                target_year = int(parts[0])
                target_week = int(parts[1])
                date_filter_type = "week"
            except (ValueError, IndexError):
                raise HTTPException(status_code=400, detail="Invalid week format. Use YYYY-Wxx")
        elif len(date) == 4:
            # YYYY format (year zoom)
            try:
                target_year = int(date)
                date_filter_type = "year"
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid year format. Use YYYY")
        else:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD, YYYY-MM, YYYY-Wxx, or YYYY")

        # Get user's places
        user_jobs = session.query(ScrapeJob).filter(ScrapeJob.user_id == current_user.id).all()
        user_place_ids = []
        for job in user_jobs:
            if job.pipeline_job_ids:
                pipeline_jobs = session.query(Job).filter(Job.id.in_(job.pipeline_job_ids)).all()
                user_place_ids.extend([pj.place_id for pj in pipeline_jobs if pj.place_id])
        user_place_ids = list(set(user_place_ids))

        if place_id:
            if place_id not in [str(pid) for pid in user_place_ids]:
                raise HTTPException(status_code=404, detail="Place not found or not accessible")
            user_place_ids = [place_id]

        if not user_place_ids:
            return {"reviews": [], "total": 0}

        # Get reviews
        reviews = session.query(Review).filter(Review.place_id.in_(user_place_ids)).all()
        review_ids = [r.id for r in reviews]

        if not review_ids:
            return {"reviews": [], "total": 0}

        # Get analyses
        analyses = session.query(ReviewAnalysis).filter(ReviewAnalysis.review_id.in_(review_ids)).all()
        analysis_map = {a.review_id: a for a in analyses}

        # Parse date helper
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

        # Date matching helper based on filter type
        def matches_date_filter(review_date):
            if review_date is None:
                return False
            if date_filter_type == "day":
                return review_date == target_date
            elif date_filter_type == "month":
                return review_date.year == target_year and review_date.month == target_month
            elif date_filter_type == "week":
                review_iso = review_date.isocalendar()
                return review_iso[0] == target_year and review_iso[1] == target_week
            elif date_filter_type == "year":
                return review_date.year == target_year
            return False

        # Filter and build response
        result_reviews = []
        for r in reviews:
            review_date = parse_review_date(r.review_date)
            if not matches_date_filter(review_date):
                continue

            analysis = analysis_map.get(r.id)
            if not analysis:
                continue

            # Filter by sentiment
            if sentiment and analysis.sentiment != sentiment:
                continue

            # Filter by topic
            topics_pos = analysis.topics_positive or []
            topics_neg = analysis.topics_negative or []
            all_topics = set(topics_pos + topics_neg)

            if topic and topic not in all_topics:
                continue

            # Get place name
            place = session.query(Place).filter(Place.id == r.place_id).first()
            place_name = place.name if place else "Unknown"

            result_reviews.append({
                "id": str(r.id),
                "text": r.text,
                "rating": r.rating,
                "author": r.author,
                "date": r.review_date,
                "place_name": place_name,
                "sentiment": analysis.sentiment,
                "score": float(analysis.score) if analysis.score else None,
                "topics_positive": topics_pos,
                "topics_negative": topics_neg,
                "summary_en": analysis.summary_en,
                "summary_ar": analysis.summary_ar,
                "suggested_reply_ar": analysis.suggested_reply_ar,
                "urgent": analysis.urgent,
            })

        # Sort by date (newest first), then by rating
        result_reviews.sort(key=lambda x: (x.get("date") or "", -(x.get("rating") or 0)), reverse=True)

        # Limit results to prevent huge responses (keep first 100)
        total_count = len(result_reviews)
        result_reviews = result_reviews[:100]

        return {
            "reviews": result_reviews,
            "total": total_count,
            "returned": len(result_reviews),
            "date": date,
            "date_type": date_filter_type,
            "filters": {
                "topic": topic,
                "sentiment": sentiment,
                "place_id": place_id
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
