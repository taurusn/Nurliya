# OS-Driven Anchor System - Next Session Guide

**Branch**: `feature/taxonomy-system`
**Last commit**: `feat: implement OS-driven anchor system (Phases 0-2)`
**Plan**: `OS_ANCHOR_PLAN_2026-02-05.md`
**Progress**: `OS_ANCHOR_PROGRESS.md`

---

## Completed (Phases 0-2)

All committed. No uncommitted changes.

### Phase 0: Fixed `anchor_manager.py`
- Changed `from embedding_client import EmbeddingClient` to `import embedding_client`
- Removed `embedding_client = EmbeddingClient()` (class doesn't exist, only module functions)
- Added `IMPORT_MATCH_THRESHOLD = 0.85`, `LEARNED_MATCH_THRESHOLD = 0.88`
- Updated docstrings from 768-dim to 384-dim (MiniLM-L12-v2)
- Added optional `anchors` param to `classify_mentions_to_anchors()`

### Phase 1: Removed seed files
- Deleted `pipline/seeds/coffee_shop.py`, `seeds/__init__.py`, `seed_anchors.py`
- `create_seed_anchors()` kept as dead code (generic utility)

### Phase 2: Wired anchors into clustering
- `run_clustering_job()`: added `import_anchors`, `is_recluster` params
- Step 2.5: anchor pre-classification between Step 2 (separate) and Step 3 (HDBSCAN)
- `build_anchor_matched_hierarchy()`: groups by anchor, deduplicates products
- `_merge_hierarchies()`: anchor priority, name-based dedup
- `save_draft_taxonomy()`: `is_recluster=True` deletes old draft first
- Cold start (no anchors) = pure HDBSCAN (backward compatible)

---

## Next: Phase 3 - Auto-Learn on Publish

**Files to modify**: `pipline/api.py`, `pipline/anchor_manager.py`

### 3A: Hook into `publish_taxonomy()` in `api.py`

Insert after `session.commit()` at **line 1911** in `api.py`:

```python
# Auto-learn anchors from approved categories
from anchor_manager import learn_from_approved_taxonomy
try:
    learned_count = learn_from_approved_taxonomy(str(taxonomy_id))
    logger.info(f"Auto-learned {learned_count} examples from taxonomy {taxonomy_id}")
except Exception as e:
    logger.warning(f"Auto-learning failed (non-blocking): {e}")
```

This is non-blocking — if learning fails, publish still succeeds.

### 3B: Fix `learn_from_approved_taxonomy()` in `anchor_manager.py`

Current function (line 204-300) has two bugs:

**Bug 1**: Only queries `discovered_category_id`, but after publish mentions use `resolved_category_id`. Fix the query at line 235:

```python
# Before (broken after publish):
mentions = session.query(RawMention).filter(
    RawMention.discovered_category_id == category.id
).all()

# After (check both):
mentions = session.query(RawMention).filter(
    or_(
        RawMention.discovered_category_id == category.id,
        RawMention.resolved_category_id == category.id,
    )
).all()
```

Need to import `or_` from sqlalchemy.

**Bug 2**: Doesn't collect product text for product categories. For categories with `has_products=True`, also gather product `canonical_text` + `variants` as anchor examples. Add after the mention collection:

```python
# For product categories, also learn from product names/variants
if category.has_products:
    products = session.query(TaxonomyProduct).filter_by(
        assigned_category_id=category.id,
        is_approved=True,
    ).all()
    for product in products:
        # Add canonical text
        product_texts.append(product.canonical_text)
        # Add variants
        if product.variants:
            product_texts.extend(product.variants)
```

Need to import `TaxonomyProduct` in anchor_manager.py.

### 3C: Test verification
- Publish a taxonomy -> check `category_anchors` table has new `source='learned'` entries
- Verify anchor examples are created with embeddings
- Verify centroids are computed

---

## After Phase 3: Phase 4 - JSON Import API + Re-Clustering

**Files**: `pipline/api.py`, `pipline/anchor_manager.py`, `pipline/database.py`

### 4A: `anchor_manager.py`
- Add `generate_anchors_from_import(import_data)` function
- Converts imported JSON categories into anchor-format dicts
- Generates embeddings, computes centroids
- Returns same format as `load_anchors_for_business()` output

### 4B: `api.py`
- Add Pydantic models: `ImportCategoryItem`, `ImportProductItem`, `TaxonomyImportRequest`
- Add `POST /api/onboarding/taxonomies/{taxonomy_id}/import` endpoint
- Endpoint: validate draft, create imported categories, clear old discovered, queue re-cluster

### 4C: `database.py`
- Add `source = Column(String(20), default="discovered")` to `TaxonomyCategory`
  - Values: `discovered`, `imported`, `manual`
- Add `is_reclustering = Column(Boolean, default=False)` to `PlaceTaxonomy`

---

## After Phase 4: Phase 5 - Import UI

**Files**: `onboarding-portal/src/`

- `src/lib/api.ts`: Add `importTaxonomy()` + types
- `src/components/ImportModal.tsx`: New modal (file upload, JSON validation, preview)
- `src/app/[taxonomyId]/page.tsx`: Import button (draft only), wire modal

---

## Key Architecture Notes

- **Embedding model**: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim)
- **Anchor storage**: PostgreSQL JSONB (centroids + examples), NOT Qdrant
- **Qdrant**: Only `MENTIONS_COLLECTION` and `PRODUCTS_COLLECTION`
- **Classification**: In-memory cosine similarity (numpy) against anchor centroids
- **Thresholds**: Learned=0.88, Import=0.85
- **Re-clustering**: `run_clustering_job(import_anchors=..., is_recluster=True)` called directly (bypasses `process_clustering_message()` and its `is_clustering_needed()` check)

## Key File Locations

| File | Purpose |
|------|---------|
| `pipline/anchor_manager.py` | Anchor CRUD, classification, learning |
| `pipline/clustering_job.py` | Main clustering pipeline with anchor integration |
| `pipline/database.py` | SQLAlchemy models (CategoryAnchor, AnchorExample, etc.) |
| `pipline/api.py` | FastAPI endpoints (publish at ~line 1826) |
| `pipline/embedding_client.py` | Module-level functions: `generate_embeddings()`, etc. |
| `pipline/vector_store.py` | Qdrant operations (MENTIONS_COLLECTION, PRODUCTS_COLLECTION) |
| `onboarding-portal/src/lib/api.ts` | Frontend API client |
| `onboarding-portal/src/app/[taxonomyId]/page.tsx` | Taxonomy editor page |
