# Learning System — Close the Gaps

**Date:** 2026-02-07
**Branch:** `feature/taxonomy-system`
**Status:** In Progress

---

## Problem Statement

The Nurliya learning system operates at ~60% capacity due to 5 disconnected gaps:

- **Loop 1 (Anchors/PostgreSQL):** Corrections → anchor centroids → better category CLASSIFICATION. **Works.**
- **Loop 2 (Products/Qdrant):** Publish → index embeddings → mention MATCHING. **Static between publishes.**

Archives are written but never read. Business types are raw strings causing anchor fragmentation. Rejected categories leave polluted anchors. Discarded drafts leave orphaned examples.

---

## How Learning Works (Algorithm)

1. **Embeddings:** Every mention text → 384-dim vector via `paraphrase-multilingual-MiniLM-L12-v2`
2. **Anchor Creation:** On taxonomy publish, collect all mention texts per category → compute centroid (mean of embeddings) → store as anchor
3. **Classification:** For new mentions, cosine similarity against anchor centroids. Score ≥ 0.80 → known category. Score < 0.80 → HDBSCAN discovery
4. **Correction Weighting:** Human corrections are added as 2x-weighted examples, shifting centroid toward user intent
5. **HDBSCAN Discovery:** Unmatched mentions clustered by density in vector space, then LLM labels each cluster

No neural network training. Vector arithmetic + density clustering + pre-trained embeddings.

---

## Implementation Order

| # | Gap | Impact | Depends On |
|---|-----|--------|------------|
| 1 | Business type normalization | Prerequisite | — |
| 2 | Corrections update Qdrant | HIGH | Gap 1 |
| 3 | Anchor cleanup on rejection | MEDIUM | Gap 1 |
| 4 | Orphaned anchor cleanup | MEDIUM | Gap 1 |
| 5 | Archives as learning input | MEDIUM | Gap 1 |

---

## Gap 1: Normalize Business Types

**Problem:** `place.category` stores raw Google Maps strings ("Coffee shop", "مقهى", "Cafe"). Same anchor fragmentes under multiple keys.

**Solution:**
- Add `BUSINESS_TYPE_MAP` lookup dict + `normalize_business_type()` function to `anchor_manager.py`
- Maps: "coffee shop"/"cafe"/"مقهى"/"كوفي شوب" → `"cafe"`, etc.
- Update all 3 call sites (anchor_manager L231, L755; clustering_job L1385)
- Migration `003_normalize_business_types.sql` to fix existing rows

**Files:** `pipline/anchor_manager.py`, `pipline/clustering_job.py`, `pipline/migrations/003_normalize_business_types.sql`

---

## Gap 2: Corrections Update Qdrant PRODUCTS_COLLECTION

**Problem:** `bulk_move_mentions` updates anchors but Qdrant `PRODUCTS_COLLECTION` stays frozen until next publish.

**Solution:**
- Add `update_product_vectors_from_corrections()` to `anchor_manager.py`
- Only fires when `taxonomy.status == 'active'`
- Generates embeddings for moved mention texts → upserts as new points in PRODUCTS_COLLECTION
- Uses uuid4() point IDs (race-condition safe)
- Wrapped in try/except (non-blocking)

**Files:** `pipline/anchor_manager.py`, `pipline/api.py`, `pipline/vector_store.py`

---

## Gap 3: Anchor Cleanup on Rejection

**Problem:** Rejected categories leave anchor examples that attract mentions into rejected categories.

**Solution:**
- Add `remove_anchor_examples_for_taxonomy()` to `anchor_manager.py`
- Only removes examples matching the specific taxonomy_id (preserves cross-place anchors)
- If anchor becomes empty and is correction/learned source → delete it
- Seed/import anchors are never deleted
- Wire into category reject and product reject actions in `api.py`

**Files:** `pipline/anchor_manager.py`, `pipline/api.py`

---

## Gap 4: Orphaned Anchor Cleanup

**Problem:** Draft corrections create AnchorExamples. If draft is discarded, examples become orphans.

**Solution:**
- Add `cleanup_orphaned_examples()` to `anchor_manager.py`
- Only removes `source='correction'` examples (learned from publish are kept)
- Wire into `import_taxonomy` endpoint, after archive + before re-cluster

**Files:** `pipline/anchor_manager.py`, `pipline/api.py`

---

## Gap 5: Archives as Learning Input

**Problem:** `taxonomy_archives` stores JSONB snapshots but nothing reads them for learning.

**Solution:**
- Add `load_anchors_from_archive()` to `anchor_manager.py`
- Reads most recent active archive for the place
- Extracts approved categories → generates centroid embeddings → returns as anchor dicts
- Add `ARCHIVE_MATCH_THRESHOLD = 0.75` (between learned 0.80 and import 0.70)
- Inject into clustering flow in `clustering_job.py` with deduplication against existing db_anchors

**Files:** `pipline/anchor_manager.py`, `pipline/clustering_job.py`

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `pipline/anchor_manager.py` | +5 functions, +2 constants, +1 dict, update 3 call sites, update classify_to_anchor |
| `pipline/api.py` | Wire 4 new calls: bulk_move, category reject, product reject, import_taxonomy |
| `pipline/vector_store.py` | Update type hint on upsert_vectors_batch |
| `pipline/clustering_job.py` | Normalize business_type, inject archive anchors |
| `pipline/migrations/003_normalize_business_types.sql` | New: normalize existing anchor rows |

No new tables. All changes use existing models.
