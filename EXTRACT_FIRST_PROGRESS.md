# Extract-First Pipeline Refactor - Progress Tracker

## Status: Deployed - Ready for Testing

**Started**: 2026-02-03
**Plan File**: `/home/42group/nurliya/EXTRACT_FIRST_PLAN.md`

---

## Tasks

### Step 1: Add analyze_with_taxonomy() to llm_client.py

| Task | Status | Notes |
|------|--------|-------|
| Add `TAXONOMY_AWARE_PROMPT` constant | ✅ Completed | Lines 309-350 |
| Add `analyze_with_taxonomy()` function | ✅ Completed | Lines 366-471 |
| Add helper to format products/categories for prompt | ✅ Completed | `_format_taxonomy_for_prompt()` lines 353-364 |

---

### Step 2: Modify Worker Flow (worker.py)

| Task | Status | Notes |
|------|--------|-------|
| Add `mode` parameter handling in `process_message()` | ✅ Completed | Lines 656-660 |
| Add taxonomy fetching for sentiment mode | ✅ Completed | Lines 673-689 |
| Add `get_active_taxonomy_for_place()` helper | ✅ Completed | Lines 39-44 |
| Add `get_approved_products_for_taxonomy()` helper | ✅ Completed | Lines 47-63 |
| Add `get_approved_categories_for_taxonomy()` helper | ✅ Completed | Lines 66-80 |
| Modify flow to use `analyze_with_taxonomy()` | ✅ Completed | Lines 697-707 |

---

### Step 3: Trigger After Publish (api.py)

| Task | Status | Notes |
|------|--------|-------|
| Add `rabbitmq` import for `get_channel`, `publish_message` | ✅ Completed | Line 26 |
| Modify `publish_taxonomy()` to queue sentiment analysis | ✅ Completed | Lines 1347-1374 |
| Add review queueing logic | ✅ Completed | Queries reviews without analysis, queues with mode="sentiment" |

---

### Step 4: Default to Extraction-Only

| Task | Status | Notes |
|------|--------|-------|
| Modify scrape job creation to default to extraction mode | ⬜ Pending | |
| Update orchestrator if needed | ⬜ Pending | |

---

### Step 5: Testing

| Task | Status | Notes |
|------|--------|-------|
| Test extraction-only mode | ⬜ Pending | |
| Test sentiment after publish | ⬜ Pending | |
| Test summary quality (product names) | ⬜ Pending | |
| Test fallback when no taxonomy | ⬜ Pending | |

---

### Step 6: Deployment

| Task | Status | Notes |
|------|--------|-------|
| Rebuild API container | ✅ Completed | 2026-02-03 09:12 UTC |
| Rebuild Worker containers | ✅ Completed | 2026-02-03 09:12 UTC |
| Commit and push | ⬜ Pending | Waiting for testing |
| Update TAXONOMY_PROGRESS.md | ⬜ Pending | |

---

## Legend

- ⬜ Pending
- 🔄 In Progress
- ✅ Completed
- ⏸️ Blocked
- ❌ Cancelled

---

## Files Modified

| File | Lines Added | Purpose |
|------|-------------|---------|
| `pipline/llm_client.py` | ~165 | TAXONOMY_AWARE_PROMPT + analyze_with_taxonomy() + _format_taxonomy_for_prompt() |
| `pipline/worker.py` | ~60 | Mode handling + taxonomy fetching helpers + analyze_with_taxonomy() integration |
| `pipline/api.py` | ~30 | Import rabbitmq + queue reviews after publish |

---

## Implementation Log

### 2026-02-03 - Planning Complete

- Identified current flow issue: sentiment before extraction
- Designed two-phase approach: extraction → approval → sentiment
- Key insight: LLM should know approved products/categories when analyzing
- Created EXTRACT_FIRST_PLAN.md and EXTRACT_FIRST_PROGRESS.md

### 2026-02-03 - Implementation Complete

**llm_client.py:**
- Added `TAXONOMY_AWARE_PROMPT` constant (lines 309-360)
- Added `_format_taxonomy_for_prompt()` helper (lines 363-382)
- Added `analyze_with_taxonomy()` function (lines 385-520)
- LLM receives approved products/categories and matches review to them
- LLM returns per-item sentiment for matched products/categories
- Falls back to original `analyze_review()` on error

**worker.py:**
- Added `get_active_taxonomy_for_place()` helper (lines 39-44)
- Added `get_approved_products_for_taxonomy()` helper (lines 47-66)
- Added `get_approved_categories_for_taxonomy()` helper (lines 69-87)
- Modified `process_message()` to support modes: "extraction", "sentiment", "full"
- When taxonomy exists, uses `analyze_with_taxonomy()` for better context

**api.py:**
- Added import for `get_channel`, `publish_message` from rabbitmq
- Modified `publish_taxonomy()` to queue reviews for sentiment analysis after publish
- Only queues reviews that don't have existing analysis
- Fixed N+1 query by using Review.job_id directly

### 2026-02-03 - Code Review Fixes

| Issue | Fix |
|-------|-----|
| Topics backward compat assigned ALL categories to one sentiment | Changed prompt to return per-item sentiment; updated handling |
| N+1 query in publish_taxonomy | Use Review.job_id directly instead of querying Job |

### 2026-02-03 - Deployment Complete

- Docker images rebuilt with cache (13.1GB each due to torch/nvidia deps)
- API container restarted successfully
- Worker containers (x2) restarted successfully
- All services healthy and listening on queues
- Note: Image size optimization identified for future work (use CPU-only torch, add .dockerignore)
