# Mention Audit & Multi-Branch Taxonomy - Implementation Plan

**Created**: 2026-02-04
**Related Issues**: BUG-014, FEATURE-001
**Related Documents**:
- `/home/42group/nurliya/TAXONOMY_PLAN.md`
- `/home/42group/nurliya/TAXONOMY_BUGS.md`
- `/home/42group/nurliya/TAXONOMY_PROGRESS.md`

---

## Overview

This plan addresses two interconnected issues in the taxonomy system:

| Issue | Priority | Description |
|-------|----------|-------------|
| **BUG-014** | P1 | Mention audit shows same data for all products/categories |
| **FEATURE-001** | High | Multi-branch businesses should share ONE taxonomy |

### How They're Related

```
BUG-014: "Show me mentions SIMILAR to this product"
         └─ Requires: Vector similarity search
         └─ Currently: Returns ALL unresolved mentions (broken)

FEATURE-001: "Query mentions from ALL branches of this business"
             └─ Requires: place_ids array on taxonomy
             └─ Currently: Single place_id only

Combined Benefit:
  → Onboarding specialist reviews shared taxonomy
  → Mention audit shows similar mentions from ALL branches
  → Better variant discovery, better cluster quality
```

---

## Current State Analysis

### BUG-014: Root Cause

**Location**: `pipline/api.py:980-993` (products), `api.py:1062-1073` (categories)

```python
# CURRENT CODE (BROKEN)
unresolved = session.query(RawMention, Review).join(...).filter(
    RawMention.place_id == place_id,
    RawMention.mention_type == 'product',
    RawMention.resolved_product_id.is_(None)  # Gets ALL unresolved, no similarity!
).limit(20).all()
```

**Problem**: Query returns the same 20 unresolved mentions for EVERY product.

**Expected Behavior**:
```
Product: "Spanish Latte"
├─ Matched (similarity > 0.80):
│   - "السبانش لاتيه was amazing" (0.92)
│   - "spanish latte is the best" (0.88)
│
└─ Below Threshold (0.60-0.80):
    - "سبانش" (0.75) ← Close but below threshold
    - "spanich late" (0.72) ← Typo, should match

Product: "V60"
├─ Matched: ...
└─ Below Threshold:
    - "v 60" (0.78) ← DIFFERENT from Spanish Latte results!
    - "vee sixty" (0.65)
```

### FEATURE-001: Current Schema Gap

**Location**: `pipline/database.py:194-215`

```python
# CURRENT SCHEMA
class PlaceTaxonomy(Base):
    place_id = Column(UUID)  # Single place only
    # Missing: place_ids = Column(ARRAY(UUID))
    # Missing: scrape_job_id = Column(UUID)
```

**Current Flow** (Broken for multi-branch):
```
Scrape: "Specialty Bean Roastery" (finds 2 branches)
  → Place A (Riyadh): 201 reviews → Job A → Taxonomy A
  → Place B (Dammam): 911 reviews → Job B → Taxonomy B
  (Separate taxonomies, separate clustering, duplicate work)
```

**Desired Flow**:
```
Scrape: "Specialty Bean Roastery" (finds 2 branches)
  → Wait for ALL jobs to complete (BUG-013 fix already does this!)
  → Combined clustering (all 1,112 mentions)
  → ONE shared taxonomy → place_ids = [Riyadh_UUID, Dammam_UUID]
```

### Existing Infrastructure

| Component | Status | Location |
|-----------|--------|----------|
| Vector similarity search | ✅ Ready | `vector_store.search_similar()` |
| MENTIONS_COLLECTION | ✅ Ready | Stores mention embeddings |
| PRODUCTS_COLLECTION | ✅ Ready | Stores approved product embeddings |
| Category centroid_embedding | ✅ Ready | `TaxonomyCategory.centroid_embedding` (BUG-006 fix) |
| Multi-job wait logic | ✅ Ready | `clustering_job.py:91-115` (BUG-013 fix) |
| Product centroid_embedding | ❌ Missing | TaxonomyProduct has no centroid |

---

## Implementation Plan

### Phase 1: Fix BUG-014 (Vector Similarity Search)

**Goal**: Make "below threshold" mentions actually show mentions SIMILAR to the product/category.

#### 1.1 Add Helper Function

**File**: `pipline/api.py`

```python
def _get_product_embedding(session, product: TaxonomyProduct) -> Optional[List[float]]:
    """
    Get embedding for a product from PRODUCTS_COLLECTION or generate.

    Checks in order:
    1. PRODUCTS_COLLECTION (indexed during publish)
    2. Generate from canonical_text + variants
    """
    from vector_store import _get_client, PRODUCTS_COLLECTION

    client = _get_client()
    if client and product.vector_id:
        try:
            points = client.retrieve(
                collection_name=PRODUCTS_COLLECTION,
                ids=[product.vector_id],
                with_vectors=True
            )
            if points:
                return points[0].vector
        except Exception as e:
            logger.debug(f"Could not retrieve product embedding: {e}")

    # Fallback: Generate from canonical_text
    from embedding_client import generate_embeddings
    texts = [product.canonical_text] + (product.variants or [])[:2]
    embeddings = generate_embeddings(texts, normalize=True)
    if embeddings:
        import numpy as np
        return np.mean(embeddings, axis=0).tolist()

    return None


def _get_category_embedding(session, category: TaxonomyCategory) -> Optional[List[float]]:
    """
    Get embedding for a category from centroid_embedding or generate.
    """
    # Use stored centroid (BUG-006 fix)
    if category.centroid_embedding:
        return category.centroid_embedding

    # Fallback: Generate from name
    from embedding_client import generate_embeddings
    embeddings = generate_embeddings([category.name], normalize=True)
    return embeddings[0] if embeddings else None
```

#### 1.2 Refactor get_product_mentions()

**File**: `pipline/api.py:957-1036`

```python
@app.get("/api/onboarding/products/{product_id}/mentions", response_model=MentionListResponse)
async def get_product_mentions(
    product_id: str,
    include_below_threshold: bool = True,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """Get mentions linked to a product, including near-misses below threshold."""
    session = get_session()
    try:
        product_uuid = UUID(product_id)
        product = session.query(TaxonomyProduct).filter_by(id=product_uuid).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Get mentions that resolved to this product (unchanged)
        matched_mentions = session.query(RawMention, Review).join(
            Review, RawMention.review_id == Review.id
        ).filter(
            RawMention.resolved_product_id == product_uuid
        ).all()

        # BUG-014 FIX: Get below-threshold mentions using vector similarity
        below_threshold_mentions = []
        if include_below_threshold and product.taxonomy:
            place_id = str(product.taxonomy.place_id)

            # Get product embedding
            product_embedding = _get_product_embedding(session, product)

            if product_embedding:
                from vector_store import search_similar, MENTIONS_COLLECTION

                # Search for similar unresolved mentions
                similar_results = search_similar(
                    collection_name=MENTIONS_COLLECTION,
                    query_vector=product_embedding,
                    place_id=place_id,
                    mention_type='product',
                    limit=30,
                    threshold=0.60,  # Lower bound for "near miss"
                )

                if similar_results:
                    # Get mention IDs that are already matched
                    matched_ids = {str(rm.id) for rm, _ in matched_mentions}

                    for result in similar_results:
                        # Filter: below 0.80 threshold and not already matched
                        if result.score < 0.80:
                            # Find mention by qdrant_point_id
                            mention = session.query(RawMention).filter_by(
                                qdrant_point_id=result.id
                            ).first()

                            if mention and str(mention.id) not in matched_ids:
                                if mention.resolved_product_id is None:
                                    review = session.query(Review).filter_by(
                                        id=mention.review_id
                                    ).first()
                                    if review:
                                        below_threshold_mentions.append(
                                            (mention, review, result.score)
                                        )
            else:
                # Fallback if no embedding available (original behavior)
                logger.warning(f"No embedding for product {product_id}, using fallback")
                unresolved = session.query(RawMention, Review).join(
                    Review, RawMention.review_id == Review.id
                ).filter(
                    RawMention.place_id == place_id,
                    RawMention.mention_type == 'product',
                    RawMention.resolved_product_id.is_(None)
                ).limit(20).all()
                below_threshold_mentions = [(rm, rev, 0.0) for rm, rev in unresolved]

        # Build response
        mentions = []
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
                review_date=review.review_date.isoformat() if hasattr(review.review_date, 'isoformat') else review.review_date,
                similarity_score=1.0  # Matched
            ))

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
                review_date=review.review_date.isoformat() if hasattr(review.review_date, 'isoformat') else review.review_date,
                similarity_score=score  # Actual similarity score
            ))

        # Sort by similarity score descending
        mentions.sort(key=lambda x: x.similarity_score, reverse=True)

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
```

#### 1.3 Refactor get_category_mentions()

**File**: `pipline/api.py:1039-1116`

Same pattern as products, using `_get_category_embedding()` and searching MENTIONS_COLLECTION with `mention_type='aspect'`.

---

### Phase 2: FEATURE-001 Schema Changes

**Goal**: Add multi-place support to PlaceTaxonomy (backward compatible).

#### 2.1 Database Schema

**File**: `pipline/database.py`

```python
class PlaceTaxonomy(Base):
    __tablename__ = "place_taxonomies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id = Column(UUID(as_uuid=True), ForeignKey("places.id"), nullable=False, index=True)

    # FEATURE-001: Multi-branch support
    place_ids = Column(ARRAY(UUID(as_uuid=True)))  # All places sharing this taxonomy
    scrape_job_id = Column(UUID(as_uuid=True), ForeignKey("scrape_jobs.id"), nullable=True)

    status = Column(String(20), default="draft")
    # ... rest unchanged ...
```

#### 2.2 Migration SQL

```sql
-- Add new columns
ALTER TABLE place_taxonomies ADD COLUMN place_ids UUID[];
ALTER TABLE place_taxonomies ADD COLUMN scrape_job_id UUID REFERENCES scrape_jobs(id);

-- Create index for place_ids array queries
CREATE INDEX ix_place_taxonomies_place_ids ON place_taxonomies USING GIN (place_ids);

-- Backfill existing taxonomies
UPDATE place_taxonomies
SET place_ids = ARRAY[place_id]
WHERE place_ids IS NULL;
```

---

### Phase 3: Update Queries for Multi-Place

**Goal**: Make BUG-014 fix work across multiple places.

#### 3.1 Update vector_store.search_similar()

**File**: `pipline/vector_store.py`

Add support for `place_ids` array parameter:

```python
def search_similar(
    collection_name: str,
    query_vector: List[float],
    place_id: Optional[str] = None,
    place_ids: Optional[List[str]] = None,  # NEW: Multi-place support
    mention_type: Optional[str] = None,
    limit: int = 10,
    threshold: float = 0.0,
) -> List[SearchResult]:
    """Search for similar vectors with optional filtering."""
    # ... existing code ...

    # Build filter conditions
    must_conditions = []

    # FEATURE-001: Support both single place_id and place_ids array
    if place_ids and len(place_ids) > 1:
        # Multiple places - use "should" with match_any
        from qdrant_client.http.models import MatchAny
        must_conditions.append(
            FieldCondition(key="place_id", match=MatchAny(any=place_ids))
        )
    elif place_id:
        must_conditions.append(
            FieldCondition(key="place_id", match=MatchValue(value=place_id))
        )

    # ... rest unchanged ...
```

#### 3.2 Update get_product_mentions() for Multi-Place

```python
# In get_product_mentions():
if include_below_threshold and product.taxonomy:
    taxonomy = product.taxonomy

    # FEATURE-001: Get all place_ids for shared taxonomy
    place_ids = [str(p) for p in taxonomy.place_ids] if taxonomy.place_ids else [str(taxonomy.place_id)]

    product_embedding = _get_product_embedding(session, product)

    if product_embedding:
        similar_results = search_similar(
            collection_name=MENTIONS_COLLECTION,
            query_vector=product_embedding,
            place_ids=place_ids,  # Search across ALL places
            mention_type='product',
            limit=30,
            threshold=0.60,
        )
```

---

### Phase 4: Combined Clustering

**Goal**: Create shared taxonomy for multi-branch businesses.

#### 4.1 Modify trigger_taxonomy_clustering()

**File**: `pipline/clustering_job.py`

```python
def trigger_taxonomy_clustering(job_id: str) -> bool:
    """
    Evaluate if clustering should be triggered for a completed job.
    For multi-branch scrapes, triggers combined clustering.
    """
    session = get_session()
    try:
        job = session.query(Job).filter_by(id=job_id).first()
        if not job or not job.place_id:
            return False

        # Find parent scrape job
        scrape_job = session.query(ScrapeJob).filter(
            ScrapeJob.pipeline_job_ids.any(job.id)
        ).first()

        if scrape_job and scrape_job.pipeline_job_ids:
            # FEATURE-001: Get ALL place_ids from the scrape
            all_jobs = session.query(Job).filter(
                Job.id.in_(scrape_job.pipeline_job_ids)
            ).all()

            place_ids = list(set(str(j.place_id) for j in all_jobs if j.place_id))

            if len(place_ids) > 1:
                # Multi-branch: Queue combined clustering
                return queue_combined_clustering(place_ids, str(scrape_job.id))

        # Single place: Original behavior
        return queue_single_place_clustering(str(job.place_id), job_id)
    finally:
        session.close()
```

#### 4.2 Add run_combined_clustering_job()

```python
def run_combined_clustering_job(place_ids: List[str], scrape_job_id: str):
    """
    Run clustering for multiple places (multi-branch support).
    Creates ONE shared taxonomy linked to all places.
    """
    session = get_session()
    try:
        # Gather mentions from ALL places
        all_mentions = []
        all_embeddings = []

        for place_id in place_ids:
            vectors = scroll_all_vectors(
                MENTIONS_COLLECTION,
                place_id=place_id,
                is_canonical=True,
            )
            for v in vectors:
                all_mentions.append(v.payload)
                all_embeddings.append(v.vector)

        if len(all_mentions) < MIN_MENTIONS_FOR_CLUSTERING:
            logger.info(f"Combined clustering: only {len(all_mentions)} mentions, skipping")
            return None

        # Cluster combined data
        labels = cluster_mentions(np.array(all_embeddings))

        # Build hierarchy from combined clusters
        hierarchy = build_hierarchy(all_mentions, labels, all_embeddings, business_type)

        # Create ONE shared taxonomy
        taxonomy = PlaceTaxonomy(
            place_id=UUID(place_ids[0]),       # Primary (backward compat)
            place_ids=[UUID(p) for p in place_ids],  # All places
            scrape_job_id=UUID(scrape_job_id),
            status="draft",
            discovered_at=datetime.utcnow(),
            reviews_sampled=len(all_mentions),
        )
        session.add(taxonomy)

        # Save categories and products (unchanged logic)
        save_taxonomy_entities(session, taxonomy, hierarchy)

        session.commit()
        return str(taxonomy.id)
    finally:
        session.close()
```

---

## API Changes Summary

### New/Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `GET /api/onboarding/products/{id}/mentions` | Vector similarity for below-threshold |
| `GET /api/onboarding/categories/{id}/mentions` | Vector similarity for below-threshold |
| `GET /api/onboarding/taxonomies/{id}` | Include `place_ids` in response |
| `GET /api/onboarding/pending` | Group taxonomies by `scrape_job_id` |

### Response Changes

**MentionResponse** - `similarity_score` now contains actual score (0.60-1.0) instead of just 0.0 or 1.0.

**TaxonomyDetailResponse** - Add `place_ids` and `scrape_job_id` fields.

---

## Testing Plan

### Phase 1 Tests (BUG-014)

```bash
# Test 1: Verify different products return different below-threshold mentions
curl -s "/api/onboarding/products/{spanish_latte_id}/mentions" | jq '.mentions[].mention_text'
curl -s "/api/onboarding/products/{v60_id}/mentions" | jq '.mentions[].mention_text'
# Results should be DIFFERENT

# Test 2: Verify similarity scores are populated
curl -s "/api/onboarding/products/{id}/mentions" | jq '.mentions[] | {text: .mention_text, score: .similarity_score}'
# Scores should be 0.60-1.0, not just 0.0 or 1.0

# Test 3: Cross-lingual matching
# Product "Spanish Latte" should find Arabic mentions like "سبانش" in below-threshold
```

### Phase 2 Tests (Schema)

```bash
# Test 1: Migration runs without error
alembic upgrade head

# Test 2: Existing taxonomies have place_ids backfilled
SELECT id, place_id, place_ids FROM place_taxonomies LIMIT 5;
# place_ids should equal ARRAY[place_id]
```

### Phase 3 Tests (Multi-Place Queries)

```bash
# Test 1: Shared taxonomy queries both places
# Create taxonomy with place_ids = [place_a, place_b]
# Query mentions - should return results from both places
```

### Phase 4 Tests (Combined Clustering)

```bash
# Test 1: Multi-branch scrape creates ONE taxonomy
# Scrape business with 2 branches
# Verify: Only 1 PlaceTaxonomy created with place_ids containing both UUIDs

# Test 2: Combined clustering has better quality
# Compare cluster count and sizes vs separate clustering
```

---

## Rollback Plan

### Phase 1 (BUG-014)
- Revert API changes
- No database changes to rollback

### Phase 2 (Schema)
```sql
-- Remove new columns (data loss!)
ALTER TABLE place_taxonomies DROP COLUMN place_ids;
ALTER TABLE place_taxonomies DROP COLUMN scrape_job_id;
```

### Phase 3-4
- Revert code changes
- Existing taxonomies continue to work (backward compatible)

---

## Dependencies

| Phase | Depends On |
|-------|------------|
| Phase 1 | BUG-006 fix (centroid_embedding) ✅ |
| Phase 2 | Database migration capability |
| Phase 3 | Phase 1 + Phase 2 |
| Phase 4 | Phase 2 + Phase 3 |

---

## Timeline

| Phase | Effort | Description |
|-------|--------|-------------|
| Phase 1 | 1 day | BUG-014 fix with vector similarity |
| Phase 2 | 0.5 day | Schema migration |
| Phase 3 | 0.5 day | Multi-place query support |
| Phase 4 | 1-2 days | Combined clustering logic |

---

## Files to Modify

| File | Phase | Changes |
|------|-------|---------|
| `pipline/api.py` | 1, 3 | get_product_mentions, get_category_mentions, helper functions |
| `pipline/vector_store.py` | 3 | search_similar() place_ids support |
| `pipline/database.py` | 2 | PlaceTaxonomy.place_ids, scrape_job_id |
| `pipline/clustering_job.py` | 4 | Combined clustering logic |
| `onboarding-portal/src/lib/api.ts` | 1 | Handle similarity_score in response |
| `onboarding-portal/src/components/MentionPanel.tsx` | 1 | Display similarity scores |

---

*Document created: 2026-02-04*
*Last updated: 2026-02-04*
