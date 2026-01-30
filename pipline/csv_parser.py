import json
import pandas as pd
from database import Place, Review, get_session


def parse_json_field(value):
    """Parse JSON string field, return None if invalid."""
    if pd.isna(value) or value == "":
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_csv(csv_path: str) -> list[dict]:
    """Parse scraper CSV and return list of place data with reviews."""
    df = pd.read_csv(csv_path)
    places = []

    for _, row in df.iterrows():
        # Parse place metadata
        place_data = {
            "name": row.get("title"),
            "place_id": row.get("place_id"),
            "category": row.get("category"),
            "address": row.get("address"),
            "rating": float(row["review_rating"]) if pd.notna(row.get("review_rating")) else None,
            "review_count": int(row["review_count"]) if pd.notna(row.get("review_count")) else 0,
            "reviews_per_rating": parse_json_field(row.get("reviews_per_rating")),
            "metadata": {
                "link": row.get("link"),
                "website": row.get("website"),
                "phone": row.get("phone"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "open_hours": parse_json_field(row.get("open_hours")),
                "complete_address": parse_json_field(row.get("complete_address")),
            }
        }

        # Parse reviews from user_reviews JSON field
        reviews_raw = parse_json_field(row.get("user_reviews")) or []
        reviews = []
        for r in reviews_raw:
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
        return place_id, review_ids
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    # Test parsing
    places = parse_csv("../results/results.csv")
    print(f"Parsed {len(places)} places")
    for p in places:
        print(f"  - {p['name']}: {len(p['reviews'])} reviews")
