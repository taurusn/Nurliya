# OS-Driven Anchor System Plan

**Created**: 2026-02-05
**Status**: In Progress
**Branch**: `feature/taxonomy-system`
**Related Documents**:
- Hybrid Discovery Plan: `HYBRID_DISCOVERY_PLAN.md`
- Taxonomy Editor Plan: `TAXONOMY_EDITOR_PLAN.md`
- Taxonomy Bugs: `TAXONOMY_BUGS.md`
- Progress Tracker: `OS_ANCHOR_PROGRESS.md`

---

## Overview

Replace the hardcoded seed system (`seeds/coffee_shop.py`) with an OS-driven anchor workflow where:
1. **Auto-learn** from approved taxonomies (anchors scoped to business type)
2. **JSON import** by OS for specific places + re-cluster using imported categories as anchors
3. **Wire anchors** into `clustering_job.py` so learned anchors guide future clustering

**No hardcoded seeds** - the system starts empty and learns from OS actions.

---

## Flow

```
Place 1 (cold start, no anchors):
  Scrape --> Extract --> Pure HDBSCAN --> OS reviews draft
  --> OS edits/approves OR imports JSON + re-cluster
  --> Approve --> categories become learned anchors

Place 2 (warm start):
  Scrape --> Extract --> Anchors classify first, unmatched --> HDBSCAN
  --> OS reviews (less work) --> Approves --> more anchors learned

Place N (mature):
  95%+ auto-classified --> OS fine-tunes only
```

---

## Phases

### Phase 0: Fix `anchor_manager.py` Import Bug (Prerequisite)

**Problem**: Line 23 imports `EmbeddingClient` class which does NOT exist - `embedding_client.py` only has module-level functions. This will crash at runtime.

**File**: `pipline/anchor_manager.py`

**Fix**:
- Change `from embedding_client import EmbeddingClient` --> `import embedding_client`
- Remove `embedding_client = EmbeddingClient()` (line 29)
- All calls like `embedding_client.generate_embeddings(...)` continue to work since it becomes a module reference
- Add `IMPORT_MATCH_THRESHOLD = 0.85` for imported anchors

---

### Phase 1: Remove Hardcoded Seeds

**Delete files**:
- `pipline/seeds/coffee_shop.py`
- `pipline/seeds/__init__.py`
- `pipline/seed_anchors.py`

**Verify**: `grep -r "seed_anchors\|seeds\.coffee_shop\|seeds/__init__\|from seeds" pipline/` - nothing else imports these.

`create_seed_anchors()` in `anchor_manager.py` can remain as a generic utility but is no longer called by any production path.

---

### Phase 2: Wire Anchors into Clustering Pipeline

**File**: `pipline/clustering_job.py`

**Changes to `run_clustering_job()`**:

1. Add parameters: `import_anchors: Optional[List[Dict]] = None`, `is_recluster: bool = False`

2. After Step 2 (line 1116, after separating products/aspects), insert **Step 2.5: Anchor Pre-Classification**:
   ```python
   # Step 2.5: Classify mentions against known anchors
   db_anchors = load_anchors_for_business(business_type)
   all_anchors = db_anchors + (import_anchors or [])

   matched_items, unmatched_items = classify_mentions_to_anchors(
       items=all_item_dicts,
       business_type=business_type,
       anchors=all_anchors,
   )

   # Re-separate unmatched for HDBSCAN
   unmatched_products = [i for i in unmatched_items if i["mention_type"] == "product"]
   unmatched_aspects = [i for i in unmatched_items if i["mention_type"] != "product"]
   ```

3. Modify `classify_mentions_to_anchors()` in `anchor_manager.py` to accept optional `anchors` parameter (skip DB load if provided)

4. HDBSCAN runs only on unmatched items

5. Add `build_anchor_matched_hierarchy(matched_items)` function - groups matched items by anchor category, deduplicates products, returns same format as `build_hierarchy()`

6. Merge anchor hierarchy + HDBSCAN hierarchy before `save_draft_taxonomy()`

7. When `is_recluster=True`: skip `is_clustering_needed()` check and existing-draft guard

**Edge case**: Zero anchors --> all items unmatched --> pure HDBSCAN (identical to current behavior).

---

### Phase 3: Auto-Learn on Publish

**File**: `pipline/api.py`

**Hook point**: Inside `publish_taxonomy()` endpoint, after `session.commit()` succeeds (~line 1911):

```python
# Auto-learn anchors from approved categories
from anchor_manager import learn_from_approved_taxonomy
try:
    learned_count = learn_from_approved_taxonomy(str(taxonomy_id))
except Exception as e:
    logger.warning(f"Auto-learning failed (non-blocking): {e}")
```

**Fix in `learn_from_approved_taxonomy()`** (`anchor_manager.py`):
- Query both `discovered_category_id` and `resolved_category_id` (after publish, mentions use resolved)
- For product categories (`has_products=True`): also collect product `canonical_text` + `variants` as examples

---

### Phase 4: JSON Import API + Re-Clustering

#### 4A: New function in `anchor_manager.py`

```python
def generate_anchors_from_import(import_data: dict) -> List[Dict]:
    """Convert imported JSON categories into anchor-format dicts for clustering."""
```

#### 4B: New API endpoint in `api.py`

```
POST /api/onboarding/taxonomies/{taxonomy_id}/import
```

**Request format**:
```json
{
  "categories": [
    {
      "name": "service",
      "display_name_en": "Service Quality",
      "display_name_ar": "جودة الخدمة",
      "is_aspect": true,
      "examples": ["الخدمة ممتازة", "التعامل راقي"]
    },
    {
      "name": "hot_drinks",
      "display_name_en": "Hot Drinks",
      "display_name_ar": "مشروبات ساخنة",
      "is_aspect": false,
      "products": [
        {
          "name": "لاتيه",
          "display_name": "Latte / لاتيه",
          "variants": ["latte", "لاتيه"]
        }
      ]
    }
  ]
}
```

**Endpoint flow**:
1. Validate taxonomy exists and is `draft` status
2. Create imported categories/products in taxonomy (mark `source='imported'`)
3. Delete old HDBSCAN-discovered categories/products (keep imported ones)
4. Clear mention links (`discovered_product_id`, `discovered_category_id` --> NULL)
5. Set `taxonomy.is_reclustering = True`
6. Generate anchors from import data via `generate_anchors_from_import()`
7. Queue re-clustering async (via `BackgroundTasks` or RabbitMQ)
8. Return success with "Re-clustering started" message

#### 4C: Database additions in `database.py`

- Add `source = Column(String(20), default="discovered")` to `TaxonomyCategory`
- Add `is_reclustering = Column(Boolean, default=False)` to `PlaceTaxonomy`

---

### Phase 5: Import UI in Onboarding Portal

#### 5A: New API function in `src/lib/api.ts`

```typescript
export async function importTaxonomy(
  taxonomyId: string,
  data: TaxonomyImportData
): Promise<{ success: boolean; message: string }>
```

#### 5B: New `ImportModal.tsx` component

- File upload (`<input type="file" accept=".json">`)
- JSON validation + preview (category count, product count)
- "Import & Re-cluster" button
- Warning: "This will replace discovered categories and re-cluster"

#### 5C: Add Import button to `src/app/[taxonomyId]/page.tsx`

- Show only when `taxonomy.status !== 'active'`
- Upload icon + "Import" label
- Opens `ImportModal`
- After import, show "Re-clustering in progress..." indicator

---

## Files Modified

| File | Phase | Changes |
|------|-------|---------|
| `pipline/anchor_manager.py` | 0,2,3,4 | Fix import bug, add `anchors` param, fix learn function, add `generate_anchors_from_import()` |
| `pipline/clustering_job.py` | 2 | Wire anchor pre-classification, add `import_anchors`/`is_recluster` params, add `build_anchor_matched_hierarchy()` |
| `pipline/api.py` | 3,4 | Hook auto-learn on publish, add import endpoint |
| `pipline/database.py` | 4 | Add `source` to TaxonomyCategory, `is_reclustering` to PlaceTaxonomy |
| `onboarding-portal/src/lib/api.ts` | 5 | Add `importTaxonomy()` function + types |
| `onboarding-portal/src/components/ImportModal.tsx` | 5 | New file - import modal |
| `onboarding-portal/src/app/[taxonomyId]/page.tsx` | 5 | Add Import button + modal integration |
| `pipline/seeds/coffee_shop.py` | 1 | **DELETE** |
| `pipline/seeds/__init__.py` | 1 | **DELETE** |
| `pipline/seed_anchors.py` | 1 | **DELETE** |

## Execution Order

Phase 0 --> Phase 1 --> Phase 2 --> Phase 3 --> Phase 4 --> Phase 5

## Verification

1. **Cold start**: Cluster a place with no anchors --> pure HDBSCAN --> identical to current behavior
2. **Auto-learn**: Publish a taxonomy --> check `category_anchors` table has new `source='learned'` entries
3. **Warm start**: Cluster another place of same type --> verify some mentions pre-classified via anchors
4. **Import**: Upload JSON in UI --> verify imported categories appear --> re-clustering runs --> new draft has imported + discovered categories
5. **Re-cluster**: After import, verify mention counts are reasonable and imported categories have matched mentions
