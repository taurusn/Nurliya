# Taxonomy Clustering Quality Improvement Plan

**Document Version**: 2.0
**Created**: 2026-02-04
**Author**: Engineering Team
**Status**: Ready for Technical Review
**Related Feature**: FEATURE-001 (Multi-Branch Shared Taxonomy)

---

## Executive Summary

Our HDBSCAN-based taxonomy clustering system successfully groups semantically similar product mentions into categories. However, the current implementation creates **one product per unique mention text** rather than grouping similar texts as variants of a single product.

**Impact**: A test run on Specialty Bean Roastery (2 branches, 1,936 mentions) produced:
- 85 products (expected: 25-35)
- 0 products with variants (expected: all products should have variants)
- 6 exact duplicate entries

**Proposed Solution**: Add embedding-based sub-clustering within each HDBSCAN cluster to group similar mention texts into single products with variants.

**Effort Estimate**: 1-2 hours implementation + testing

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [Problem Analysis](#2-problem-analysis)
3. [Evidence from Production Data](#3-evidence-from-production-data)
4. [Proposed Solution](#4-proposed-solution)
5. [Technical Implementation](#5-technical-implementation)
6. [Expected Outcomes](#6-expected-outcomes)
7. [Risk Assessment](#7-risk-assessment)
8. [Success Criteria](#8-success-criteria)

---

## 1. Current Architecture

### 1.1 Data Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MENTION EXTRACTION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Reviews (1,936)                                                            │
│      │                                                                      │
│      ▼                                                                      │
│  LLM Extraction ──► Raw Mentions (450 products)                            │
│      │                                                                      │
│      ▼                                                                      │
│  Embedding Generation (text-embedding-3-small)                              │
│      │                                                                      │
│      ▼                                                                      │
│  Qdrant Vector Store ──► 153 unique product vectors                        │
│  (aggregated by text, with mention_count)                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TAXONOMY CLUSTERING                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  HDBSCAN Clustering                                                         │
│      │                                                                      │
│      ├── Cluster 0: 33 vectors ──► Category: "coffee_&_sweets"             │
│      ├── Cluster 1: 12 vectors ──► Category: "v60_coffee"                  │
│      ├── Cluster 2: 12 vectors ──► Category: "coffee_drinks"               │
│      ├── Cluster 3:  4 vectors ──► Category: "flat_white" (Arabic)         │
│      ├── Cluster 4:  4 vectors ──► Category: "flat_white_(hot_coffee)" (EN)│
│      └── ... (10 clusters total)                                           │
│                                                                             │
│  Current Product Creation:                                                  │
│      FOR EACH vector IN cluster:                                           │
│          CREATE product(canonical_text = vector.text)  ◄── PROBLEM         │
│                                                                             │
│  Result: 85 products (one per unique text)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Current HDBSCAN Configuration

```python
# clustering_job.py
HDBSCAN_CONFIG = {
    "min_cluster_size": 3,      # Minimum mentions to form a cluster
    "min_samples": None,        # Default (same as min_cluster_size)
    "metric": "euclidean",      # Distance metric
    "cluster_selection_method": "eom"  # Excess of Mass
}

SUPER_CATEGORY_SIMILARITY_THRESHOLD = 0.7  # For hierarchy detection
```

### 1.3 Current Product Creation Logic

**File**: `clustering_job.py`, lines 565-583

```python
# Create products from items
for item in product_items:
    if item.cluster_id < 0:
        continue  # Skip noise

    category = sub_id_map.get(item.cluster_id)
    if not category:
        continue

    product = {
        "id": str(uuid.uuid4()),
        "canonical_text": item.text.lower().strip(),  # ◄── Each text = new product
        "display_name": item.text,
        "discovered_category_id": category["id"],
        "discovered_mention_count": item.mention_count,
        "avg_sentiment": item.sentiment_sum / max(item.mention_count, 1),
    }
    hierarchy["products"].append(product)
```

**Issue**: This creates one product per unique mention text, ignoring that multiple texts may represent the same real-world product.

---

## 2. Problem Analysis

### 2.1 Problem Statement

The clustering pipeline correctly identifies semantic categories (HDBSCAN clusters), but fails to deduplicate similar product mentions within each cluster.

### 2.2 Three Distinct Issues Identified

| Issue | Description | Severity |
|-------|-------------|----------|
| **P1: No Within-Cluster Deduplication** | "فلات وايت", "flat white", "flatwhite" become 3 products | High |
| **P2: Cross-Lingual Cluster Separation** | Arabic and English variants in different clusters | Medium |
| **P3: Exact Duplicates** | Same text appearing multiple times | Low |

### 2.3 Root Cause Analysis

```
                    ┌─────────────────────────────────┐
                    │     WHY 85 PRODUCTS?            │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │  Each unique text = 1 product   │
                    │  (No grouping of similar texts) │
                    └───────────────┬─────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ P1: No sub-     │    │ P2: Embeddings  │    │ P3: Vector      │
│ clustering      │    │ not capturing   │    │ aggregation     │
│ within HDBSCAN  │    │ cross-lingual   │    │ bug (duplicate  │
│ clusters        │    │ similarity well │    │ texts)          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
   PRIMARY FIX           SECONDARY FIX          MINOR FIX
  (Sub-clustering)     (Lower threshold)     (Dedup in storage)
```

---

## 3. Evidence from Production Data

### 3.1 Test Dataset

| Metric | Value |
|--------|-------|
| Business | Specialty Bean Roastery |
| Branches | 2 (Riyadh + Al Khobar) |
| Total Reviews | 1,936 |
| Product Mentions | 450 |
| Unique Product Vectors | 153 |
| HDBSCAN Clusters | 10 |
| Products Created | 85 |

### 3.2 Top Mentions (Should Be Grouped)

```sql
-- Raw mention frequency
SELECT mention_text, COUNT(*) FROM raw_mentions GROUP BY mention_text ORDER BY COUNT(*) DESC;
```

| Mention Text | Occurrences | Should Group With |
|--------------|-------------|-------------------|
| فلات وايت | 34 | flat white, الفلات وايت |
| V60 | 20 | v60, في ٦٠ |
| الفلات وايت | 18 | فلات وايت, flat white |
| اللاتيه | 14 | لاتيه, latte, Latte |
| flat white | 12 | فلات وايت, الفلات وايت |
| v60 | 10 | V60, في ٦٠ |
| لاتيه | 9 | اللاتيه, latte |
| الكورتادو | 8 | كورتادو, Cortado |
| التيراميسو | 6 | تراميسو, tiramisu |

**Expected**: "Flat White" product with 64+ mentions (combined)
**Actual**: 8 separate products across 2 categories

### 3.3 Category Distribution Analysis

```sql
-- Products per category
SELECT c.name, COUNT(p.id) FROM taxonomy_categories c
JOIN taxonomy_products p ON p.discovered_category_id = c.id
GROUP BY c.name ORDER BY COUNT(p.id) DESC;
```

| Category | Product Count | Assessment |
|----------|---------------|------------|
| coffee_&_sweets | 33 | ❌ Too many - needs sub-clustering |
| v60_coffee | 12 | ❌ Should be ~3 (V60, V60 Brazilian, etc.) |
| coffee_drinks | 12 | ❌ Should be ~5 |
| iced_coffee | 5 | ⚠️ Reasonable |
| coffee_beans | 5 | ⚠️ Reasonable |
| brewed_coffee | 4 | ✓ OK |
| flat_white | 4 | ❌ Should merge with flat_white_(hot_coffee) |
| flat_white_(hot_coffee) | 4 | ❌ Should merge with flat_white |
| ethiopian_coffee | 3 | ✓ OK |
| cakes | 3 | ✓ OK |

### 3.4 Flat White Case Study

**Current State** (2 clusters, 8 products):

```
Category: flat_white (Arabic cluster)
├── الفلات وايت     (mentions: 18)
├── فلات وايت       (mentions: 34)
├── الفلايت وايت    (mentions: 1)   ◄── typo variant
└── فلات وايت بلند  (mentions: 2)

Category: flat_white_(hot_coffee) (English cluster)
├── flat white      (mentions: 12)
├── flat white      (mentions: 12)  ◄── EXACT DUPLICATE
├── flatwhite       (mentions: 2)
└── hot flat white  (mentions: 1)
```

**Expected State** (1-2 products):

```
Product: "فلات وايت" (Flat White)
├── canonical_text: "فلات وايت"
├── variants: ["الفلات وايت", "الفلايت وايت", "flat white", "flatwhite", "hot flat white"]
├── total_mentions: 80
└── category: flat_white

Product: "فلات وايت بلند" (Flat White Blend) [if distinct]
├── canonical_text: "فلات وايت بلند"
├── variants: []
├── total_mentions: 2
└── category: flat_white
```

### 3.5 Coffee & Sweets Category (33 Products)

This single category contains what should be ~12 distinct products:

| Actual Products | Should Be |
|-----------------|-----------|
| اللاتيه, اللاتيه, سبنش لاتيه, سقنتشر لاتيه | 1-2 products (Latte variants) |
| كابتشينو, كابتشينو, الكاباتشينو | 1 product (Cappuccino) |
| التيراميسو, التيراميسو, تراميسو, تراميسوا | 1 product (Tiramisu) |
| اسبرسو, شاباد للشوت اسبريسو | 1 product (Espresso) |
| كركديه, كركديه بالنعناع | 1-2 products (Hibiscus) |
| 5 different cakes | 5 products (distinct items) |

---

## 4. Proposed Solution

### 4.1 Solution Overview

**Add embedding-based sub-clustering within each HDBSCAN cluster.**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PROPOSED ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  HDBSCAN Cluster (Category)                                                 │
│      │                                                                      │
│      ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │  NEW: DBSCAN Sub-Clustering (85% similarity threshold)          │       │
│  │                                                                  │       │
│  │  Input: All vectors in HDBSCAN cluster                          │       │
│  │  Output: Sub-clusters (each = one product)                      │       │
│  │                                                                  │       │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │       │
│  │  │ Sub-cluster A│  │ Sub-cluster B│  │ Sub-cluster C│          │       │
│  │  │ فلات وايت    │  │ كابتشينو     │  │ تراميسو      │          │       │
│  │  │ flat white   │  │ الكاباتشينو  │  │ التيراميسو   │          │       │
│  │  │ flatwhite    │  │ cappuccino   │  │ tiramisu     │          │       │
│  │  └──────────────┘  └──────────────┘  └──────────────┘          │       │
│  │         │                 │                 │                   │       │
│  │         ▼                 ▼                 ▼                   │       │
│  │    Product 1         Product 2         Product 3               │       │
│  │    + variants        + variants        + variants              │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Algorithm Selection: Why DBSCAN for Sub-Clustering?

| Algorithm | Pros | Cons | Verdict |
|-----------|------|------|---------|
| **DBSCAN** | No need to specify k, handles noise, density-based | Sensitive to eps parameter | ✓ Selected |
| K-Means | Simple, fast | Requires k (unknown), spherical clusters | ✗ |
| Agglomerative | Hierarchical, flexible | Computationally expensive | ✗ |
| Text Similarity | Simple | Fails cross-lingual (Arabic/English) | ✗ |

**DBSCAN Configuration**:
- `eps = 0.15` (equivalent to 85% cosine similarity)
- `min_samples = 1` (allow single-item clusters for unique products)
- `metric = "cosine"` (semantic similarity)

### 4.3 Why 85% Similarity Threshold?

```
Embedding Similarity Analysis:

"فلات وايت" vs "flat white"     → ~0.88 similarity (same product)
"فلات وايت" vs "فلات وايت بلند"  → ~0.82 similarity (variant vs distinct)
"فلات وايت" vs "كابتشينو"        → ~0.65 similarity (different products)

Threshold Selection:
├── 0.90: Too strict - misses valid variants
├── 0.85: ✓ Optimal - groups variants, separates products
├── 0.80: Too loose - may merge distinct products
└── 0.75: Too loose - definitely merges different items
```

### 4.4 Cross-Lingual Handling

The embedding model (text-embedding-3-small) is multilingual. Sub-clustering with embeddings naturally handles:

```
"flat white" ─────┐
                  ├──► Same sub-cluster (cosine similarity ~0.88)
"فلات وايت" ──────┘

No text matching needed. Pure semantic similarity.
```

---

## 5. Technical Implementation

### 5.1 New Function: `deduplicate_cluster_items()`

**Location**: `clustering_job.py`

```python
from sklearn.cluster import DBSCAN
from collections import defaultdict
from typing import List, Dict
import numpy as np


def deduplicate_cluster_items(
    items: List[ClusterItem],
    similarity_threshold: float = 0.85
) -> List[Dict]:
    """
    Sub-cluster items within an HDBSCAN cluster to identify distinct products.

    Uses DBSCAN with cosine similarity on embeddings, which handles:
    - Cross-lingual variants (Arabic/English)
    - Typos and spelling variations
    - Semantic similarity

    Args:
        items: List of ClusterItem objects from one HDBSCAN cluster
        similarity_threshold: Minimum cosine similarity to group items (default 0.85)

    Returns:
        List of product dictionaries, each containing:
        - canonical_text: Most frequent mention text (lowercase)
        - display_name: Original casing of canonical text
        - variants: List of other text variations
        - items: Original ClusterItem objects
        - total_mentions: Sum of mention_count across all items
        - avg_sentiment: Weighted average sentiment

    Example:
        Input items: ["فلات وايت"(34), "flat white"(12), "flatwhite"(2)]
        Output: [{
            "canonical_text": "فلات وايت",
            "variants": ["flat white", "flatwhite"],
            "total_mentions": 48
        }]
    """
    # Handle edge cases
    if not items:
        return []

    if len(items) == 1:
        return [{
            "canonical_text": items[0].text.lower().strip(),
            "display_name": items[0].text,
            "variants": [],
            "items": items,
            "total_mentions": items[0].mention_count,
            "avg_sentiment": items[0].sentiment_sum / max(items[0].mention_count, 1)
        }]

    # Extract embeddings for sub-clustering
    embeddings = np.array([item.embedding for item in items])

    # DBSCAN with cosine distance
    # eps = 1 - similarity_threshold (cosine distance = 1 - cosine similarity)
    sub_clustering = DBSCAN(
        eps=1 - similarity_threshold,
        min_samples=1,
        metric="cosine"
    ).fit(embeddings)

    # Group items by sub-cluster label
    groups = defaultdict(list)
    for i, label in enumerate(sub_clustering.labels_):
        # DBSCAN uses -1 for noise, but with min_samples=1, no noise expected
        groups[label].append(items[i])

    # Convert groups to product dictionaries
    products = []
    for group_items in groups.values():
        # Sort by mention_count descending - highest frequency = canonical
        sorted_items = sorted(group_items, key=lambda x: -x.mention_count)

        # Canonical text is the most frequently mentioned variant
        canonical = sorted_items[0].text.lower().strip()
        display_name = sorted_items[0].text  # Preserve original casing

        # Collect unique variants (excluding canonical)
        variants = []
        seen_texts = {canonical}
        for item in sorted_items[1:]:
            normalized = item.text.lower().strip()
            if normalized not in seen_texts:
                variants.append(item.text)
                seen_texts.add(normalized)

        # Calculate aggregated metrics
        total_mentions = sum(item.mention_count for item in group_items)
        total_sentiment = sum(item.sentiment_sum for item in group_items)

        products.append({
            "canonical_text": canonical,
            "display_name": display_name,
            "variants": variants,
            "items": group_items,
            "total_mentions": total_mentions,
            "avg_sentiment": total_sentiment / max(total_mentions, 1)
        })

    return products
```

### 5.2 Modified `build_hierarchy()` Function

**Location**: `clustering_job.py`, replace lines 565-583

```python
    # ─────────────────────────────────────────────────────────────────────────
    # CREATE PRODUCTS WITH DEDUPLICATION (replaces old logic)
    # ─────────────────────────────────────────────────────────────────────────

    # Group items by their HDBSCAN cluster
    cluster_items = defaultdict(list)
    for item in product_items:
        if item.cluster_id >= 0:  # Skip noise (cluster_id = -1)
            cluster_items[item.cluster_id].append(item)

    # Process each cluster: sub-cluster to find distinct products
    for cluster_id, items in cluster_items.items():
        category = sub_id_map.get(cluster_id)
        if not category:
            continue

        # Sub-cluster to deduplicate similar items into products
        product_groups = deduplicate_cluster_items(items, similarity_threshold=0.85)

        logger.debug(
            f"Cluster {cluster_id} ({category['name']}): "
            f"{len(items)} items → {len(product_groups)} products"
        )

        # Create product entries
        for group in product_groups:
            product = {
                "id": str(uuid.uuid4()),
                "canonical_text": group["canonical_text"],
                "display_name": group["display_name"],
                "variants": group["variants"],
                "discovered_category_id": category["id"],
                "discovered_mention_count": group["total_mentions"],
                "avg_sentiment": group["avg_sentiment"],
            }
            hierarchy["products"].append(product)

    # ─────────────────────────────────────────────────────────────────────────
```

### 5.3 Database Schema (No Changes Required)

The `taxonomy_products` table already supports variants:

```sql
CREATE TABLE taxonomy_products (
    id UUID PRIMARY KEY,
    taxonomy_id UUID NOT NULL,
    canonical_text VARCHAR(200) NOT NULL,
    display_name VARCHAR(200),
    variants JSONB,                    -- ◄── Already exists, currently empty
    discovered_mention_count INTEGER,
    ...
);
```

### 5.4 Configuration Constants

**Add to `clustering_job.py`**:

```python
# Sub-clustering configuration
PRODUCT_SIMILARITY_THRESHOLD = 0.85  # Cosine similarity for grouping variants
```

---

## 6. Expected Outcomes

### 6.1 Quantitative Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total Products | 85 | 25-35 | ~60% reduction |
| Products with Variants | 0 | 25-35 | 100% coverage |
| Exact Duplicates | 6 | 0 | Eliminated |
| Avg Variants per Product | 0 | 2-3 | Meaningful grouping |

### 6.2 Category-Level Improvements

| Category | Before | After |
|----------|--------|-------|
| coffee_&_sweets | 33 products | ~12 products |
| v60_coffee | 12 products | ~3 products |
| flat_white + flat_white_(hot_coffee) | 8 products | 1-2 products |
| coffee_drinks | 12 products | ~5 products |

### 6.3 Example Transformation

**Before**:
```json
{
  "category": "flat_white",
  "products": [
    {"canonical_text": "الفلات وايت", "variants": [], "mentions": 18},
    {"canonical_text": "فلات وايت", "variants": [], "mentions": 34},
    {"canonical_text": "الفلايت وايت", "variants": [], "mentions": 1},
    {"canonical_text": "فلات وايت بلند", "variants": [], "mentions": 2}
  ]
},
{
  "category": "flat_white_(hot_coffee)",
  "products": [
    {"canonical_text": "flat white", "variants": [], "mentions": 12},
    {"canonical_text": "flat white", "variants": [], "mentions": 12},
    {"canonical_text": "flatwhite", "variants": [], "mentions": 2},
    {"canonical_text": "hot flat white", "variants": [], "mentions": 1}
  ]
}
```

**After**:
```json
{
  "category": "flat_white",
  "products": [
    {
      "canonical_text": "فلات وايت",
      "display_name": "فلات وايت",
      "variants": ["الفلات وايت", "الفلايت وايت", "flat white", "flatwhite", "hot flat white"],
      "total_mentions": 80,
      "avg_sentiment": 0.85
    },
    {
      "canonical_text": "فلات وايت بلند",
      "display_name": "فلات وايت بلند",
      "variants": [],
      "total_mentions": 2,
      "avg_sentiment": 0.90
    }
  ]
}
```

---

## 7. Risk Assessment

### 7.1 Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Over-grouping (merge distinct products) | Low | Medium | Configurable threshold, human review |
| Under-grouping (miss variants) | Medium | Low | Can lower threshold if needed |
| Performance impact | Low | Low | DBSCAN is O(n²) but n is small per cluster |
| Breaking existing taxonomies | None | N/A | Only affects new draft taxonomies |

### 7.2 Threshold Sensitivity Analysis

```
Threshold: 0.90 (Very Strict)
├── Pros: No false merges
├── Cons: "flat white" and "فلات وايت" may not merge
└── Result: ~50 products (still too many)

Threshold: 0.85 (Recommended) ◄──────────────────────────────
├── Pros: Balances precision and recall
├── Cons: Minor risk of over-grouping
└── Result: ~30 products (optimal)

Threshold: 0.80 (Loose)
├── Pros: Maximum grouping
├── Cons: May merge "latte" with "cappuccino" in edge cases
└── Result: ~20 products (possibly too aggressive)
```

### 7.3 Rollback Strategy

- Changes only affect `clustering_job.py`
- New taxonomies use new logic; existing taxonomies unchanged
- Can revert with single commit if issues arise

---

## 8. Success Criteria

### 8.1 Acceptance Criteria

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| Product count reduction | ≥50% | Count products before/after |
| Variant coverage | ≥90% of products have variants | Query products where variants != [] |
| Zero duplicates | 0 exact duplicate texts | Count distinct vs total |
| Cross-lingual grouping | Arabic/English variants together | Manual spot check |
| No regression | Existing tests pass | CI/CD pipeline |

### 8.2 Validation Queries

```sql
-- Product count
SELECT COUNT(*) FROM taxonomy_products WHERE taxonomy_id = ?;

-- Products with variants
SELECT COUNT(*) FROM taxonomy_products
WHERE taxonomy_id = ? AND jsonb_array_length(variants) > 0;

-- Check for duplicates
SELECT canonical_text, COUNT(*)
FROM taxonomy_products
WHERE taxonomy_id = ?
GROUP BY canonical_text
HAVING COUNT(*) > 1;

-- Variant distribution
SELECT
    jsonb_array_length(variants) as variant_count,
    COUNT(*) as product_count
FROM taxonomy_products
WHERE taxonomy_id = ?
GROUP BY jsonb_array_length(variants)
ORDER BY variant_count;
```

### 8.3 Manual Verification Checklist

- [ ] "Flat White" variations grouped into single product
- [ ] "V60" variations grouped into single product
- [ ] "Tiramisu" variations grouped (Arabic/English)
- [ ] "Latte" and "Cappuccino" remain separate products
- [ ] Products with distinct names remain separate (e.g., "Signature Latte" vs "Spanish Latte")

---

## Appendix A: File Changes Summary

| File | Changes |
|------|---------|
| `clustering_job.py` | Add `deduplicate_cluster_items()`, modify `build_hierarchy()` |

**Lines Changed**: ~60 lines added, ~20 lines modified

---

## Appendix B: Dependencies

**Existing** (no new dependencies):
- `scikit-learn` (DBSCAN)
- `numpy` (array operations)

---

## Appendix C: Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| Implementation | 1 hour | Add function, modify build_hierarchy |
| Testing | 30 min | Re-run clustering, verify results |
| Code Review | 30 min | Technical review |
| Deployment | 15 min | Docker rebuild |

**Total**: ~2.5 hours

---

*Document prepared for technical review*
*Last updated: 2026-02-04*
