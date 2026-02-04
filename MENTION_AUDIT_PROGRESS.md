# Mention Audit & Multi-Branch Taxonomy - Progress Tracker

**Started**: 2026-02-04
**Plan File**: `/home/42group/nurliya/MENTION_AUDIT_PLAN.md`
**Related Bugs**: BUG-014, FEATURE-001

---

## Status Summary

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| Phase 1 | BUG-014: Vector similarity search | ✅ Complete | Backend + Frontend done |
| Phase 2 | FEATURE-001: Schema changes | ✅ Complete | Migration ready, needs deploy |
| Phase 3 | Multi-place query support | ✅ Complete | All queries updated |
| Phase 4 | Combined clustering | ✅ Complete | Needs Docker rebuild to test |

---

## Phase 1: BUG-014 Fix (Vector Similarity Search)

**Goal**: Make "below threshold" mentions show similar items, not all unresolved.

| Task | Status | Notes |
|------|--------|-------|
| Add `_get_product_embedding()` helper | ✅ Completed | api.py:939-973 |
| Add `_get_category_embedding()` helper | ✅ Completed | api.py:976-988 |
| Refactor `get_product_mentions()` | ✅ Completed | api.py:1011-1148, uses vector_store.search_similar() |
| Refactor `get_category_mentions()` | ✅ Completed | api.py:1151-1275, uses vector_store.search_similar() |
| Update MentionPanel.tsx for scores | ✅ Completed | Shows "X% similar" badge with color gradient |
| Test: Different products → different results | ⏳ Deploy | Needs Docker rebuild to test |
| Test: Cross-lingual matching | ⏳ Deploy | Needs Docker rebuild to test |

### Phase 1 Verification Checklist

- [ ] Product "Spanish Latte" returns different below-threshold than "V60"
- [ ] Similarity scores are 0.60-1.0 (not just 0.0 or 1.0)
- [ ] Arabic mentions like "سبانش" appear for "Spanish Latte"
- [ ] No regression: Matched mentions still work correctly

---

## Phase 2: FEATURE-001 Schema Changes

**Goal**: Add `place_ids` and `scrape_job_id` to PlaceTaxonomy.

| Task | Status | Notes |
|------|--------|-------|
| Add columns to database.py | ✅ Completed | PlaceTaxonomy model updated |
| Add `all_place_ids` helper property | ✅ Completed | Backward-compatible accessor |
| Add `scrape_job` relationship | ✅ Completed | Links to ScrapeJob |
| Create SQL migration | ✅ Completed | `migrations/001_add_multi_branch_taxonomy.sql` |
| Add GIN index for place_ids | ✅ Completed | In migration file |
| Backfill existing taxonomies | ✅ Completed | In migration file |
| Test migration on dev | ⏳ Deploy | Needs Docker + psql |
| Deploy migration to prod | ⬜ Pending | After dev testing |

### Schema Changes

**Migration file**: `pipline/migrations/001_add_multi_branch_taxonomy.sql`

```sql
-- Adds:
ALTER TABLE place_taxonomies ADD COLUMN place_ids UUID[];
ALTER TABLE place_taxonomies ADD COLUMN scrape_job_id UUID REFERENCES scrape_jobs(id);
CREATE INDEX ix_place_taxonomies_place_ids ON place_taxonomies USING GIN (place_ids);
UPDATE place_taxonomies SET place_ids = ARRAY[place_id] WHERE place_ids IS NULL;
```

### Queries to Update (Phase 3)

| File | Line | Current | Needs Update |
|------|------|---------|--------------|
| `clustering_job.py` | 146 | `filter_by(place_id=X)` | Check `place_ids.any(X)` too |
| `api.py` | 2368 | `place_id == X` | Check `place_ids.any(X)` too |

---

## Phase 3: Multi-Place Query Support

**Goal**: Make Phase 1 fix work across multiple places.

| Task | Status | Notes |
|------|--------|-------|
| Update `search_similar()` for place_ids | ✅ Completed | Added `place_ids` param with `MatchAny` |
| Update `get_product_mentions()` for place_ids | ✅ Completed | Uses `taxonomy.all_place_ids` |
| Update `get_category_mentions()` for place_ids | ✅ Completed | Uses `taxonomy.all_place_ids` |
| Update `clustering_job.py` taxonomy lookup | ✅ Completed | Uses `or_(place_id, place_ids.any())` |
| Update `api.py` pipeline status lookup | ✅ Completed | Uses `or_(place_id, place_ids.any())` |
| Test: Shared taxonomy queries both places | ⏳ Deploy | Needs migration + Docker rebuild |

---

## Phase 4: Combined Clustering

**Goal**: Create shared taxonomy for multi-branch businesses.

| Task | Status | Notes |
|------|--------|-------|
| Update `scroll_all_vectors()` | ✅ Completed | Added `place_ids` param with `MatchAny` |
| Update `count_vectors()` | ✅ Completed | Added `place_ids` param with `MatchAny` |
| Modify `trigger_taxonomy_clustering()` | ✅ Completed | Detects multi-branch, gathers all place_ids |
| Update `run_clustering_job()` | ✅ Completed | Accepts `place_ids` and `scrape_job_id` |
| Update `save_draft_taxonomy()` | ✅ Completed | Sets `place_ids` and `scrape_job_id` on taxonomy |
| Update `process_clustering_message()` | ✅ Completed | Reads and passes `place_ids`/`scrape_job_id` |
| Test: Multi-branch → ONE taxonomy | ⏳ Deploy | Needs Docker rebuild |
| Test: Better cluster quality | ⏳ Deploy | More data points |

---

## Implementation Log

### 2026-02-04 - Phase 1 Backend Implementation Complete

**Changes to `pipline/api.py`:**

1. **Added `_get_product_embedding()` helper** (lines 938-968):
   - Retrieves embedding from PRODUCTS_COLLECTION via `client.retrieve()`
   - Fallback: Generates embedding from canonical_text + variants using `embedding_client.generate_embeddings()`
   - Returns averaged embedding for variant matching

2. **Added `_get_category_embedding()` helper** (lines 971-983):
   - Uses stored `centroid_embedding` from BUG-006 fix
   - Fallback: Generates from category name

3. **Refactored `get_product_mentions()`** (lines 1005-1148):
   - Now uses `vector_store.search_similar()` with product embedding
   - Searches MENTIONS_COLLECTION for similar unresolved mentions
   - Filters to 0.55-0.80 similarity range ("near misses")
   - Returns actual similarity scores instead of 0.0
   - Results sorted by similarity score descending

4. **Refactored `get_category_mentions()`** (lines 1151-1275):
   - Same pattern as products but for aspect mentions
   - Uses category centroid_embedding for similarity search

**Key implementation details:**
- Threshold: 0.55 lower bound, 0.80 upper bound for "below threshold"
- Matches found via `qdrant_point_id` on RawMention
- Excludes already-matched mentions from results
- Graceful fallback to old behavior if embedding unavailable

**Syntax verified:** `python3 -m py_compile api.py` passed

**Frontend updated:** `MentionPanel.tsx`
- Shows "X% similar" badge with actual similarity score
- Color gradient: 70%+ (bright), 60%+ (medium), <60% (muted)
- Shows "Matched" badge for 100% matches

**Phase 1 Complete** - Ready for Docker rebuild and testing.

---

### 2026-02-04 - Phase 2 Schema Implementation Complete

**Changes to `pipline/database.py`:**

1. **Added `place_ids` column** to PlaceTaxonomy:
   - Type: `ARRAY(UUID(as_uuid=True))`
   - Purpose: Store all place IDs for multi-branch shared taxonomies
   - NULL means single-place (use `place_id` for backward compat)

2. **Added `scrape_job_id` column** to PlaceTaxonomy:
   - Type: `UUID` with FK to `scrape_jobs(id)`
   - Purpose: Link taxonomy to parent scrape job

3. **Added `scrape_job` relationship**:
   - Links PlaceTaxonomy to ScrapeJob model

4. **Added `all_place_ids` property**:
   - Returns `place_ids` if set, otherwise `[place_id]`
   - Provides backward-compatible access for queries

**Created migration file**: `pipline/migrations/001_add_multi_branch_taxonomy.sql`
- Adds columns with `IF NOT EXISTS`
- Creates GIN index for efficient array queries
- Creates index on scrape_job_id
- Backfills existing taxonomies with `place_ids = ARRAY[place_id]`
- Includes rollback commands

**Identified queries needing Phase 3 updates:**
- `clustering_job.py:146` - taxonomy existence check
- `api.py:2368` - taxonomy lookup by place

**Phase 2 Complete** - Migration ready for deployment.

---

### 2026-02-04 - Phase 3 Multi-Place Query Support Complete

**Changes to `pipline/vector_store.py`:**

1. **Updated `search_similar()` function**:
   - Added `place_ids: Optional[List[str]]` parameter
   - Uses `MatchAny` for multiple places (OR condition)
   - Falls back to `MatchValue` for single place
   - Backward compatible with `place_id` parameter

**Changes to `pipline/api.py`:**

1. **Updated `get_product_mentions()`**:
   - Uses `taxonomy.all_place_ids` instead of single `place_id`
   - Passes `place_ids` to `search_similar()`
   - Fallback query uses `place_id.in_()` for multi-place

2. **Updated `get_category_mentions()`**:
   - Same changes as products

3. **Updated `_get_place_pipeline_status()`** (line 2375):
   - Taxonomy lookup now uses `or_(place_id, place_ids.any())`

**Changes to `pipline/clustering_job.py`:**

1. **Added import**: `from sqlalchemy import or_`

2. **Updated `is_clustering_needed()`** (line 147):
   - Taxonomy existence check now uses `or_(place_id, place_ids.any())`
   - Works for both single-place and shared taxonomies

**Key implementation details:**
- All queries now check both `place_id` (legacy) and `place_ids.any()` (multi-branch)
- Vector search uses `MatchAny` for efficient OR filtering in Qdrant
- Backward compatible - works with existing single-place taxonomies

**Syntax verified:** All three files pass `py_compile`

**Phase 3 Complete** - Ready for Phase 4 (combined clustering).

---

### 2026-02-04 - Code Review Fixes

**Issues found and fixed:**

| Issue | File | Fix |
|-------|------|-----|
| Inline `or_` import | `api.py:2376` | Moved to top-level import at line 14 |
| Unresolved count single-place | `clustering_job.py:163` | Now uses `existing.all_place_ids` for multi-branch |

**Changes:**
1. `api.py:14` - Added `or_` to sqlalchemy import
2. `api.py:2375` - Removed inline `from sqlalchemy import or_`
3. `clustering_job.py:163-173` - Updated unresolved count to query across all places in shared taxonomy

**Syntax verified:** Both files pass `py_compile`

---

### 2026-02-04 - Phase 4 Combined Clustering Implementation

**Changes to `pipline/vector_store.py`:**

1. **Updated `scroll_all_vectors()` function**:
   - Added `place_ids: Optional[List[str]]` parameter
   - Uses `MatchAny` for multiple places (OR condition)
   - Falls back to `MatchValue` for single place
   - Backward compatible with `place_id` parameter
   - Updated logging to reflect multi-place

2. **Updated `count_vectors()` function**:
   - Added `place_ids: Optional[List[str]]` parameter
   - Same pattern as `scroll_all_vectors()`

**Changes to `pipline/clustering_job.py`:**

1. **Updated `trigger_taxonomy_clustering()`** (lines 192-280):
   - Detects if job is part of multi-place scrape via `ScrapeJob.pipeline_job_ids`
   - Gathers all `place_ids` from sibling jobs
   - Includes `place_ids` and `scrape_job_id` in queue message

2. **Updated `run_clustering_job()`** (lines 827-1005):
   - New signature: accepts `place_ids` and `scrape_job_id` parameters
   - Uses `scroll_all_vectors(place_ids=...)` to gather from ALL places
   - Counts reviews sampled across all places
   - Passes parameters to `save_draft_taxonomy()`

3. **Updated `save_draft_taxonomy()`** (lines 649-824):
   - New signature: accepts `place_ids` and `scrape_job_id` parameters
   - Checks for existing draft across ALL places (array overlap)
   - Sets `PlaceTaxonomy.place_ids` and `PlaceTaxonomy.scrape_job_id`
   - Only sets `place_ids` if multiple places (backward compat)

4. **Updated `process_clustering_message()`** (lines 1008-1046):
   - Reads `place_ids` and `scrape_job_id` from message
   - Passes to `run_clustering_job()`
   - Logs multi-place info

**Key implementation details:**
- Single-place clustering still works (backward compatible)
- Multi-branch scrapes create ONE shared taxonomy
- Taxonomy linked to all places via `place_ids` array
- More data points = better HDBSCAN cluster quality

**Syntax verified:** `python3 -m py_compile` passed for both files

---

### 2026-02-04 - Phase 4 Code Review Fix

**Issue found during review:**

The array overlap check in `save_draft_taxonomy()` used `.op('&&')` which may not correctly convert Python list to PostgreSQL array:

```python
# Before (problematic):
existing = session.query(PlaceTaxonomy).filter(
    or_(
        PlaceTaxonomy.place_id.in_(place_uuids),
        PlaceTaxonomy.place_ids.op('&&')(place_uuids)  # May not work correctly
    ),
    PlaceTaxonomy.status == "draft",
).first()
```

**Fix applied:**

Changed to use multiple `.any()` calls which is the safe SQLAlchemy approach:

```python
# After (safe):
overlap_conditions = [PlaceTaxonomy.place_id.in_(place_uuids)]
for p_uuid in place_uuids:
    overlap_conditions.append(PlaceTaxonomy.place_ids.any(p_uuid))

existing = session.query(PlaceTaxonomy).filter(
    or_(*overlap_conditions),
    PlaceTaxonomy.status == "draft",
).first()
```

**Syntax verified:** `python3 -m py_compile` passed

**Phase 4 Complete** - Ready for Docker rebuild and testing.

---

### 2026-02-04 - BUG FIX: Job Progress Counter Not Incremented

**Issue Discovered:**
During testing of multi-branch scrape (Specialty Bean Roastery), the Al Khobar job got stuck at 923/989 reviews (66 reviews missing). Manual intervention was required to complete the job.

**Root Cause Analysis:**

Investigated `worker.py` and found **two code paths** where messages are consumed but `update_job_progress()` is never called:

| Location | Condition | Action | Bug |
|----------|-----------|--------|-----|
| Line 680-683 | Review not found in DB | `basic_ack()` + return | No progress update |
| Line 784 | Max retries exceeded | `basic_nack(requeue=False)` + return | No progress update |

Both paths permanently consume the message (either ACK or dead-letter) without incrementing `job.processed_reviews`. This causes the job to get stuck forever since `total_reviews` can never be reached.

**Other paths (OK):**
- Line 771: Rate limit → `basic_nack(requeue=True)` - OK, message will be reprocessed
- Line 826: Generic exception → `basic_nack(requeue=True)` - OK, message will be reprocessed

**Fix Applied:**

```python
# Fix 1: Line 683 - Review not found
ch.basic_ack(delivery_tag=method.delivery_tag)
update_job_progress(job_id)  # BUG FIX: Must update progress even for missing reviews
return

# Fix 2: Line 785 - Dead-letter after max retries
ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
update_job_progress(job_id)  # BUG FIX: Must update progress even for dead-lettered reviews
return
```

**Impact:**
- Jobs will now complete correctly even if some reviews fail
- 66 reviews (or any failed reviews) won't cause job to get stuck
- Dead-lettered reviews are still logged for debugging but don't block job completion

**Files Modified:**
- `pipline/worker.py` - Added `update_job_progress()` calls to two error paths

**Syntax verified:** `python3 -m py_compile worker.py` passed

---

### 2026-02-04 - Analysis Complete

**BUG-014 Root Cause Identified:**
- Location: `api.py:980-993` (products), `api.py:1062-1073` (categories)
- Problem: Query returns ALL unresolved mentions, no vector similarity
- Every product/category shows identical "below threshold" data

**FEATURE-001 Gap Identified:**
- PlaceTaxonomy has single `place_id`, needs `place_ids` array
- Clustering creates separate taxonomy per place
- BUG-013 fix already waits for all jobs (infrastructure ready)

**Relationship Documented:**
- BUG-014 fix benefits from FEATURE-001 (multi-place queries)
- FEATURE-001 requires schema migration first
- Combined implementation provides best UX

**Files Analyzed:**
- `pipline/api.py:957-1116` - Mention audit endpoints
- `pipline/database.py:194-294` - Taxonomy models
- `pipline/clustering_job.py:78-197` - Clustering logic
- `pipline/vector_store.py:436-515` - Vector search functions

**Plan Created:**
- `/home/42group/nurliya/MENTION_AUDIT_PLAN.md`

---

## Legend

- ⬜ Pending
- 🔄 In Progress
- ✅ Completed
- ⏸️ Blocked
- ❌ Cancelled

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `pipline/api.py` | Mention audit endpoints (lines 957-1116) |
| `pipline/vector_store.py` | Vector search functions |
| `pipline/database.py` | PlaceTaxonomy model (lines 194-215) |
| `pipline/clustering_job.py` | Clustering trigger and execution |
| `onboarding-portal/src/components/MentionPanel.tsx` | UI for mention audit |
| `onboarding-portal/src/lib/api.ts` | API client |

---

## Dependencies

```
Phase 1 (BUG-014)
    │
    ├─ Requires: BUG-006 centroid_embedding ✅ Already done
    │
    └─► Phase 2 (Schema)
            │
            └─► Phase 3 (Multi-place queries)
                    │
                    └─► Phase 4 (Combined clustering)
```

---

## Notes

_Add implementation notes, blockers, and decisions here as work progresses._

### Open Questions

1. **Phase 4 Trigger**: When multiple places complete, which job triggers clustering?
   - Current: Last completing job triggers
   - Proposed: Same behavior, but detect multi-branch and gather all place_ids

2. **Existing Taxonomies**: How to handle existing separate taxonomies when FEATURE-001 deployed?
   - Option A: Leave separate, only new scrapes get shared
   - Option B: Provide merge tool for OS to combine existing

3. **Place Count Limit**: Should there be a max places per shared taxonomy?
   - Proposed: No limit initially, monitor performance

---

*Progress tracker created: 2026-02-04*
*Last updated: 2026-02-04*
