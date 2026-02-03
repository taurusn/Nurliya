"""
Vector store client for Qdrant with fallback logic.
Handles embedding storage, similarity search, and entity resolution.
"""

import uuid
from typing import List, Optional, Dict, Any, Tuple, Union
from dataclasses import dataclass
from enum import Enum

from logging_config import get_logger
from config import QDRANT_URL, QDRANT_API_KEY, EMBEDDING_DIMENSION

logger = get_logger(__name__, service="vector_store")

# Lazy load Qdrant client
_qdrant_client = None
_qdrant_available = None

# Collection names
MENTIONS_COLLECTION = "mentions"
PRODUCTS_COLLECTION = "products"

# Default similarity threshold for entity resolution
DEFAULT_SIMILARITY_THRESHOLD = 0.85

# Lower threshold for matching mentions to approved products (catches variants)
PRODUCT_MATCH_THRESHOLD = 0.80


class MentionType(str, Enum):
    PRODUCT = "product"
    ASPECT = "aspect"


@dataclass
class VectorPayload:
    """Payload structure for vectors in Qdrant."""
    text: str
    place_id: str
    mention_type: str
    is_canonical: bool = False
    canonical_id: Optional[str] = None
    sentiment_sum: float = 0.0
    mention_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "place_id": self.place_id,
            "mention_type": self.mention_type,
            "is_canonical": self.is_canonical,
            "canonical_id": self.canonical_id,
            "sentiment_sum": self.sentiment_sum,
            "mention_count": self.mention_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorPayload":
        return cls(
            text=data.get("text", ""),
            place_id=data.get("place_id", ""),
            mention_type=data.get("mention_type", "product"),
            is_canonical=data.get("is_canonical", False),
            canonical_id=data.get("canonical_id"),
            sentiment_sum=data.get("sentiment_sum", 0.0),
            mention_count=data.get("mention_count", 0),
        )


@dataclass
class TaxonomyVectorPayload:
    """Payload for approved taxonomy items in PRODUCTS_COLLECTION."""
    text: str                          # canonical_text or category name
    place_id: str
    taxonomy_id: str
    entity_type: str                   # 'product' or 'category'
    entity_id: str                     # UUID of product/category
    category_id: Optional[str] = None  # Parent category for products

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "place_id": self.place_id,
            "taxonomy_id": self.taxonomy_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "category_id": self.category_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaxonomyVectorPayload":
        return cls(
            text=data.get("text", ""),
            place_id=data.get("place_id", ""),
            taxonomy_id=data.get("taxonomy_id", ""),
            entity_type=data.get("entity_type", "product"),
            entity_id=data.get("entity_id", ""),
            category_id=data.get("category_id"),
        )


@dataclass
class SearchResult:
    """Result from similarity search."""
    id: str
    score: float
    payload: Union[VectorPayload, TaxonomyVectorPayload]


def _get_client():
    """Lazy load Qdrant client with connection handling."""
    global _qdrant_client, _qdrant_available

    if _qdrant_available is False:
        return None

    if _qdrant_client is not None:
        return _qdrant_client

    try:
        from qdrant_client import QdrantClient

        # Parse URL for host/port
        url = QDRANT_URL.rstrip('/')

        if QDRANT_API_KEY:
            _qdrant_client = QdrantClient(url=url, api_key=QDRANT_API_KEY)
        else:
            _qdrant_client = QdrantClient(url=url)

        # Test connection
        _qdrant_client.get_collections()
        _qdrant_available = True
        logger.info(f"Connected to Qdrant at {url}")
        return _qdrant_client

    except ImportError:
        logger.error("qdrant-client not installed. Run: pip install qdrant-client")
        _qdrant_available = False
        return None
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        _qdrant_available = False
        return None


def is_available() -> bool:
    """Check if Qdrant is available."""
    return _get_client() is not None


def reset_connection():
    """Reset client connection (useful after Qdrant restart)."""
    global _qdrant_client, _qdrant_available
    _qdrant_client = None
    _qdrant_available = None
    logger.info("Qdrant connection reset")


def ensure_collection(collection_name: str, dimension: int = EMBEDDING_DIMENSION) -> bool:
    """
    Ensure a collection exists, creating it if necessary.

    Args:
        collection_name: Name of the collection
        dimension: Vector dimension (default: from config)

    Returns:
        True if collection exists or was created successfully
    """
    client = _get_client()
    if client is None:
        return False

    try:
        from qdrant_client.http.models import Distance, VectorParams

        collections = client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)

        if not exists:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created collection '{collection_name}' with dimension {dimension}")

        return True
    except Exception as e:
        logger.error(f"Failed to ensure collection '{collection_name}': {e}")
        return False


def upsert_vector(
    collection_name: str,
    vector_id: str,
    vector: List[float],
    payload: VectorPayload,
) -> bool:
    """
    Insert or update a vector in the collection.

    Args:
        collection_name: Target collection
        vector_id: Unique ID for the vector
        vector: Embedding vector
        payload: Associated payload data

    Returns:
        True if successful
    """
    client = _get_client()
    if client is None:
        logger.warning(f"Qdrant unavailable, cannot upsert vector {vector_id}")
        return False

    try:
        from qdrant_client.http.models import PointStruct

        client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=vector_id,
                    vector=vector,
                    payload=payload.to_dict(),
                )
            ],
        )
        return True
    except Exception as e:
        logger.error(f"Failed to upsert vector {vector_id}: {e}")
        return False


def upsert_vectors_batch(
    collection_name: str,
    vectors: List[Tuple[str, List[float], VectorPayload]],
    batch_size: int = 100,
) -> int:
    """
    Batch insert/update vectors.

    Args:
        collection_name: Target collection
        vectors: List of (id, vector, payload) tuples
        batch_size: Number of vectors per batch

    Returns:
        Number of successfully upserted vectors
    """
    client = _get_client()
    if client is None:
        logger.warning("Qdrant unavailable, cannot upsert batch")
        return 0

    try:
        from qdrant_client.http.models import PointStruct

        total_upserted = 0
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            points = [
                PointStruct(
                    id=vid,
                    vector=vec,
                    payload=payload.to_dict(),
                )
                for vid, vec, payload in batch
            ]

            client.upsert(collection_name=collection_name, points=points)
            total_upserted += len(batch)

        logger.debug(f"Upserted {total_upserted} vectors to '{collection_name}'")
        return total_upserted
    except Exception as e:
        logger.error(f"Failed to upsert batch: {e}")
        return 0


def increment_mention_count(
    collection_name: str,
    vector_id: str,
    sentiment_delta: float = 0.0,
) -> bool:
    """
    Increment mention_count and update sentiment_sum for an existing vector.

    Args:
        collection_name: Target collection
        vector_id: ID of the vector to update
        sentiment_delta: Value to add to sentiment_sum (+1, -1, or 0)

    Returns:
        True if update succeeded, False otherwise
    """
    client = _get_client()
    if client is None:
        return False

    try:
        # Retrieve current point
        points = client.retrieve(
            collection_name=collection_name,
            ids=[vector_id],
            with_payload=True,
        )

        if not points:
            logger.warning(f"Vector {vector_id} not found for increment")
            return False

        current_payload = points[0].payload
        new_count = current_payload.get("mention_count", 1) + 1
        new_sentiment_sum = current_payload.get("sentiment_sum", 0.0) + sentiment_delta

        # Update payload
        client.set_payload(
            collection_name=collection_name,
            payload={
                "mention_count": new_count,
                "sentiment_sum": new_sentiment_sum,
            },
            points=[vector_id],
        )

        return True
    except Exception as e:
        logger.error(f"Failed to increment mention count for {vector_id}: {e}")
        return False


def search_similar(
    collection_name: str,
    query_vector: List[float],
    place_id: Optional[str] = None,
    mention_type: Optional[str] = None,
    limit: int = 5,
    score_threshold: float = 0.0,
) -> List[SearchResult]:
    """
    Search for similar vectors.

    Args:
        collection_name: Collection to search
        query_vector: Query embedding
        place_id: Filter by place (optional)
        mention_type: Filter by mention type (optional)
        limit: Maximum results to return
        score_threshold: Minimum similarity score

    Returns:
        List of SearchResult objects
    """
    client = _get_client()
    if client is None:
        logger.warning("Qdrant unavailable, returning empty results")
        return []

    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        # Build filter conditions
        conditions = []
        if place_id:
            conditions.append(
                FieldCondition(key="place_id", match=MatchValue(value=place_id))
            )
        if mention_type:
            conditions.append(
                FieldCondition(key="mention_type", match=MatchValue(value=mention_type))
            )

        query_filter = Filter(must=conditions) if conditions else None

        results = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                id=str(r.id),
                score=r.score,
                payload=VectorPayload.from_dict(r.payload),
            )
            for r in results.points
        ]
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


def find_similar_mention(
    text_embedding: List[float],
    place_id: str,
    mention_type: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Optional[SearchResult]:
    """
    Find if a similar mention already exists for entity resolution.

    Args:
        text_embedding: Embedding of the mention text
        place_id: Place to search within
        mention_type: Type of mention ('product' or 'aspect')
        threshold: Similarity threshold for matching

    Returns:
        Best matching result if above threshold, else None
    """
    results = search_similar(
        collection_name=MENTIONS_COLLECTION,
        query_vector=text_embedding,
        place_id=place_id,
        mention_type=mention_type,
        limit=1,
        score_threshold=threshold,
    )

    if results:
        logger.debug(f"Found similar mention with score {results[0].score:.3f}")
        return results[0]

    return None


def find_matching_product(
    text_embedding: List[float],
    place_id: str,
    mention_type: str,
    threshold: float = PRODUCT_MATCH_THRESHOLD,
) -> Optional[SearchResult]:
    """
    Find matching approved product/category for a mention.

    Args:
        text_embedding: Embedding of the mention text
        place_id: Place to search within
        mention_type: 'product' or 'aspect'
        threshold: Similarity threshold (default 0.80)

    Returns:
        Best matching result if above threshold, else None
    """
    entity_type = "product" if mention_type == "product" else "category"

    client = _get_client()
    if client is None:
        return None

    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        results = client.query_points(
            collection_name=PRODUCTS_COLLECTION,
            query=text_embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(key="place_id", match=MatchValue(value=place_id)),
                    FieldCondition(key="entity_type", match=MatchValue(value=entity_type)),
                ]
            ),
            limit=1,
            score_threshold=threshold,
        )

        if results.points:
            point = results.points[0]
            return SearchResult(
                id=str(point.id),
                score=point.score,
                payload=TaxonomyVectorPayload.from_dict(point.payload),
            )

        return None
    except Exception as e:
        logger.error(f"Failed to find matching product: {e}")
        return None


def index_approved_taxonomy(
    place_id: str,
    taxonomy_id: str,
    products: List[Tuple[str, str, List[float], str, Optional[str]]],
    categories: List[Tuple[str, str, List[float]]],
) -> int:
    """
    Index approved products and categories in PRODUCTS_COLLECTION.

    BUG-008 FIX: Now indexes each variant as a separate point for better cross-lingual matching.

    Args:
        place_id: Place UUID
        taxonomy_id: Taxonomy UUID
        products: List of (point_id, text, embedding, entity_id, category_id)
                  - point_id: Unique ID for this vector point
                  - text: The text for this specific variant
                  - embedding: Vector embedding
                  - entity_id: Product UUID (same for all variants of a product)
                  - category_id: Category UUID or None
        categories: List of (category_id, name, embedding)

    Returns:
        Number of indexed vectors
    """
    client = _get_client()
    if client is None:
        logger.warning("Qdrant unavailable, cannot index taxonomy")
        return 0

    try:
        from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue, FilterSelector

        # Clear existing vectors for this place in PRODUCTS_COLLECTION
        place_filter = Filter(
            must=[FieldCondition(key="place_id", match=MatchValue(value=place_id))]
        )
        client.delete(
            collection_name=PRODUCTS_COLLECTION,
            points_selector=FilterSelector(filter=place_filter),
        )

        points = []

        # Index products (BUG-008 FIX: each variant is a separate point)
        for point_id, text, embedding, entity_id, category_id in products:
            payload = TaxonomyVectorPayload(
                text=text,
                place_id=place_id,
                taxonomy_id=taxonomy_id,
                entity_type="product",
                entity_id=entity_id,  # Same entity_id for all variants of a product
                category_id=category_id,
            )
            points.append(PointStruct(
                id=point_id,  # Unique ID per variant
                vector=embedding,
                payload=payload.to_dict(),
            ))

        # Index categories (for aspect resolution)
        for category_id, name, embedding in categories:
            payload = TaxonomyVectorPayload(
                text=name,
                place_id=place_id,
                taxonomy_id=taxonomy_id,
                entity_type="category",
                entity_id=category_id,
                category_id=None,
            )
            points.append(PointStruct(
                id=category_id,
                vector=embedding,
                payload=payload.to_dict(),
            ))

        if points:
            client.upsert(collection_name=PRODUCTS_COLLECTION, points=points)

        logger.info(f"Indexed {len(points)} taxonomy items for place {place_id}")
        return len(points)
    except Exception as e:
        logger.error(f"Failed to index taxonomy: {e}")
        return 0


def get_active_taxonomy_id(place_id: str) -> Optional[str]:
    """
    Check if an active taxonomy exists for a place.

    Returns:
        taxonomy_id if active taxonomy exists, None otherwise
    """
    client = _get_client()
    if client is None:
        return None

    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue, ScrollRequest

        place_filter = Filter(
            must=[FieldCondition(key="place_id", match=MatchValue(value=place_id))]
        )

        # Use scroll to check if any vectors exist (avoids zero vector issue)
        result = client.scroll(
            collection_name=PRODUCTS_COLLECTION,
            scroll_filter=place_filter,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )

        points, _ = result
        if points:
            return points[0].payload.get("taxonomy_id")

        return None
    except Exception as e:
        logger.debug(f"No active taxonomy for place {place_id}: {e}")
        return None


def delete_vector(collection_name: str, vector_id: str) -> bool:
    """Delete a vector by ID."""
    client = _get_client()
    if client is None:
        return False

    try:
        from qdrant_client.http.models import PointIdsList

        client.delete(
            collection_name=collection_name,
            points_selector=PointIdsList(points=[vector_id]),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to delete vector {vector_id}: {e}")
        return False


def delete_by_place(collection_name: str, place_id: str) -> int:
    """
    Delete all vectors for a place.

    Args:
        collection_name: Target collection
        place_id: Place ID to delete vectors for

    Returns:
        Number of deleted vectors (estimated)
    """
    client = _get_client()
    if client is None:
        return 0

    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue, FilterSelector

        place_filter = Filter(
            must=[FieldCondition(key="place_id", match=MatchValue(value=place_id))]
        )

        # First count existing vectors
        count_result = client.count(
            collection_name=collection_name,
            count_filter=place_filter,
        )
        count = count_result.count

        # Delete by filter using FilterSelector
        client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(filter=place_filter),
        )

        logger.info(f"Deleted {count} vectors for place {place_id}")
        return count
    except Exception as e:
        logger.error(f"Failed to delete vectors for place {place_id}: {e}")
        return 0


def get_collection_stats(collection_name: str) -> Optional[Dict[str, Any]]:
    """Get collection statistics."""
    client = _get_client()
    if client is None:
        return None

    try:
        info = client.get_collection(collection_name)
        return {
            "name": collection_name,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status.value,
        }
    except Exception as e:
        logger.error(f"Failed to get stats for '{collection_name}': {e}")
        return None


def scroll_all_vectors(
    collection_name: str,
    place_id: str,
    mention_type: Optional[str] = None,
    is_canonical: bool = True,
    batch_size: int = 100,
) -> List[Tuple[str, List[float], VectorPayload]]:
    """
    Retrieve all vectors for a place using Qdrant scroll API.

    Args:
        collection_name: Collection to scroll
        place_id: Filter by place_id
        mention_type: Optional filter ('product' or 'aspect')
        is_canonical: Only retrieve canonical mentions (default: True)
        batch_size: Points per scroll request

    Returns:
        List of (vector_id, embedding, payload) tuples
    """
    client = _get_client()
    if client is None:
        logger.warning("Qdrant unavailable, returning empty results")
        return []

    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        # Build filter conditions
        conditions = [
            FieldCondition(key="place_id", match=MatchValue(value=place_id))
        ]
        if mention_type:
            conditions.append(
                FieldCondition(key="mention_type", match=MatchValue(value=mention_type))
            )
        if is_canonical:
            conditions.append(
                FieldCondition(key="is_canonical", match=MatchValue(value=True))
            )

        scroll_filter = Filter(must=conditions)

        all_points = []
        offset = None

        while True:
            points, next_offset = client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                limit=batch_size,
                with_vectors=True,
                with_payload=True,
                offset=offset,
            )

            for point in points:
                all_points.append((
                    str(point.id),
                    point.vector,
                    VectorPayload.from_dict(point.payload),
                ))

            if next_offset is None:
                break
            offset = next_offset

        logger.debug(f"Scrolled {len(all_points)} vectors for place {place_id}")
        return all_points

    except Exception as e:
        logger.error(f"Failed to scroll vectors for place {place_id}: {e}")
        return []


def count_vectors(
    collection_name: str,
    place_id: str,
    mention_type: Optional[str] = None,
    is_canonical: bool = True,
) -> int:
    """
    Count vectors matching filter criteria.

    Args:
        collection_name: Collection to count in
        place_id: Filter by place_id
        mention_type: Optional filter ('product' or 'aspect')
        is_canonical: Only count canonical mentions (default: True)

    Returns:
        Number of matching vectors
    """
    client = _get_client()
    if client is None:
        return 0

    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        # Build filter conditions
        conditions = [
            FieldCondition(key="place_id", match=MatchValue(value=place_id))
        ]
        if mention_type:
            conditions.append(
                FieldCondition(key="mention_type", match=MatchValue(value=mention_type))
            )
        if is_canonical:
            conditions.append(
                FieldCondition(key="is_canonical", match=MatchValue(value=True))
            )

        count_filter = Filter(must=conditions)

        result = client.count(
            collection_name=collection_name,
            count_filter=count_filter,
        )

        return result.count

    except Exception as e:
        logger.error(f"Failed to count vectors for place {place_id}: {e}")
        return 0


def initialize_collections() -> bool:
    """
    Initialize all required collections for the taxonomy system.

    Returns:
        True if all collections are ready
    """
    if not is_available():
        logger.warning("Qdrant not available, skipping collection initialization")
        return False

    success = True
    for collection_name in [MENTIONS_COLLECTION, PRODUCTS_COLLECTION]:
        if not ensure_collection(collection_name):
            success = False

    # Create payload indexes for efficient filtering on PRODUCTS_COLLECTION
    if success:
        _create_payload_indexes()

    if success:
        logger.info("All Qdrant collections initialized")
    else:
        logger.error("Some collections failed to initialize")

    return success


def _create_payload_indexes():
    """Create payload indexes for efficient filtering."""
    client = _get_client()
    if client is None:
        return

    try:
        from qdrant_client.http.models import PayloadSchemaType

        # Index place_id and entity_type on PRODUCTS_COLLECTION for fast filtering
        for field in ["place_id", "entity_type", "taxonomy_id"]:
            try:
                client.create_payload_index(
                    collection_name=PRODUCTS_COLLECTION,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.debug(f"Created payload index for {PRODUCTS_COLLECTION}.{field}")
            except Exception as e:
                # Index may already exist
                if "already exists" not in str(e).lower():
                    logger.debug(f"Payload index {field} may already exist: {e}")

        # Index place_id and mention_type on MENTIONS_COLLECTION
        for field in ["place_id", "mention_type"]:
            try:
                client.create_payload_index(
                    collection_name=MENTIONS_COLLECTION,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.debug(f"Created payload index for {MENTIONS_COLLECTION}.{field}")
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.debug(f"Payload index {field} may already exist: {e}")

    except Exception as e:
        logger.warning(f"Failed to create some payload indexes: {e}")


# Fallback/retry queue for when Qdrant is unavailable
_pending_operations = []
MAX_PENDING_OPERATIONS = 1000


def queue_for_retry(operation: str, args: tuple, kwargs: dict):
    """
    Queue an operation for retry when Qdrant becomes available.

    Args:
        operation: Operation name ('upsert', 'delete', etc.)
        args: Positional arguments
        kwargs: Keyword arguments
    """
    global _pending_operations

    if len(_pending_operations) >= MAX_PENDING_OPERATIONS:
        logger.warning(f"Pending operations queue full ({MAX_PENDING_OPERATIONS}), dropping oldest")
        _pending_operations.pop(0)

    _pending_operations.append({
        "operation": operation,
        "args": args,
        "kwargs": kwargs,
    })
    logger.debug(f"Queued operation '{operation}' for retry (queue size: {len(_pending_operations)})")


def process_retry_queue() -> int:
    """
    Process pending operations from the retry queue.

    Returns:
        Number of successfully processed operations
    """
    global _pending_operations

    if not _pending_operations:
        return 0

    if not is_available():
        logger.warning("Qdrant still unavailable, cannot process retry queue")
        return 0

    processed = 0
    remaining = []

    for op in _pending_operations:
        try:
            operation = op["operation"]
            args = op["args"]
            kwargs = op["kwargs"]

            if operation == "upsert":
                if upsert_vector(*args, **kwargs):
                    processed += 1
                else:
                    remaining.append(op)
            elif operation == "delete":
                if delete_vector(*args, **kwargs):
                    processed += 1
                else:
                    remaining.append(op)
            else:
                logger.warning(f"Unknown retry operation: {operation}")
        except Exception as e:
            logger.error(f"Failed to process retry operation: {e}")
            remaining.append(op)

    _pending_operations = remaining
    logger.info(f"Processed {processed} retry operations, {len(remaining)} remaining")
    return processed


def get_pending_count() -> int:
    """Get number of pending retry operations."""
    return len(_pending_operations)


if __name__ == "__main__":
    # Test connection and collection setup
    print(f"Qdrant URL: {QDRANT_URL}")
    print(f"Available: {is_available()}")

    if is_available():
        print("\nInitializing collections...")
        initialize_collections()

        for collection in [MENTIONS_COLLECTION, PRODUCTS_COLLECTION]:
            stats = get_collection_stats(collection)
            if stats:
                print(f"  {collection}: {stats['vectors_count']} vectors")

        # Test upsert and search
        print("\nTesting upsert and search...")
        test_id = str(uuid.uuid4())
        test_vector = [0.1] * EMBEDDING_DIMENSION
        test_payload = VectorPayload(
            text="test product",
            place_id="test-place",
            mention_type="product",
        )

        if upsert_vector(MENTIONS_COLLECTION, test_id, test_vector, test_payload):
            print(f"  Upserted test vector: {test_id}")

            results = search_similar(
                MENTIONS_COLLECTION,
                test_vector,
                place_id="test-place",
                limit=1,
            )
            if results:
                print(f"  Search result: score={results[0].score:.3f}, text='{results[0].payload.text}'")

            # Cleanup
            delete_vector(MENTIONS_COLLECTION, test_id)
            print("  Cleaned up test vector")
    else:
        print("\nQdrant not available - ensure it's running")
