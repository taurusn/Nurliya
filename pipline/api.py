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
from sqlalchemy import func, text, case

from logging_config import get_logger
import embedding_client
import vector_store
from database import (
    Place, Review, ReviewAnalysis, Job, ScrapeJob, ActivityLog, User, AnomalyInsight,
    PlaceTaxonomy, TaxonomyCategory, TaxonomyProduct, RawMention, TaxonomyAuditLog,
    get_session, create_tables
)
from datetime import datetime
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
    action: str = Field(..., description="Action: approve, reject, move, add_variant")
    rejection_reason: Optional[str] = Field(None, description="Required if action=reject")
    assigned_category_id: Optional[UUID] = Field(None, description="Category ID if action=move (None=standalone)")
    variant: Optional[str] = Field(None, description="Variant text if action=add_variant")


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
                            # Use product_id for canonical, product_id_variant_{i} for variants
                            point_id = product_id if i == 0 else f"{product_id}_v{i}"
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
                category_totals[category_id]['sentiment_sum'] += (avg_sent * count)

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

        # Build response message
        message = f"Taxonomy published. {indexed_count} items indexed, "
        message += f"{products_resolved} product mentions and {categories_resolved} category mentions resolved."
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

        # Sort buckets chronologically
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
                                "recommendation": cached.recommendation
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
