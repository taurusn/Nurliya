# Taxonomy System - Known Bugs & Issues

**Created**: 2026-02-03
**Related Documents**:
- Plan: `/home/42group/nurliya/TAXONOMY_PLAN.md`
- Progress: `/home/42group/nurliya/TAXONOMY_PROGRESS.md`
- Phase 4 Plan: `/home/42group/nurliya/PHASE4_PLAN.md`

---

## Summary

| Priority | Count | Status |
|----------|-------|--------|
| P0 (Blocking) | 3 | **Fixed** (2026-02-03) |
| P1 (High) | 3 | **Fixed** (2026-02-03) |
| P2 (Medium) | 3 | **Fixed** (2026-02-03) |
| P2 (Medium) | 3 | **Open** - Extract-First Pipeline (2026-02-03) |

---

## P0 - Blocking Issues

### BUG-001: Race Condition - Clustering Triggered Before Mentions Saved

**Severity**: P0 (Blocking)
**Status**: **FIXED** (2026-02-03)
**File**: `pipline/clustering_job.py:78-145`
**Related Plan Section**: Phase 1B Worker Integration (TAXONOMY_PLAN.md line 284-288)

**Description**:
Job completion triggers `trigger_taxonomy_clustering(job_id)` before `process_mentions()` completes. Since mention extraction is non-blocking (line 75 comment), the clustering job may run on an incomplete mention set.

**Plan Reference**:
> Phase 1B: Modify worker.py for dual-write (keep old topics + new mentions)
> - Non-blocking process_mentions() after save_analysis()

The plan specifies non-blocking for graceful degradation, but doesn't account for the clustering trigger timing.

**Current Code**:
```python
# worker.py:498
update_job_progress(job_id)
trigger_taxonomy_clustering(job_id)  # Called while process_mentions may still be running
```

**Impact**:
- Taxonomy built on 70-90% of actual mentions
- Products with few mentions may be classified as noise
- Re-discovery threshold (50 unresolved) triggered prematurely

**Fix Applied**:
Added extraction rate verification in `is_clustering_needed()`:
- Now accepts optional `job_id` parameter
- Counts RawMentions for reviews in the completed job
- Requires at least 30% extraction rate (MIN_EXTRACTION_RATE = 0.3)
- Logs warning and skips clustering if extraction appears incomplete

```python
# clustering_job.py:78-145
def is_clustering_needed(place_id: str, job_id: str = None) -> Tuple[bool, str]:
    if job_id:
        # Verify extraction rate before clustering
        extraction_rate = mention_count_for_job / review_count
        if extraction_rate < MIN_EXTRACTION_RATE:
            return False, f"Extraction incomplete: only {extraction_rate:.1%}"
```

---

### BUG-002: Category Statistics Exclude Product Mentions

**Severity**: P0 (Blocking)
**Status**: **FIXED** (2026-02-03)
**File**: `pipline/api.py:977-1090`
**Related Plan Section**: Phase 4 Integration - Analytics (TAXONOMY_PLAN.md line 302-306)

**Description**:
`_aggregate_taxonomy_analytics()` filters out product-resolved mentions when computing category statistics, causing artificially low category sentiment scores.

**Plan Reference**:
> Phase 4: Integration
> - Analytics endpoints (by category, by product, timeline)
> - Client portal category/product breakdown

The plan expects category breakdowns to reflect ALL mentions in that category, including those resolved through products.

**Current Code**:
```python
# api.py:1026
).filter(
    RawMention.resolved_category_id.in_(approved_category_ids),
    RawMention.resolved_product_id.is_(None),  # BUG: Excludes product mentions
).group_by(RawMention.resolved_category_id).all()
```

**Example**:
- Mention "Spanish Latte is great" → resolved to Product "Spanish Latte" → in Category "Hot Coffee"
- Current: Category "Hot Coffee" does NOT count this mention
- Expected: Category "Hot Coffee" SHOULD count this mention (aggregated from its products)

**Impact**:
- Category sentiment shows only aspect mentions (e.g., "service was slow")
- Product-heavy categories show near-zero mention counts
- Client portal category breakdown is misleading

**Fix Applied**:
Refactored `_aggregate_taxonomy_analytics()` to aggregate from two sources:

1. **Direct category mentions** (aspects like "service was slow")
2. **Product rollup** (mentions resolved to products, rolled up to their category)

```python
# api.py:977-1090
# Source 1: Direct category mentions
direct_category_stats = session.query(...).filter(
    RawMention.resolved_category_id.in_(approved_category_ids),
    RawMention.resolved_product_id.is_(None),  # Direct mentions only
)

# Source 2: Rollup from products
for product_id, (count, avg_sent) in product_stats_map.items():
    category_id = product_to_category.get(product_id)
    if category_id in category_totals:
        category_totals[category_id]['count'] += count
        category_totals[category_id]['sentiment_sum'] += (avg_sent * count)
```

---

### BUG-003: Silent Embedding Failures Skip Products

**Severity**: P0 (Blocking)
**Status**: **FIXED** (2026-02-03)
**File**: `pipline/api.py:881-975`
**Related Plan Section**: Phase 4 Integration (PHASE4_PLAN.md line 191-271)

**Description**:
If `generate_embeddings()` fails or returns partial results, products are silently skipped from PRODUCTS_COLLECTION indexing. No error is logged.

**Plan Reference** (PHASE4_PLAN.md):
> index_approved_taxonomy()
> - Index approved products and categories in PRODUCTS_COLLECTION
> - Returns: Number of indexed vectors

The plan assumes all approved products get indexed.

**Current Code**:
```python
# api.py:900-910
all_embeddings = embedding_client.generate_embeddings(all_texts, normalize=True) or []
# No validation that len(all_embeddings) == len(all_texts)
for p, start_idx, end_idx in product_text_ranges:
    product_embs = all_embeddings[start_idx:end_idx]
    if product_embs:  # Silently skips if empty
        # ... index product
```

**Impact**:
- Approved products become unsearchable for live resolution
- Client sees product in portal but mentions never resolve to it
- No indication of failure in logs or audit trail

**Fix Applied**:
Refactored `_index_taxonomy_vectors()` with comprehensive validation:

1. **Return type changed** from `int` to `tuple`: `(indexed_count, skipped_products, skipped_categories)`
2. **Validation added** for embedding generation results
3. **Logging added** for all failure cases
4. **Skipped items tracked** and reported in publish response

```python
# api.py:881-975
def _index_taxonomy_vectors(...) -> tuple:
    # Validate embedding count
    if all_embeddings is None:
        logger.error("Embedding generation failed completely")
        skipped_products = [p.canonical_text for p in products]
    elif len(all_embeddings) != len(all_texts):
        logger.error(f"Embedding count mismatch: expected {len(all_texts)}, got {len(all_embeddings)}")

    # Validate individual embeddings (not all zeros)
    valid_embs = [e for e in product_embs if e is not None and not all(v == 0.0 for v in e)]

    return indexed_count, len(skipped_products), len(skipped_categories)
```

Publish response now includes warning if items were skipped:
```
"Taxonomy published. 45 items indexed... Warning: 3 products and 1 categories could not be indexed."
```

---

## P1 - High Priority Issues

### BUG-004: Dual Statistics Sources Conflict

**Severity**: P1 (High)
**Status**: **FIXED** (2026-02-03)
**Files**: `pipline/worker.py:39-68`, `pipline/api.py:1068-1164`
**Related Plan Section**: Phase 4 Integration (TAXONOMY_PLAN.md line 302-306)

**Description**:
Two independent systems update `mention_count` and `avg_sentiment` on TaxonomyProduct/TaxonomyCategory:
1. **Live updates**: `_increment_product_stats()` in worker.py (real-time)
2. **Batch aggregation**: `_aggregate_taxonomy_analytics()` in api.py (on publish)

These conflict because publish overwrites live counts.

**Plan Reference**:
> Phase 4: Integration
> - Add resolved_products/categories to ReviewAnalysis

The plan doesn't specify whether statistics should be live-updated or batch-computed.

**Fix Applied**:
Chose **Option A**: Removed live updates, single source of truth is RawMention table.

1. Removed `_increment_product_stats()` and `_increment_category_stats()` from worker.py
2. Removed calls to these functions in `process_mentions()`
3. Statistics now computed ONLY via `_aggregate_taxonomy_analytics()` during publish
4. Removed unused imports (TaxonomyProduct, TaxonomyCategory from worker.py)

```python
# worker.py - REMOVED:
# def _increment_product_stats(session, product_id, sentiment): ...
# def _increment_category_stats(session, category_id, sentiment): ...

# In process_mentions() - REMOVED calls:
# _increment_product_stats(session, resolved_product_id, mention["sentiment"])
# _increment_category_stats(session, resolved_category_id, mention["sentiment"])
```

**Benefit**: Stats are always consistent - computed from authoritative RawMention table on every publish.

---

### BUG-005: Batch Resolution Skips Already-Resolved Mentions

**Severity**: P1 (High)
**Status**: **FIXED** (2026-02-03)
**File**: `pipline/api.py:1018-1107`
**Related Plan Section**: Phase 4 Integration (PHASE4_PLAN.md line 354-396)

**Description**:
`_resolve_mentions_batch()` only processes mentions where BOTH `resolved_product_id` AND `resolved_category_id` are NULL. Mentions resolved during Phase 1 (live) are never re-evaluated against newly approved products.

**Fix Applied**:
Refactored `_resolve_mentions_batch()` to resolve ALL mentions for the place:

1. Fetches ALL mentions (not just completely unresolved)
2. Re-resolves against newly approved products/categories
3. Tracks "newly resolved" vs "re-resolved" for logging
4. Only updates if resolution changed (prevents unnecessary DB writes)

```python
# api.py:1018-1107
def _resolve_mentions_batch(session, place_id: str, taxonomy_id: str = None) -> tuple:
    # BUG-005 FIX: Get ALL mentions for this place
    mentions = session.query(RawMention).filter(
        RawMention.place_id == place_uuid,
    ).all()

    # Track changes
    was_unresolved = mention.resolved_product_id is None and mention.resolved_category_id is None

    # Only count as resolved if it changed
    if mention.resolved_product_id != new_product_id:
        mention.resolved_product_id = new_product_id
        ...
```

**Benefit**:
- Historical mentions now properly linked to approved products
- Re-resolution finds better matches when new products approved
- Logs show how many were newly resolved vs re-resolved

---

### BUG-006: Centroid Embeddings Lost - Re-generated from Names

**Severity**: P1 (High)
**Status**: **FIXED** (2026-02-03)
**Files**: `pipline/clustering_job.py:772`, `pipline/api.py:913-920`, `pipline/database.py:238`
**Related Plan Section**: Phase 2 Discovery (TAXONOMY_PLAN.md line 290-294)

**Description**:
During clustering, centroids are computed from actual mention embeddings. But during publish, completely NEW embeddings are generated from category names. These won't match.

**Plan Reference**:
> Phase 2: Discovery
> - Create clustering_job.py (HDBSCAN + LLM labeling)
> - Build hierarchy (Main → Sub → Products)

The plan doesn't specify that centroids should be preserved for later indexing.

**Current Flow** (before fix):
```
Clustering:
  "Spanish Latte" cluster centroid = average of ["spanish latte", "سبانش لاتيه", "Spanish latté"] embeddings

Publish:
  Category "Hot Coffee" embedding = embedding of text "Hot Coffee"  ← DIFFERENT!
```

**Impact**:
- Live resolution uses PRODUCTS_COLLECTION (name-based embeddings)
- Mention embeddings were clustered against centroid embeddings
- Semantic mismatch causes resolution failures for edge cases

**Fix Applied**:
Implemented end-to-end centroid preservation across three files:

1. **database.py**: Added `centroid_embedding` column to TaxonomyCategory
```python
# TaxonomyCategory model
centroid_embedding = Column(JSONB)  # List[float] - 384-dim for MiniLM
```

2. **clustering_job.py**: Compute and store centroids during discovery
```python
# In cluster_aspects() - compute centroids per cluster
aspect_centroids = {}
for label in set(labels):
    if label == -1:
        continue
    cluster_mask = labels == label
    cluster_embeddings = embeddings[cluster_mask]
    aspect_centroids[label] = np.mean(cluster_embeddings, axis=0)

# Pass to build_hierarchy()
hierarchy = build_hierarchy(..., aspect_centroids=aspect_centroids)

# In save_draft_taxonomy() - store centroid in category
category = TaxonomyCategory(
    ...
    centroid_embedding=centroid.tolist() if centroid is not None else None,
)
```

3. **api.py**: Use stored centroids during publish indexing
```python
# In _index_taxonomy_vectors()
for category in categories:
    if category.centroid_embedding:
        # BUG-006 FIX: Use stored centroid from clustering
        embedding = category.centroid_embedding
    else:
        # Fallback: generate from name
        embedding = embedding_client.generate_embeddings([category.name])[0]
```

**Note**: Centroids are per-place. Each place's "Spanish Latte" has its own centroid based on how that place's customers describe it.

**Migration Required**: Run `alembic revision --autogenerate` to add `centroid_embedding` column.

---

## P2 - Medium Priority Issues

### BUG-007: No Distributed Lock on Publish

**Severity**: P2 (Medium)
**Status**: **FIXED** (2026-02-03)
**File**: `pipline/api.py:1246-1340`
**Related Plan Section**: Phase 3 Onboarding Portal (TAXONOMY_PLAN.md line 296-300)

**Description**:
Multiple concurrent requests to `publish_taxonomy()` could both succeed, causing duplicate indexing and inconsistent state.

**Plan Reference**:
> Phase 3: Onboarding Portal
> - API endpoints for approve/reject/move/link/publish

The plan doesn't specify concurrency handling for publish.

**Fix Applied**:
Added PostgreSQL advisory lock with proper cleanup:

```python
# api.py:1246-1340
lock_acquired = False
try:
    taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
    if not taxonomy:
        raise HTTPException(status_code=404, detail="Taxonomy not found")

    # BUG-007 FIX: Acquire advisory lock to prevent concurrent publish
    lock_key = taxonomy_id.int % (2**31 - 1)  # PostgreSQL bigint limit
    session.execute(text(f"SELECT pg_advisory_lock({lock_key})"))
    lock_acquired = True

    # Re-check status after acquiring lock (another request may have published)
    session.refresh(taxonomy)
    if taxonomy.status == "active":
        raise HTTPException(status_code=400, detail="Taxonomy already published")
    # ... rest of publish logic
finally:
    # BUG-007 FIX: Release advisory lock
    if lock_acquired:
        try:
            lock_key = taxonomy_id.int % (2**31 - 1)
            session.execute(text(f"SELECT pg_advisory_unlock({lock_key})"))
        except Exception:
            pass  # Lock will be released when session closes anyway
    session.close()
```

**Key aspects of fix:**
1. Uses `pg_advisory_lock` with taxonomy ID as lock key
2. Re-checks status after acquiring lock (double-check pattern)
3. Properly releases lock in finally block
4. Handles lock cleanup even on exception

---

### BUG-008: Product Variants Not Indexed in PRODUCTS_COLLECTION

**Severity**: P2 (Medium)
**Status**: **FIXED** (2026-02-03)
**Files**: `pipline/api.py:957-978`, `pipline/vector_store.py:490-567`
**Related Plan Section**: Database Schema (TAXONOMY_PLAN.md line 358-373)

**Description**:
`TaxonomyProduct.variants` field stores alternative spellings (e.g., "spanish latté", "سبانش"), but these variants were averaged into a single embedding instead of indexed individually.

**Fix Applied**:

1. **api.py:_index_taxonomy_vectors()** - Index each variant separately:
```python
# BUG-008 FIX: Index each variant separately instead of averaging
for p, start_idx, end_idx in product_text_ranges:
    texts = [p.canonical_text] + (p.variants or [])[:3]
    product_embs = all_embeddings[start_idx:end_idx]
    product_id = str(p.id)

    # Index each variant as a separate point with same entity_id
    for i, (text, emb) in enumerate(zip(texts, product_embs)):
        if emb is not None and not all(v == 0.0 for v in emb):
            # Use product_id for canonical, product_id_v{i} for variants
            point_id = product_id if i == 0 else f"{product_id}_v{i}"
            products_to_index.append((point_id, text, emb, product_id, category_id))
```

2. **vector_store.py:index_approved_taxonomy()** - Updated signature:
```python
# New tuple format: (point_id, text, embedding, entity_id, category_id)
# - point_id: Unique ID for this vector point
# - entity_id: Product UUID (same for all variants of a product)

for point_id, text, embedding, entity_id, category_id in products:
    payload = TaxonomyVectorPayload(
        text=text,
        entity_id=entity_id,  # Same entity_id for all variants
        # ...
    )
    points.append(PointStruct(
        id=point_id,  # Unique ID per variant
        vector=embedding,
        payload=payload.to_dict(),
    ))
```

**Result**:
- Arabic variant "سبانش لاتيه" now has its own vector point
- Arabic-only mentions match the Arabic variant directly
- Improved cross-lingual matching accuracy

---

### BUG-009: No Cascading Updates When Product Moved

**Severity**: P2 (Medium)
**Status**: **FIXED** (2026-02-03)
**File**: `pipline/api.py:723-743`
**Related Plan Section**: Phase 3 Onboarding Portal - Actions (TAXONOMY_PLAN.md line 147-163)

**Description**:
When a product is moved to a different category via the onboarding portal, existing `RawMention.resolved_category_id` values were not updated.

**Fix Applied**:
```python
# api.py:723-743
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
```

**Result**:
- Moving a product now automatically updates all related RawMentions
- Analytics remain consistent with taxonomy structure
- Response message indicates how many mentions were updated

---

### BUG-010: No Extraction Validation Before Sentiment Queue

**Severity**: P2 (Medium)
**Status**: **Open**
**File**: `pipline/api.py:1383-1408`
**Related**: Extract-First Pipeline (EXTRACT_FIRST_PLAN.md)

**Description**:
`publish_taxonomy()` queues reviews with `mode="sentiment"` but doesn't verify that extraction was completed. If extraction phase was skipped or failed, sentiment analysis runs without RawMention context.

**Current Code**:
```python
# api.py:1383-1408
reviews_to_analyze = session.query(Review).filter(
    Review.place_id == taxonomy.place_id,
    Review.job_id.isnot(None)
).outerjoin(ReviewAnalysis, Review.id == ReviewAnalysis.review_id).filter(
    ReviewAnalysis.id.is_(None)  # No existing analysis
).all()
# No check for RawMention extraction completion
```

**Impact**:
- Sentiment analysis runs without taxonomy-aware context
- LLM can't match to products/categories (no extraction data)
- Silent degradation of analysis quality

**Proposed Fix**:
```python
# Before queuing, verify extraction exists
mentions_count = session.query(RawMention).filter(
    RawMention.place_id == taxonomy.place_id
).count()
if mentions_count == 0:
    logger.warning("No mentions extracted - sentiment analysis may lack context")
```

---

### BUG-011: Silent Fallback Loses Taxonomy Context

**Severity**: P2 (Medium)
**Status**: **Open**
**File**: `pipline/llm_client.py:545-549`
**Related**: Extract-First Pipeline

**Description**:
If `analyze_with_taxonomy()` LLM call fails, it silently falls back to `analyze_review()` WITHOUT taxonomy context. After building and approving a taxonomy, the review loses all taxonomy-aware benefits.

**Current Code**:
```python
# llm_client.py:545-549
except Exception as e:
    logger.error(f"Taxonomy-aware analysis failed: {e}")
    # BUG: Falls back to analysis WITHOUT taxonomy context
    return analyze_review(review_text, rating)
```

**Impact**:
- Review analyzed without knowing approved products/categories
- Summaries say "coffee was good" instead of "Spanish Latte was good"
- Inconsistent analysis quality across reviews

**Proposed Fix**:
Option A: Queue for retry with taxonomy context
Option B: Return error and let worker handle retry
Option C: Store partial result with flag indicating fallback used

---

### BUG-012: No Explicit Extraction Complete Flag

**Severity**: P2 (Medium)
**Status**: **Open**
**Files**: `pipline/worker.py`, `pipline/database.py`
**Related**: Extract-First Pipeline

**Description**:
There's no explicit flag on Job to indicate extraction phase completed successfully. Clustering and sentiment queueing rely on implicit checks (review count vs mention count ratio).

**Current Flow**:
```
Job completes → update_job_progress() → trigger_taxonomy_clustering()
                                         └─ is_clustering_needed() checks mention ratio
```

**Impact**:
- Race condition: clustering may check before all mentions saved
- No way to query "jobs with completed extraction"
- Publish can't verify extraction state

**Proposed Fix**:
Add `extraction_completed_at` timestamp to Job model:
```python
# database.py - Job model
extraction_completed_at = Column(DateTime)  # Set when all mentions saved

# worker.py - After all reviews processed
if mode == "extraction":
    job.extraction_completed_at = datetime.utcnow()
```

---

## Design Issues (Not Bugs)

### DESIGN-001: No Re-indexing Command for Disaster Recovery

**Related Plan Section**: Phase 5 Polish (TAXONOMY_PLAN.md line 308-312)

If Qdrant loses data, there's no way to rebuild PRODUCTS_COLLECTION without re-publishing all taxonomies. Consider adding:
- `POST /api/admin/reindex-taxonomy/{taxonomy_id}`
- Or automatic reconciliation job

---

### DESIGN-002: Entity Resolution vs Product Match Thresholds Differ

**Files**: `worker.py:32` (0.85), `vector_store.py:28` (0.80)

Two different thresholds with no documentation explaining why:
- Entity resolution (finding similar mentions): 0.85
- Product matching (resolving to approved taxonomy): 0.80

This means a mention might create a new canonical entity (fails 0.85) but still match an approved product (passes 0.80).

---

### DESIGN-003: No Feedback Loop Between Collections

**Related Plan Section**: Architecture (TAXONOMY_PLAN.md line 225-238)

MENTIONS_COLLECTION and PRODUCTS_COLLECTION are independent:
- Approving a product doesn't update MENTIONS_COLLECTION
- Future mentions might create new canonical entries instead of resolving to approved product

Consider syncing collections or using single collection with status flags.

---

## References

| Bug ID | File | Line(s) | Plan Section |
|--------|------|---------|--------------|
| BUG-001 | worker.py | 498 | Phase 1B (line 284-288) |
| BUG-002 | api.py | 1026 | Phase 4 Analytics (line 302-306) |
| BUG-003 | api.py | 900-910 | PHASE4_PLAN (line 191-271) |
| BUG-004 | worker.py, api.py | 39-68, 977-1033 | Phase 4 (line 302-306) |
| BUG-005 | api.py | 937-940 | PHASE4_PLAN (line 354-396) |
| BUG-006 | clustering_job.py, api.py | 772, 913-920 | Phase 2 (line 290-294) |
| BUG-007 | api.py | 1036-1117 | Phase 3 (line 296-300) |
| BUG-008 | vector_store.py | 436-487 | Schema (line 358-373) |
| BUG-009 | api.py | 723-725 | Phase 3 Actions (line 147-163) |
| BUG-010 | api.py | 1383-1408 | Extract-First Pipeline |
| BUG-011 | llm_client.py | 545-549 | Extract-First Pipeline |
| BUG-012 | worker.py, database.py | - | Extract-First Pipeline |
