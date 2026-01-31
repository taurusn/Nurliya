"""
Database models and session management for Nurliya Pipeline.
"""

import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Text, Boolean, DECIMAL, TIMESTAMP, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from logging_config import get_logger
from config import DATABASE_URL

logger = get_logger(__name__, service="database")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


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
