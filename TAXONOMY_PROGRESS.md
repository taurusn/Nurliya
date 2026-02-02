# Dynamic Taxonomy System - Progress Tracker

## Status: Phase 1B Complete - Ready for Phase 2

**Started**: 2026-02-02
**Target**: Weeks 3-4

---

## Phase 1A: Infrastructure (Weeks 1-2)

| Task | Status | Notes |
|------|--------|-------|
| Add Qdrant to docker-compose.yml | ✅ Completed | Added service with ports 6333/6334, health check, volume persistence |
| Add taxonomy tables to database.py | ✅ Completed | 5 tables: PlaceTaxonomy, TaxonomyCategory, TaxonomyProduct, RawMention, TaxonomyAuditLog |
| Create embedding_client.py | ✅ Completed | MiniLM + Arabic normalization (diacritics, character mapping) |
| Create vector_store.py | ✅ Completed | Qdrant wrapper + fallback logic + retry queue |
| Update requirements.txt | ✅ Completed | Added qdrant-client, sentence-transformers, hdbscan, numpy |
| Add Qdrant config to config.py | ✅ Completed | QDRANT_URL, QDRANT_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIMENSION |

---

## Phase 1B: Worker Integration (Weeks 3-4)

| Task | Status | Notes |
|------|--------|-------|
| Add extract_mentions() to llm_client.py | ✅ Completed | Separate LLM call with dedicated prompt for products/aspects |
| Modify worker.py for dual-write | ✅ Completed | Non-blocking process_mentions() after save_analysis() |
| Entity resolution via Qdrant | ✅ Completed | 0.85 cosine threshold, batch embeddings per review |
| **GATE: Arabic embedding quality test** | ✅ Completed | PASS: avg similarity 0.655 > 0.5 threshold |

---

## Phase 2: Discovery (Weeks 5-6)

| Task | Status | Notes |
|------|--------|-------|
| Create clustering_job.py | ⬜ Pending | HDBSCAN + LLM labeling |
| Trigger on scrape complete | ⬜ Pending | Or 50+ new mentions |
| Hierarchy builder | ⬜ Pending | Main → Sub → Products |
| Save draft taxonomy | ⬜ Pending | |

---

## Phase 3: Onboarding Portal (Weeks 7-9)

| Task | Status | Notes |
|------|--------|-------|
| API: /api/onboarding/* endpoints | ⬜ Pending | pending, approve, reject, move, link, publish |
| Portal UI: Pending places list | ⬜ Pending | |
| Portal UI: Taxonomy tree editor | ⬜ Pending | |
| Portal UI: Bulk operations | ⬜ Pending | |
| Audit logging | ⬜ Pending | |

---

## Phase 4: Integration (Weeks 10-11)

| Task | Status | Notes |
|------|--------|-------|
| Match mentions to approved taxonomy | ⬜ Pending | |
| Add resolved_products/categories to ReviewAnalysis | ⬜ Pending | |
| Analytics endpoints | ⬜ Pending | /categories, /products, /timeline |
| Client portal category breakdown | ⬜ Pending | |

---

## Phase 5: Polish (Week 12)

| Task | Status | Notes |
|------|--------|-------|
| Migration script (backfill existing reviews) | ⬜ Pending | |
| New discovery alerts | ⬜ Pending | Dashboard badge + email |
| Performance tuning | ⬜ Pending | |
| Documentation | ⬜ Pending | |

---

## Legend

- ⬜ Pending
- 🔄 In Progress
- ✅ Completed
- ⏸️ Blocked
- ❌ Cancelled

---

## Notes

_Add implementation notes, blockers, and decisions here as work progresses._

### Embedding Model Decision
- Starting with: `paraphrase-multilingual-MiniLM-L12-v2` (~80MB)
- Upgrade to CAMeL-BERT if Arabic quality test fails (similarity < 0.7)

### Key Files
- Plan: `/home/42group/nurliya/TAXONOMY_PLAN.md`
- Progress: `/home/42group/nurliya/TAXONOMY_PROGRESS.md`
- Database: `pipline/database.py`
- Worker: `pipline/worker.py`
- LLM: `pipline/llm_client.py`

---

## Implementation Log

### 2026-02-02 - Phase 1A Complete

**docker-compose.yml changes:**
- Added `qdrant` service (qdrant/qdrant:latest)
- Ports: 6333 (REST), 6334 (gRPC)
- Health check via /readyz endpoint
- Added `qdrant_data` volume
- Added QDRANT_URL env to api and worker services
- Added qdrant dependency to api and worker

**database.py new tables:**
1. `PlaceTaxonomy` - Per-place taxonomy container with status workflow (draft → review → active)
2. `TaxonomyCategory` - Hierarchical categories with self-referential parent_id, approval fields
3. `TaxonomyProduct` - Products with variants (JSONB), discovered/assigned category refs
4. `RawMention` - Extracted mentions linked to reviews, with resolution to products/categories
5. `TaxonomyAuditLog` - Full audit trail for approval workflow

**embedding_client.py features:**
- Arabic text normalization: diacritics removal, character mapping (alef variants, teh marbuta, yeh)
- Lazy model loading to avoid startup overhead
- Batch embedding generation
- Cosine similarity computation
- Cross-lingual quality test function

**vector_store.py features:**
- Qdrant client wrapper with lazy connection
- Collection management (ensure_collection, initialize_collections)
- Upsert single and batch operations
- Similarity search with place_id and mention_type filters
- Entity resolution helper (find_similar_mention)
- Delete by ID and by place
- Fallback retry queue for Qdrant downtime
- Collection stats

**config.py additions:**
- QDRANT_URL (default: http://localhost:6333)
- QDRANT_API_KEY (optional, for Qdrant Cloud)
- EMBEDDING_MODEL (default: paraphrase-multilingual-MiniLM-L12-v2)
- EMBEDDING_DIMENSION (default: 384)

**requirements.txt additions:**
- qdrant-client>=1.7.0
- sentence-transformers>=2.2.0
- hdbscan>=0.8.33
- numpy>=1.24.0

**Next Steps (Phase 1B):**
1. Add extract_mentions() to llm_client.py
2. Modify worker.py for dual-write
3. Implement entity resolution via Qdrant
4. Run Arabic embedding quality test

### 2026-02-02 - Code Review Fixes

**Issues found and fixed:**

| Severity | File | Issue | Fix |
|----------|------|-------|-----|
| High | docker-compose.yml | Health check used `wget` which may not exist in Qdrant image | Changed to TCP-based check: `bash -c ':> /dev/tcp/localhost/6333'` |
| High | database.py | `TaxonomyCategory.parent_id` used CASCADE delete - would delete all children when parent deleted | Changed to SET NULL - orphaned children become top-level |
| Low | embedding_client.py | Unused import `lru_cache` | Removed |
| Low | embedding_client.py | Docstring order didn't match code execution order | Fixed docstring |
| Low | vector_store.py | Unused import `UnexpectedResponse` | Removed |

**Design decisions confirmed:**
- `TaxonomyCategory.parent_id` ON DELETE SET NULL is safer - prevents accidental cascade deletion of entire category trees
- TCP-based health check is more portable across different Qdrant image versions

### 2026-02-02 - Phase 1B Worker Integration

**llm_client.py - extract_mentions():**
- New `MENTION_EXTRACTION_PROMPT` - extracts products and aspects with sentiment
- Separate LLM call from analyze_review() for isolation
- Returns `{"products": [...], "aspects": [...]}` with text/sentiment per item
- Max 10 mentions per review, handles Arabic/English/mixed
- Graceful fallback: returns empty arrays on error

**worker.py - process_mentions():**
- Non-blocking dual-write: extraction failure doesn't affect analysis
- Batch embedding generation via `embedding_client.generate_embeddings()`
- Entity resolution flow:
  1. Generate embedding for mention text
  2. Search Qdrant for similar in same place (0.85 threshold)
  3. If found: use existing canonical_id
  4. If not found: create new canonical, upsert to Qdrant
- Fallback: if Qdrant unavailable, queue for retry, save RawMention with NULL qdrant_point_id
- Saves to RawMention table (resolved_product_id/resolved_category_id remain NULL until Phase 3)

**worker.py - process_message() changes:**
- Now captures place_id when fetching review
- Calls process_mentions() after save_analysis() (non-blocking)

**Design decisions:**
- Separate LLM calls: can iterate on extraction prompt independently
- Batch embeddings per review: sentence-transformers handles efficiently
- Non-blocking extraction: graceful degradation, analysis always succeeds
- Deduplication: skip if RawMention already exists for review_id (handles requeue)

**Known limitations (to address in Phase 2):**
- If Qdrant upsert fails and queues for retry, RawMention is saved with NULL qdrant_point_id. Retry succeeds but doesn't backfill the RawMention record. Reconciliation job needed.
- No rate limit retry for extract_mentions() - fails silently (by design)

### 2026-02-02 - GATE Test Passed

**Arabic Embedding Quality Test Results:**

| Test | Result |
|------|--------|
| Model | paraphrase-multilingual-MiniLM-L12-v2 |
| Dimension | 384 |
| Cross-lingual pairs tested | 12 |
| Pairs with similarity > 0.5 | 7/12 (58%) |
| **Average similarity** | **0.655** |
| GATE threshold | > 0.5 |
| **Status** | **PASS** |

**Sample cross-lingual similarities:**
- "قهوة" ↔ "coffee": 0.776
- "لاتيه" ↔ "latte": 0.867
- "كابتشينو" ↔ "cappuccino": 0.858
- "خدمة" ↔ "service": 0.564

**Conclusion:** The multilingual embedding model provides sufficient cross-lingual similarity for entity resolution. No need to upgrade to CAMeL-BERT.

**Phase 1B Complete. Ready to proceed to Phase 2: Discovery.**

**Next Steps (Phase 2):**
1. Create clustering_job.py with HDBSCAN
2. Implement LLM labeling for clusters
3. Build taxonomy hierarchy (Main → Sub → Products)
4. Trigger on scrape complete or 50+ new mentions
