"""
Database models and session management for Nurliya Pipeline.
"""

import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Text, Boolean, DECIMAL, TIMESTAMP, ForeignKey, ARRAY, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

import bcrypt

from logging_config import get_logger
from config import DATABASE_URL

logger = get_logger(__name__, service="database")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    """User model for authentication."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    scrape_jobs = relationship("ScrapeJob", back_populates="user")

    def verify_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


class Place(Base):
    __tablename__ = "places"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255))
    place_id = Column(String(255), unique=True)
    category = Column(String(100))
    address = Column(Text)
    rating = Column(DECIMAL(2, 1))
    review_count = Column(Integer)
    reviews_per_rating = Column(JSONB)
    metadata_ = Column("metadata", JSONB)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    reviews = relationship("Review", back_populates="place")
    jobs = relationship("Job", back_populates="place")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id = Column(UUID(as_uuid=True), ForeignKey("places.id"))
    status = Column(String(50), default="pending")
    total_reviews = Column(Integer, default=0)
    processed_reviews = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    completed_at = Column(TIMESTAMP)

    place = relationship("Place", back_populates="jobs")
    reviews = relationship("Review", back_populates="job")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # Index for duplicate detection (place + author + date)
        Index('ix_reviews_duplicate_check', 'place_id', 'author', 'review_date'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id = Column(UUID(as_uuid=True), ForeignKey("places.id"))
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    author = Column(String(255))
    rating = Column(Integer)
    text = Column(Text)
    review_date = Column(String(50))
    profile_picture = Column(Text)
    images = Column(JSONB)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    place = relationship("Place", back_populates="reviews")
    job = relationship("Job", back_populates="reviews")
    analysis = relationship("ReviewAnalysis", back_populates="review", uselist=False)


class ReviewAnalysis(Base):
    __tablename__ = "review_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey("reviews.id"), unique=True)
    sentiment = Column(String(20))
    score = Column(DECIMAL(3, 2))
    topics_positive = Column(ARRAY(Text))
    topics_negative = Column(ARRAY(Text))
    language = Column(String(20))
    urgent = Column(Boolean, default=False)
    summary_ar = Column(Text)
    summary_en = Column(Text)
    suggested_reply_ar = Column(Text)
    raw_response = Column(JSONB)
    analyzed_at = Column(TIMESTAMP, default=datetime.utcnow)

    review = relationship("Review", back_populates="analysis")


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    query = Column(String(500))
    status = Column(String(50), default="pending")  # pending, scraping, processing, completed, failed
    scraper_job_id = Column(String(100))  # ID from Go scraper
    pipeline_job_ids = Column(ARRAY(UUID(as_uuid=True)))  # Multiple places per scrape
    places_found = Column(Integer, default=0)
    reviews_total = Column(Integer, default=0)
    reviews_processed = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    completed_at = Column(TIMESTAMP)
    notification_email = Column(String(255))  # User's email for completion report
    email_sent_at = Column(TIMESTAMP)  # Prevents duplicate email sends

    user = relationship("User", back_populates="scrape_jobs")


class AnomalyInsight(Base):
    """
    Cached LLM insights for sentiment anomalies.
    Generated in background by worker, not during API requests.
    """
    __tablename__ = "anomaly_insights"
    __table_args__ = (
        # Unique constraint on place + date + topic combination
        Index('ix_anomaly_insights_lookup', 'place_id', 'date', 'topic'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id = Column(UUID(as_uuid=True), ForeignKey("places.id", ondelete="CASCADE"), nullable=True)
    date = Column(String(20), nullable=False)  # YYYY-MM-DD format
    topic = Column(String(50), nullable=True)  # null means "all topics"
    anomaly_type = Column(String(20))  # 'spike' or 'drop'
    magnitude = Column(DECIMAL(5, 2))  # percentage change
    reason = Column(Text)  # Statistical reason
    analysis = Column(Text)  # LLM-generated analysis
    recommendation = Column(Text)  # LLM-generated recommendation
    review_ids = Column(ARRAY(UUID(as_uuid=True)))  # Reviews that contributed to this anomaly
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    place = relationship("Place")


class ActivityLog(Base):
    """
    Activity logs for tracking system events.
    Combines activity logs (jobs, analyses) and system logs (errors, processing).
    """
    __tablename__ = "activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(TIMESTAMP, default=datetime.utcnow, index=True)
    level = Column(String(20), default="info")  # info, warning, error, success
    category = Column(String(50), index=True)  # job, analysis, email, scraper, worker, system
    action = Column(String(100))  # job_created, review_analyzed, email_sent, etc.
    message = Column(Text)
    details = Column(JSONB)  # Additional structured data

    # Optional references
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    scrape_job_id = Column(UUID(as_uuid=True), ForeignKey("scrape_jobs.id", ondelete="SET NULL"), nullable=True)
    place_id = Column(UUID(as_uuid=True), ForeignKey("places.id", ondelete="SET NULL"), nullable=True)


# =============================================================================
# DYNAMIC TAXONOMY SYSTEM TABLES
# =============================================================================

class PlaceTaxonomy(Base):
    """
    Per-place taxonomy container.
    Each place has its own taxonomy that goes through discovery → review → active lifecycle.

    FEATURE-001: Multi-branch support
    - place_id: Primary place (backward compatibility)
    - place_ids: All places sharing this taxonomy (for multi-branch businesses)
    - scrape_job_id: Link to parent scrape job that triggered discovery
    """
    __tablename__ = "place_taxonomies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id = Column(UUID(as_uuid=True), ForeignKey("places.id", ondelete="CASCADE"), nullable=False, index=True)

    # FEATURE-001: Multi-branch shared taxonomy support
    place_ids = Column(ARRAY(UUID(as_uuid=True)))  # All places sharing this taxonomy (NULL = single place, use place_id)
    scrape_job_id = Column(UUID(as_uuid=True), ForeignKey("scrape_jobs.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(20), default="draft")  # draft, review, active
    discovered_at = Column(TIMESTAMP)
    reviews_sampled = Column(Integer, default=0)  # Number of reviews used for discovery
    entities_discovered = Column(Integer, default=0)  # Total categories + products discovered
    published_at = Column(TIMESTAMP)
    published_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    place = relationship("Place")
    scrape_job = relationship("ScrapeJob")  # FEATURE-001: Link to parent scrape
    publisher = relationship("User")
    categories = relationship("TaxonomyCategory", back_populates="taxonomy", cascade="all, delete-orphan")
    products = relationship("TaxonomyProduct", back_populates="taxonomy", cascade="all, delete-orphan")

    @property
    def all_place_ids(self):
        """
        Get all place IDs for this taxonomy (FEATURE-001 helper).

        Returns place_ids array if set, otherwise falls back to [place_id].
        Use this for queries that need to work with both single-place and
        multi-branch taxonomies.
        """
        if self.place_ids:
            return self.place_ids
        return [self.place_id] if self.place_id else []


class TaxonomyCategory(Base):
    """
    Hierarchical categories for a place's taxonomy.
    Supports main categories (parent_id=NULL) and subcategories.
    """
    __tablename__ = "taxonomy_categories"
    __table_args__ = (
        Index('ix_taxonomy_categories_taxonomy', 'taxonomy_id'),
        Index('ix_taxonomy_categories_parent', 'parent_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    taxonomy_id = Column(UUID(as_uuid=True), ForeignKey("place_taxonomies.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("taxonomy_categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False)  # Internal name (lowercase, normalized)
    display_name_en = Column(String(100))
    display_name_ar = Column(String(100))
    has_products = Column(Boolean, default=False)  # Whether this category contains products
    vector_id = Column(String(100))  # Reference to Qdrant point ID for category centroid
    # BUG-006 FIX: Store cluster centroid embedding computed during discovery
    # This preserves the semantic center of all mentions in this category
    centroid_embedding = Column(JSONB)  # List[float] - 384-dim for MiniLM

    # Approval workflow
    is_approved = Column(Boolean, default=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(TIMESTAMP)
    rejection_reason = Column(Text)

    # Analytics
    discovered_mention_count = Column(Integer, default=0)  # Frozen at discovery (for audit)
    mention_count = Column(Integer, default=0)  # Live count, updated continuously
    avg_sentiment = Column(DECIMAL(3, 2))  # 0.00 to 1.00
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    taxonomy = relationship("PlaceTaxonomy", back_populates="categories")
    parent = relationship("TaxonomyCategory", remote_side=[id], backref="children")
    approver = relationship("User")
    products = relationship("TaxonomyProduct", foreign_keys="TaxonomyProduct.assigned_category_id", back_populates="assigned_category")


class TaxonomyProduct(Base):
    """
    Products discovered from review mentions.
    Can be assigned to a category or standalone (assigned_category_id=NULL).
    """
    __tablename__ = "taxonomy_products"
    __table_args__ = (
        Index('ix_taxonomy_products_taxonomy', 'taxonomy_id'),
        Index('ix_taxonomy_products_category', 'assigned_category_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    taxonomy_id = Column(UUID(as_uuid=True), ForeignKey("place_taxonomies.id", ondelete="CASCADE"), nullable=False)
    discovered_category_id = Column(UUID(as_uuid=True), ForeignKey("taxonomy_categories.id", ondelete="SET NULL"), nullable=True)  # System suggestion
    assigned_category_id = Column(UUID(as_uuid=True), ForeignKey("taxonomy_categories.id", ondelete="SET NULL"), nullable=True)  # Human decision
    canonical_text = Column(String(200), nullable=False)  # Normalized product name
    display_name = Column(String(200))  # Human-readable name
    variants = Column(JSONB, default=list)  # Alternative spellings: ["spanish latté", "سبانش لاتيه"]
    vector_id = Column(String(100))  # Reference to Qdrant point ID

    # Approval workflow
    is_approved = Column(Boolean, default=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(TIMESTAMP)
    rejection_reason = Column(Text)

    # Analytics
    discovered_mention_count = Column(Integer, default=0)  # Frozen at discovery
    mention_count = Column(Integer, default=0)  # Live count
    avg_sentiment = Column(DECIMAL(3, 2))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    taxonomy = relationship("PlaceTaxonomy", back_populates="products")
    discovered_category = relationship("TaxonomyCategory", foreign_keys=[discovered_category_id])
    assigned_category = relationship("TaxonomyCategory", foreign_keys=[assigned_category_id], back_populates="products")
    approver = relationship("User")


class RawMention(Base):
    """
    Raw mentions extracted from reviews.
    Links to resolved products/categories once taxonomy is approved.
    """
    __tablename__ = "raw_mentions"
    __table_args__ = (
        Index('ix_raw_mentions_review', 'review_id'),
        Index('ix_raw_mentions_place', 'place_id'),
        Index('ix_raw_mentions_resolved_product', 'resolved_product_id'),
        Index('ix_raw_mentions_resolved_category', 'resolved_category_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    place_id = Column(UUID(as_uuid=True), ForeignKey("places.id", ondelete="CASCADE"), nullable=False)
    mention_text = Column(Text, nullable=False)  # Original extracted text
    mention_type = Column(String(20), nullable=False)  # 'product' or 'aspect'
    sentiment = Column(String(20))  # 'positive', 'negative', 'neutral'
    qdrant_point_id = Column(String(100))  # Reference to embedding in Qdrant

    # Resolution (populated after taxonomy approval)
    resolved_product_id = Column(UUID(as_uuid=True), ForeignKey("taxonomy_products.id", ondelete="SET NULL"), nullable=True)
    resolved_category_id = Column(UUID(as_uuid=True), ForeignKey("taxonomy_categories.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    review = relationship("Review")
    place = relationship("Place")
    resolved_product = relationship("TaxonomyProduct")
    resolved_category = relationship("TaxonomyCategory")


class TaxonomyAuditLog(Base):
    """
    Audit log for taxonomy approval workflow.
    Tracks all changes made during review process.
    """
    __tablename__ = "taxonomy_audit_logs"
    __table_args__ = (
        Index('ix_taxonomy_audit_logs_taxonomy', 'taxonomy_id'),
        Index('ix_taxonomy_audit_logs_user', 'user_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    taxonomy_id = Column(UUID(as_uuid=True), ForeignKey("place_taxonomies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(50), nullable=False)  # approve, reject, move, rename, merge, create, delete, publish
    entity_type = Column(String(20), nullable=False)  # 'category', 'product', 'taxonomy'
    entity_id = Column(UUID(as_uuid=True))  # ID of the affected entity
    old_value = Column(JSONB)  # Previous state
    new_value = Column(JSONB)  # New state
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    taxonomy = relationship("PlaceTaxonomy")
    user = relationship("User")


def get_session():
    return SessionLocal()


def create_tables():
    """Create all database tables."""
    try:
        Base.metadata.create_all(engine)
        logger.info("Database tables created/verified successfully")
    except Exception as e:
        logger.error("Failed to create database tables", exc_info=True)
        raise


if __name__ == "__main__":
    create_tables()
