# OS-Driven Anchor System - Progress Tracker

**Created**: 2026-02-05
**Plan**: `OS_ANCHOR_PLAN_2026-02-05.md`

---

## Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 | Fix `anchor_manager.py` import bug | **Done** |
| Phase 1 | Remove hardcoded seed files | **Done** |
| Phase 2 | Wire anchors into clustering pipeline | **Done** |
| Phase 3 | Auto-learn on publish | **Done** |
| Phase 4 | JSON import API + re-clustering | **Done** |
| Phase 5 | Import UI in onboarding portal | **Pending** |

---

## Phase 0: Fix `anchor_manager.py` Import Bug

**Status**: Done (2026-02-05)
**File**: `pipline/anchor_manager.py`

- [x] Change `from embedding_client import EmbeddingClient` to `import embedding_client`
- [x] Remove `embedding_client = EmbeddingClient()` line
- [x] Add `IMPORT_MATCH_THRESHOLD = 0.85`
- [x] Update source-specific threshold logic in `classify_to_anchor()` to handle `import` source
- [x] Remove `SEED_MATCH_THRESHOLD` (no more seeds)
- [x] Update docstrings: 768-dim references corrected to 384-dim (MiniLM-L12-v2)
- [x] Add `anchors` param to `classify_mentions_to_anchors()` (pre-load support for Phase 2)
- [x] Document vector DB design decision in module docstring (PostgreSQL JSONB for anchors, Qdrant for primary data)

---

## Phase 1: Remove Hardcoded Seeds

**Status**: Done (2026-02-05)
**Files**: `pipline/seeds/`, `pipline/seed_anchors.py`

- [x] Delete `pipline/seeds/coffee_shop.py`
- [x] Delete `pipline/seeds/__init__.py`
- [x] Delete `pipline/seed_anchors.py`
- [x] Remove `pipline/seeds/` directory
- [x] Verify no other files import from these (only self-references + anchor_manager stats)
- [x] Update `database.py` AnchorExample docstring (seeds -> OS imports)

---

## Phase 2: Wire Anchors into Clustering Pipeline

**Status**: Done (2026-02-05)
**Files**: `pipline/clustering_job.py`, `pipline/anchor_manager.py`

- [x] Add `import_anchors` and `is_recluster` params to `run_clustering_job()`
- [x] Add Step 2.5: Anchor pre-classification between separation and HDBSCAN
- [x] Modify `classify_mentions_to_anchors()` to accept optional `anchors` param (done in Phase 0)
- [x] Create `build_anchor_matched_hierarchy()` function (groups by anchor, deduplicates products)
- [x] Create `_merge_hierarchies()` helper (anchor priority, name-based dedup)
- [x] Modify HDBSCAN steps 3 & 4 to use only unmatched items
- [x] Handle `is_recluster=True` — skips existing-draft guard, deletes old draft in `save_draft_taxonomy()`
- [x] Cold start (no anchors) → `all_anchors` empty → skip classification → pure HDBSCAN (identical)
- [x] `process_clustering_message()` uses defaults (import_anchors=None, is_recluster=False) — backward compatible

**Architecture note**: Anchor centroids stored in PostgreSQL JSONB (384-dim), NOT in Qdrant.
Mentions fetched from Qdrant MENTIONS_COLLECTION, classified against anchors in-memory via cosine similarity.

---

## Phase 3: Auto-Learn on Publish

**Status**: Done (2026-02-05)
**Files**: `pipline/api.py`, `pipline/anchor_manager.py`

- [x] Hook `learn_from_approved_taxonomy()` into `publish_taxonomy()` endpoint (after `session.commit()`, non-blocking try/except)
- [x] Fix mention query to check both `discovered_category_id` and `resolved_category_id` (using `or_()`)
- [x] Import `or_` from sqlalchemy, `TaxonomyProduct` from database
- [x] Add product text collection for product categories (`has_products=True`) — queries approved `TaxonomyProduct`, collects `canonical_text` + `variants`
- [x] Product texts added as `AnchorExample` entries in both existing-anchor and new-anchor paths
- [x] Centroid recomputed after adding product text examples
- [x] Early-exit relaxed: skips category only if BOTH mentions and product_texts are empty

---

## Phase 4: JSON Import API + Re-Clustering

**Status**: Done (2026-02-05)
**Files**: `pipline/api.py`, `pipline/anchor_manager.py`, `pipline/database.py`

### 4A: anchor_manager.py
- [x] Add `generate_anchors_from_import()` function — collects example texts + product names/variants, generates embeddings, computes centroids, returns anchor dicts matching `load_anchors_for_business()` format with `source="import"`

### 4B: api.py
- [x] Add Pydantic models: `ImportProductItem`, `ImportCategoryItem`, `TaxonomyImportRequest`
- [x] Add `POST /api/onboarding/taxonomies/{taxonomy_id}/import` endpoint
- [x] Endpoint: validates draft status, deletes all existing categories/products, clears mention links, creates imported categories/products (`source="imported"`, `is_approved=True`), logs action, queues re-clustering via `BackgroundTasks`
- [x] Background `run_recluster()` calls `run_clustering_job(import_anchors=..., is_recluster=True)` and clears `is_reclustering` flag on completion

### 4C: database.py
- [x] Add `source = Column(String(20), default="discovered")` to `TaxonomyCategory` (values: discovered, imported, manual)
- [x] Add `source = Column(String(20), default="discovered")` to `TaxonomyProduct` (same values)
- [x] Add `is_reclustering = Column(Boolean, default=False)` to `PlaceTaxonomy`

---

## Phase 5: Import UI in Onboarding Portal

**Status**: Pending
**Files**: `onboarding-portal/src/`

### 5A: api.ts
- [ ] Add `ImportCategory`, `ImportProduct`, `TaxonomyImportData` types
- [ ] Add `importTaxonomy()` API function

### 5B: ImportModal.tsx
- [ ] Create modal component with file upload
- [ ] JSON validation and schema checking
- [ ] Preview (category count, product count)
- [ ] "Import & Re-cluster" button with warning

### 5C: page.tsx
- [ ] Add Import button (visible only for draft taxonomies)
- [ ] Wire ImportModal open/close state
- [ ] Handle import success + re-clustering indicator

---

## Change Log

| Date | Phase | Change |
|------|-------|--------|
| 2026-02-05 | - | Plan created and approved |
| 2026-02-05 | 0 | Fixed EmbeddingClient import bug, updated thresholds, added anchors param to classify |
| 2026-02-05 | 1 | Deleted seeds/coffee_shop.py, seeds/__init__.py, seed_anchors.py, seeds/ dir |
| 2026-02-05 | 2 | Wired anchor classification into clustering pipeline, added build_anchor_matched_hierarchy, _merge_hierarchies, is_recluster support |
| 2026-02-05 | 3 | Hooked auto-learn into publish_taxonomy (non-blocking), fixed mention query (or_ for both category IDs), added product text collection for product categories |
| 2026-02-05 | 4 | Added generate_anchors_from_import(), import endpoint with Pydantic models, background re-clustering, source column on TaxonomyCategory/Product, is_reclustering on PlaceTaxonomy |
