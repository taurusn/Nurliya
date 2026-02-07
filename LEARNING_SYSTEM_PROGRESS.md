# Learning System — Progress Tracker

**Started:** 2026-02-07
**Branch:** `feature/taxonomy-system`

---

## Overall Status: Complete

---

## Gap 1: Normalize Business Types (Prerequisite)
- [x] Add `BUSINESS_TYPE_MAP` dict to `anchor_manager.py`
- [x] Add `normalize_business_type()` function
- [x] Update `learn_from_approved_taxonomy()` call site
- [x] Update `learn_from_corrections()` call site
- [x] Update `run_clustering_job()` call site in `clustering_job.py`
- [x] Create migration `003_normalize_business_types.sql`

## Gap 2: Corrections Update Qdrant
- [x] Add `update_product_vectors_from_corrections()` to `anchor_manager.py`
- [x] Wire into `bulk_move_mentions` in `api.py`
- [x] Update type hint in `vector_store.py`

## Gap 3: Anchor Cleanup on Rejection
- [x] Add `remove_anchor_examples_for_taxonomy()` to `anchor_manager.py`
- [x] Wire into category reject action in `api.py`
- [x] Wire into product reject action in `api.py`

## Gap 4: Orphaned Anchor Cleanup
- [x] Add `cleanup_orphaned_examples()` to `anchor_manager.py`
- [x] Wire into `import_taxonomy` in `api.py`

## Gap 5: Archives as Learning Input
- [x] Add `ARCHIVE_MATCH_THRESHOLD` constant
- [x] Add `load_anchors_from_archive()` to `anchor_manager.py`
- [x] Update `classify_to_anchor()` for archive source
- [x] Inject archive anchors into `clustering_job.py`
- [x] Deduplicate archive anchors against db_anchors
- [x] Add `TaxonomyArchive` import to `anchor_manager.py`
