# Phase 4: Taxonomy Resolution - Full Lifecycle

## Overview

Implement proper vector-based resolution for the complete review lifecycle.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TAXONOMY LIFECYCLE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Phase 1-2: DISCOVERY                                                   │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐    ┌─────────────┐       │
│  │ Reviews │───▶│ Extract  │───▶│ Cluster   │───▶│ Draft       │       │
│  │ arrive  │    │ Mentions │    │ (HDBSCAN) │    │ Taxonomy    │       │
│  └─────────┘    └──────────┘    └───────────┘    └─────────────┘       │
│                                                          │              │
│  Phase 3: APPROVAL                                       ▼              │
│                                              ┌─────────────────────┐    │
│                                              │ OS Reviews/Edits    │    │
│                                              │ Approves/Rejects    │    │
│                                              └──────────┬──────────┘    │
│                                                         │               │
│  Phase 4: PUBLISH                                       ▼               │
│                                              ┌─────────────────────┐    │
│                                              │ PUBLISH             │    │
│                                              │ • Index in Qdrant   │    │
│                                              │ • Resolve existing  │    │
│                                              │ • Aggregate stats   │    │
│                                              └──────────┬──────────┘    │
│                                                         │               │
│  Phase 5: CONTINUOUS                                    ▼               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    ACTIVE TAXONOMY LOOP                          │   │
│  │  ┌───────────┐    ┌──────────────┐    ┌────────────────────┐    │   │
│  │  │ NEW       │───▶│ Extract &    │───▶│ Resolve to         │    │   │
│  │  │ Review    │    │ Embed        │    │ approved products  │    │   │
│  │  └───────────┘    └──────────────┘    └─────────┬──────────┘    │   │
│  │                                                  │               │   │
│  │       ┌──────────────────────────────────────────┴───────────┐  │   │
│  │       ▼                                                      ▼  │   │
│  │  ┌─────────────┐                            ┌─────────────────┐ │   │
│  │  │ MATCHED     │                            │ UNMATCHED       │ │   │
│  │  │ • Set IDs   │                            │ • Trigger re-   │ │   │
│  │  │ • Update    │                            │   discovery if  │ │   │
│  │  │   stats     │                            │   50+ unmatched │ │   │
│  │  └─────────────┘                            └─────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Current Gaps Being Fixed

| Gap | Impact |
|-----|--------|
| Publish uses exact text matching only | Misses spelling variants, cross-lingual |
| PRODUCTS_COLLECTION never populated | Vector search against approved items impossible |
| resolved_category_id never populated | Aspects not tracked |
| Future reviews not matched | New reviews have NULL resolution |
| mention_count/avg_sentiment not updated | Analytics stale after discovery |

---

## Step 1: Database Schema Change

**File:** `pipline/database.py` (line ~234)

Add `vector_id` column to `TaxonomyCategory`:

```python
class TaxonomyCategory(Base):
    # ... existing fields ...
    has_products = Column(Boolean, default=False)
    vector_id = Column(String(100))  # NEW: Reference to Qdrant point ID

    # Approval workflow
    is_approved = Column(Boolean, default=False)
    # ...
```

**Migration SQL:**
```sql
ALTER TABLE taxonomy_categories ADD COLUMN vector_id VARCHAR(100);
```

---

## Step 2: Vector Store Functions

**File:** `pipline/vector_store.py`

### 2.1 Add Constant (after line 25)

```python
PRODUCT_MATCH_THRESHOLD = 0.80  # Lower than 0.85 to catch variants
```

### 2.2 Add TaxonomyVectorPayload Dataclass (after line 65)

```python
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
```

### 2.3 Add New Functions

#### find_matching_product()

```python
def find_matching_product(
    text_embedding: List[float],
    place_id: str,
    mention_type: str,
    threshold: float = PRODUCT_MATCH_THRESHOLD,
) -> Optional[ScoredPoint]:
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
            point.payload = TaxonomyVectorPayload.from_dict(point.payload)
            return point

        return None
    except Exception as e:
        logger.error(f"Failed to find matching product: {e}")
        return None
```

#### index_approved_taxonomy()

```python
def index_approved_taxonomy(
    place_id: str,
    taxonomy_id: str,
    products: List[Tuple[str, str, List[float], Optional[str]]],
    categories: List[Tuple[str, str, List[float]]],
) -> int:
    """
    Index approved products and categories in PRODUCTS_COLLECTION.

    Args:
        place_id: Place UUID
        taxonomy_id: Taxonomy UUID
        products: List of (product_id, canonical_text, embedding, category_id)
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

        # Clear existing vectors for this place
        place_filter = Filter(
            must=[FieldCondition(key="place_id", match=MatchValue(value=place_id))]
        )
        client.delete(
            collection_name=PRODUCTS_COLLECTION,
            points_selector=FilterSelector(filter=place_filter),
        )

        points = []

        # Index products
        for product_id, text, embedding, category_id in products:
            payload = TaxonomyVectorPayload(
                text=text,
                place_id=place_id,
                taxonomy_id=taxonomy_id,
                entity_type="product",
                entity_id=product_id,
                category_id=category_id,
            )
            points.append(PointStruct(
                id=product_id,
                vector=embedding,
                payload=payload.to_dict(),
            ))

        # Index categories
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
```

#### get_active_taxonomy_id()

```python
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
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        result = client.query_points(
            collection_name=PRODUCTS_COLLECTION,
            query=[0.0] * EMBEDDING_DIMENSION,  # Dummy vector
            query_filter=Filter(
                must=[FieldCondition(key="place_id", match=MatchValue(value=place_id))]
            ),
            limit=1,
            score_threshold=0.0,
        )

        if result.points:
            return result.points[0].payload.get("taxonomy_id")

        return None
    except Exception as e:
        logger.debug(f"No active taxonomy for place {place_id}: {e}")
        return None
```

---

## Step 3: Refactor Publish Endpoint

**File:** `pipline/api.py`

### 3.1 Helper: _index_taxonomy_vectors()

```python
def _index_taxonomy_vectors(
    session, place_id: str, taxonomy_id: str,
    products: List, categories: List
) -> int:
    """Generate embeddings and index approved taxonomy items in Qdrant."""
    import numpy as np

    products_to_index = []
    categories_to_index = []

    # Process products
    for p in products:
        texts = [p.canonical_text] + (p.variants or [])[:3]
        embeddings = embedding_client.generate_embeddings(texts, normalize=True)
        if embeddings:
            avg_emb = np.mean(embeddings, axis=0).tolist()
            category_id = str(p.assigned_category_id) if p.assigned_category_id else None
            products_to_index.append((str(p.id), p.canonical_text, avg_emb, category_id))
            p.vector_id = str(p.id)

    # Process aspect categories (has_products=False)
    aspect_categories = [c for c in categories if not c.has_products]
    if aspect_categories:
        cat_texts = [c.name for c in aspect_categories]
        cat_embeddings = embedding_client.generate_embeddings(cat_texts, normalize=True) or []
        for i, c in enumerate(aspect_categories):
            if i < len(cat_embeddings):
                categories_to_index.append((str(c.id), c.name, cat_embeddings[i]))
                c.vector_id = str(c.id)

    return vector_store.index_approved_taxonomy(
        place_id, taxonomy_id, products_to_index, categories_to_index
    )
```

### 3.2 Helper: _resolve_mentions_batch()

```python
def _resolve_mentions_batch(session, place_id: str, taxonomy_id: str) -> Tuple[int, int]:
    """Resolve all unresolved RawMentions using vector similarity."""

    product_resolved = 0
    category_resolved = 0

    mentions = session.query(RawMention).filter(
        RawMention.place_id == place_id,
        RawMention.resolved_product_id.is_(None),
        RawMention.resolved_category_id.is_(None),
    ).all()

    if not mentions:
        return 0, 0

    mention_texts = [m.mention_text for m in mentions]
    embeddings = embedding_client.generate_embeddings(mention_texts, normalize=True)

    if not embeddings:
        return 0, 0

    for mention, embedding in zip(mentions, embeddings):
        result = vector_store.find_matching_product(
            text_embedding=embedding,
            place_id=place_id,
            mention_type=mention.mention_type,
        )

        if result:
            payload = result.payload
            if payload.entity_type == "product":
                mention.resolved_product_id = UUID(payload.entity_id)
                if payload.category_id:
                    mention.resolved_category_id = UUID(payload.category_id)
                product_resolved += 1
            else:
                mention.resolved_category_id = UUID(payload.entity_id)
                category_resolved += 1

    return product_resolved, category_resolved
```

### 3.3 Helper: _aggregate_taxonomy_analytics()

```python
def _aggregate_taxonomy_analytics(session, taxonomy_id: UUID):
    """Compute and store aggregated mention_count and avg_sentiment."""
    from sqlalchemy import func, case

    # Aggregate for products
    product_stats = session.query(
        RawMention.resolved_product_id,
        func.count(RawMention.id).label('count'),
        func.avg(case(
            (RawMention.sentiment == 'positive', 1.0),
            (RawMention.sentiment == 'negative', -1.0),
            else_=0.0
        )).label('avg_sent')
    ).filter(
        RawMention.resolved_product_id.isnot(None)
    ).group_by(RawMention.resolved_product_id).all()

    for product_id, count, avg_sent in product_stats:
        product = session.query(TaxonomyProduct).filter_by(id=product_id).first()
        if product:
            product.mention_count = count
            product.avg_sentiment = (avg_sent + 1) / 2 if avg_sent else 0.5

    # Aggregate for categories
    category_stats = session.query(
        RawMention.resolved_category_id,
        func.count(RawMention.id).label('count'),
        func.avg(case(
            (RawMention.sentiment == 'positive', 1.0),
            (RawMention.sentiment == 'negative', -1.0),
            else_=0.0
        )).label('avg_sent')
    ).filter(
        RawMention.resolved_category_id.isnot(None),
        RawMention.resolved_product_id.is_(None),
    ).group_by(RawMention.resolved_category_id).all()

    for category_id, count, avg_sent in category_stats:
        category = session.query(TaxonomyCategory).filter_by(id=category_id).first()
        if category:
            category.mention_count = count
            category.avg_sentiment = (avg_sent + 1) / 2 if avg_sent else 0.5
```

### 3.4 Refactored publish_taxonomy()

```python
@app.post("/api/onboarding/taxonomies/{taxonomy_id}/publish", response_model=ActionResponse)
async def publish_taxonomy(taxonomy_id: UUID, current_user: User = Depends(get_current_user)):
    """Publish a taxonomy with vector-based resolution."""
    session = get_session()
    try:
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")
        if taxonomy.status == "active":
            raise HTTPException(status_code=400, detail="Already published")

        place_id = str(taxonomy.place_id)

        approved_categories = session.query(TaxonomyCategory).filter_by(
            taxonomy_id=taxonomy_id, is_approved=True).all()
        approved_products = session.query(TaxonomyProduct).filter_by(
            taxonomy_id=taxonomy_id, is_approved=True).all()

        if not approved_categories and not approved_products:
            raise HTTPException(status_code=400, detail="No approved items")

        # Update status
        old_status = taxonomy.status
        taxonomy.status = "active"
        taxonomy.published_at = datetime.utcnow()
        taxonomy.published_by = current_user.id

        # Step 1: Index in Qdrant
        indexed = _index_taxonomy_vectors(
            session, place_id, str(taxonomy_id), approved_products, approved_categories)

        # Step 2: Resolve mentions
        prod_resolved, cat_resolved = _resolve_mentions_batch(
            session, place_id, str(taxonomy_id))

        # Step 3: Aggregate analytics
        _aggregate_taxonomy_analytics(session, taxonomy_id)

        # Log action
        log_taxonomy_action(session, taxonomy_id, current_user.id, "publish", "taxonomy",
            taxonomy_id, {"status": old_status},
            {"status": "active", "indexed": indexed,
             "products_resolved": prod_resolved, "categories_resolved": cat_resolved})

        session.commit()
        return ActionResponse(
            success=True,
            message=f"Published. {indexed} indexed, {prod_resolved} products and {cat_resolved} categories resolved."
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()
```

---

## Step 4: Worker Live Resolution

**File:** `pipline/worker.py`

### 4.1 Helper: _increment_product_stats()

```python
def _increment_product_stats(session, product_id: UUID, sentiment: str):
    """Increment mention_count and update avg_sentiment for a product."""
    product = session.query(TaxonomyProduct).filter_by(id=product_id).first()
    if product:
        old_count = product.mention_count or 0
        old_sum = ((product.avg_sentiment or 0.5) * 2 - 1) * old_count

        sentiment_val = 1.0 if sentiment == "positive" else (-1.0 if sentiment == "negative" else 0.0)

        new_count = old_count + 1
        new_avg = (old_sum + sentiment_val) / new_count

        product.mention_count = new_count
        product.avg_sentiment = (new_avg + 1) / 2
```

### 4.2 Helper: _increment_category_stats()

```python
def _increment_category_stats(session, category_id: UUID, sentiment: str):
    """Increment mention_count and update avg_sentiment for a category."""
    category = session.query(TaxonomyCategory).filter_by(id=category_id).first()
    if category:
        old_count = category.mention_count or 0
        old_sum = ((category.avg_sentiment or 0.5) * 2 - 1) * old_count

        sentiment_val = 1.0 if sentiment == "positive" else (-1.0 if sentiment == "negative" else 0.0)

        new_count = old_count + 1
        new_avg = (old_sum + sentiment_val) / new_count

        category.mention_count = new_count
        category.avg_sentiment = (new_avg + 1) / 2
```

### 4.3 Modified process_mentions() Flow

Add after entity resolution (around line 120):

```python
# Check for active taxonomy and resolve
resolved_product_id = None
resolved_category_id = None

active_taxonomy_id = vector_store.get_active_taxonomy_id(str(place_id))

if active_taxonomy_id and embedding:
    result = vector_store.find_matching_product(
        text_embedding=embedding,
        place_id=str(place_id),
        mention_type=mention["type"],
    )

    if result:
        payload = result.payload
        if payload.entity_type == "product":
            resolved_product_id = UUID(payload.entity_id)
            if payload.category_id:
                resolved_category_id = UUID(payload.category_id)
            _increment_product_stats(session, resolved_product_id, mention["sentiment"])
        else:
            resolved_category_id = UUID(payload.entity_id)
            _increment_category_stats(session, resolved_category_id, mention["sentiment"])

# Save RawMention with resolution
raw_mention = RawMention(
    # ... existing fields ...
    resolved_product_id=resolved_product_id,
    resolved_category_id=resolved_category_id,
)
```

---

## Verification Tests

### Test 1: Publish with Vector Resolution
```bash
docker exec nurliya-api python -c "
# Publish taxonomy and verify vector resolution
from api import publish_taxonomy
# ... test code
"
```

### Test 2: Live Resolution
```bash
# 1. Publish taxonomy
# 2. Requeue a review
# 3. Check worker logs for resolution
docker logs nurliya-worker-1 --tail 50 | grep -i "resolved"
```

### Test 3: Cross-lingual Matching
```bash
docker exec nurliya-api python -c "
from embedding_client import generate_embeddings, compute_similarity
e1 = generate_embeddings(['coffee'], normalize=True)[0]
e2 = generate_embeddings(['قهوة'], normalize=True)[0]
print(f'Similarity: {compute_similarity(e1, e2):.3f}')  # Should be > 0.80
"
```

### Test 4: Full Lifecycle
```
Day 1: Scrape → Extract → Cluster → OS approves → Publish
Day 2: New reviews → Auto-resolved → Stats updated
Day 7: 50+ unmatched → Re-clustering → New draft
Day 8: OS reviews → Publishes updated taxonomy
```

---

## Key Design Decisions

| Decision | Value | Rationale |
|----------|-------|-----------|
| Product match threshold | 0.80 | Lower than 0.85 to catch spelling variants |
| Multiple match handling | Closest wins | limit=1 returns best match |
| Category resolution | Aspect categories only | has_products=False indexed |
| Stats update | Incremental | Real-time accuracy |
| Re-discovery trigger | 50 unmatched | Existing threshold in is_clustering_needed() |
