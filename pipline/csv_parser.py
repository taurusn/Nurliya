"""
CSV parser for Google Maps Scraper output.
Parses place data and reviews from scraper CSV files.
"""

import json
import math
import pandas as pd

from logging_config import get_logger
from database import Place, Review, get_session

logger = get_logger(__name__, service="csv_parser")


def clean_value(value):
    """Clean pandas NaN values to None for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    # Handle scalar pd.isna check (avoid array ambiguity)
    try:
        if pd.isna(value):
            return None
    except ValueError:
        # Value is an array - return as-is
        pass
    return value


def clean_dict(d):
    """Recursively clean NaN values from a dictionary."""
    if d is None:
        return None
    return {k: clean_value(v) if not isinstance(v, dict) else clean_dict(v) for k, v in d.items()}


def parse_json_field(value):
    """Parse JSON string field, return None if invalid."""
    try:
        if pd.isna(value) or value == "":
            return None
    except ValueError:
        # Value is an array - not a JSON field
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_csv(csv_path: str) -> list[dict]:
    """Parse scraper CSV and return list of place data with reviews."""
    logger.info("Parsing CSV file", extra={"extra_data": {"path": csv_path}})
    df = pd.read_csv(csv_path)
    places = []

    for _, row in df.iterrows():
        # Parse place metadata
        place_data = {
            "name": clean_value(row.get("title")),
            "place_id": clean_value(row.get("place_id")),
            "category": clean_value(row.get("category")),
            "address": clean_value(row.get("address")),
            "rating": float(row["review_rating"]) if pd.notna(row.get("review_rating")) else None,
            "review_count": int(row["review_count"]) if pd.notna(row.get("review_count")) else 0,
            "reviews_per_rating": parse_json_field(row.get("reviews_per_rating")),
            "metadata": clean_dict({
                "link": row.get("link"),
                "website": row.get("website"),
                "phone": row.get("phone"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "open_hours": parse_json_field(row.get("open_hours")),
                "complete_address": parse_json_field(row.get("complete_address")),
            })
        }

        # Parse reviews from user_reviews and user_reviews_extended JSON fields
        reviews_raw = parse_json_field(row.get("user_reviews")) or []
        reviews_extended = parse_json_field(row.get("user_reviews_extended")) or []
        # Combine both sources (extended has more reviews when extra_reviews is enabled)
        all_reviews_raw = reviews_raw + reviews_extended
        reviews = []
        for r in all_reviews_raw:
            reviews.append({
                "author": r.get("Name"),
                "rating": r.get("Rating"),
                "text": r.get("Description"),
                "review_date": r.get("When"),
                "profile_picture": r.get("ProfilePicture"),
                "images": r.get("Images"),
            })

        place_data["reviews"] = reviews
        places.append(place_data)

    logger.info(
        "CSV parsing complete",
        extra={"extra_data": {
            "path": csv_path,
            "places_count": len(places),
            "total_reviews": sum(len(p["reviews"]) for p in places)
        }}
    )
    return places


def save_place_and_reviews(place_data: dict, job_id: str = None) -> tuple:
    """Save place and reviews to database. Returns (place_id, review_ids)."""
    session = get_session()
    try:
        # Upsert place
        place = session.query(Place).filter_by(place_id=place_data["place_id"]).first()
        if not place:
            place = Place(
                name=place_data["name"],
                place_id=place_data["place_id"],
                category=place_data["category"],
                address=place_data["address"],
                rating=place_data["rating"],
                review_count=place_data["review_count"],
                reviews_per_rating=place_data["reviews_per_rating"],
                metadata_=place_data["metadata"],
            )
            session.add(place)
            session.flush()
            logger.debug("Created new place", extra={"extra_data": {"name": place_data["name"], "place_id": place_data["place_id"]}})

        place_id = str(place.id)

        # Insert reviews
        review_ids = []
        for r in place_data["reviews"]:
            review = Review(
                place_id=place.id,
                job_id=job_id,
                author=r["author"],
                rating=r["rating"],
                text=r["text"],
                review_date=r["review_date"],
                profile_picture=r["profile_picture"],
                images=r["images"],
            )
            session.add(review)
            session.flush()
            review_ids.append(str(review.id))

        session.commit()
        logger.info(
            "Saved place and reviews",
            extra={"extra_data": {"place_name": place_data["name"], "reviews_count": len(review_ids)}}
        )
        return place_id, review_ids
    except Exception as e:
        session.rollback()
        logger.error("Failed to save place and reviews", extra={"extra_data": {"place_name": place_data.get("name")}}, exc_info=True)
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    # Test parsing
    places = parse_csv("../results/results.csv")
    for p in places:
        logger.info(f"Parsed: {p['name']}", extra={"extra_data": {"reviews_count": len(p['reviews'])}})
