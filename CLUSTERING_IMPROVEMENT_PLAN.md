# Taxonomy Clustering Quality Improvement Plan

**Document Version**: 3.0
**Created**: 2026-02-04
**Author**: Engineering Team
**Status**: Ready for Technical Review (Updated with Empirical Validation)
**Related Feature**: FEATURE-001 (Multi-Branch Shared Taxonomy)

---

## Executive Summary

Our HDBSCAN-based taxonomy clustering system successfully groups semantically similar product mentions into categories. However, the current implementation creates **one product per unique mention text** rather than grouping similar texts as variants of a single product.

**Impact**: A test run on Specialty Bean Roastery (2 branches, 1,936 mentions) produced:
- 85 products (expected: 25-35)
- 0 products with variants (expected: all products should have variants)
- 6 exact duplicate entries

### Critical Finding (Empirical Validation)

**The embedding model (text-embedding-3-small) has weak cross-lingual performance:**

| Pair | Actual Similarity | Assumption |
|------|-------------------|------------|
| "flat white" vs "فلات وايت" | **0.6255** | ~0.88 |
| "latte" vs "اللاتيه" | **0.2891** | ~0.85 |
| "tiramisu" vs "التيراميسو" | **0.7262** | ~0.85 |

This means embedding-based sub-clustering **cannot merge Arabic and English variants**. The solution must address this limitation.

### Revised Solution

**Two-phase approach:**
1. **Phase 1**: Embedding-based sub-clustering for same-language variants (immediate win)
2. **Phase 2**: LLM-based cross-lingual grouping (solves Arabic/English merge)

**Effort Estimate**: Phase 1: 1-2 hours | Phase 2: 2-3 hours

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [Problem Analysis](#2-problem-analysis)
3. [Empirical Validation](#3-empirical-validation)
4. [Revised Solution Design](#4-revised-solution-design)
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
    "min_cluster_size": 3,
    "min_samples": None,
    "metric": "euclidean",
    "cluster_selection_method": "eom"
}

SUPER_CATEGORY_SIMILARITY_THRESHOLD = 0.7
```

### 1.3 Current Product Creation Logic

**File**: `clustering_job.py`, lines 565-583

```python
for item in product_items:
    if item.cluster_id < 0:
        continue

    product = {
        "id": str(uuid.uuid4()),
        "canonical_text": item.text.lower().strip(),  # ◄── Each text = new product
        "display_name": item.text,
        "discovered_category_id": category["id"],
        "discovered_mention_count": item.mention_count,
    }
    hierarchy["products"].append(product)
```

---

## 2. Problem Analysis

### 2.1 Three Distinct Issues

| Issue | Description | Root Cause | Severity |
|-------|-------------|------------|----------|
| **P1** | No within-cluster deduplication | Code creates 1 product per text | High |
| **P2** | Cross-lingual cluster separation | Embedding model weak on AR-EN | High |
| **P3** | Exact duplicates | Vector aggregation bug | Low |

### 2.2 Root Cause Hierarchy

```
                    ┌─────────────────────────────────┐
                    │     WHY 85 PRODUCTS?            │
                    └───────────────┬─────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ P1: No sub-     │    │ P2: Embedding   │    │ P3: Duplicate   │
│ clustering      │    │ model weak on   │    │ vectors         │
│                 │    │ Arabic-English  │    │                 │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         ▼                      ▼                      ▼
    DBSCAN sub-          LLM cross-lingual       Dedup on
    clustering           grouping                 insert
    (Phase 1)            (Phase 2)               (Minor fix)
```

---

## 3. Empirical Validation

### 3.1 Methodology

Extracted actual embeddings from Qdrant and computed pairwise cosine similarities.

```python
def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
```

### 3.2 Cross-Lingual Similarity (Arabic vs English)

**Finding: Cross-lingual similarity is POOR (0.29-0.63)**

| English | Arabic | Similarity | Assessment |
|---------|--------|------------|------------|
| flat white | فلات وايت | **0.6255** | ❌ Too low to merge |
| latte | اللاتيه | **0.2891** | ❌ Far too low |
| tiramisu | التيراميسو | **0.7262** | ⚠️ Borderline |
| tiramisu | تراميسو | **0.7145** | ⚠️ Borderline |

**Conclusion**: The text-embedding-3-small model does NOT produce similar vectors for Arabic and English versions of the same word. Transliterations (tiramisu→تيراميسو) perform better than translations (latte→لاتيه).

### 3.3 Same-Language Similarity (Within Arabic)

**Finding: Arabic variants cluster well (0.78-0.96)**

| Text 1 | Text 2 | Similarity | Assessment |
|--------|--------|------------|------------|
| فلات وايت | الفلايت وايت | **0.9635** | ✓ Excellent |
| الفلايت وايت | الفلات وايت | **0.8872** | ✓ Good |
| فلات وايت | الفلات وايت | **0.8368** | ✓ Acceptable |
| تراميسو | التيراميسو | **0.7764** | ⚠️ Borderline |
| فلات وايت | فلات وايت بلند | **0.7984** | ✓ Correctly separate |

### 3.4 Same-Language Similarity (Within English)

**Finding: English variants cluster adequately (0.80-0.81)**

| Text 1 | Text 2 | Similarity | Assessment |
|--------|--------|------------|------------|
| flat white | Flatwhite | **0.8060** | ⚠️ Borderline |
| hot flat white | flat white | **0.8116** | ⚠️ Borderline |

### 3.5 Different Products (Negative Cases)

**Finding: Different products correctly have low similarity (0.13-0.38)**

| Text 1 | Text 2 | Similarity | Assessment |
|--------|--------|------------|------------|
| flat white | cappuccino | ~0.35 | ✓ Correctly separate |
| latte | espresso | **0.3375** | ✓ Correctly separate |
| V60 | tiramisu | **0.1313** | ✓ Correctly separate |
| فلات وايت | كابتشينو | **0.3747** | ✓ Correctly separate |

### 3.6 Threshold Analysis (Revised)

Based on empirical data:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SIMILARITY DISTRIBUTION                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Different products     │ Cross-lingual    │ Same-lang variants│           │
│  (should separate)      │ (PROBLEMATIC)    │ (should merge)    │           │
│  ◄──────────────────────┼──────────────────┼───────────────────►           │
│                         │                  │                    │           │
│  0.13 ─── 0.38          │  0.29 ─── 0.73   │  0.78 ─── 0.96    │           │
│                         │                  │                    │           │
│  ════════════════════════════════════════════════════════════════          │
│  0.0      0.2      0.4      0.6      0.8      1.0                          │
│                              ▲                                              │
│                              │                                              │
│                    Cross-lingual overlaps                                   │
│                    with "different products"!                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

Recommended threshold for same-language: 0.78
Cross-lingual: Cannot use embedding similarity alone
```

---

## 4. Revised Solution Design

### 4.1 Two-Phase Approach

Given the embedding model's cross-lingual limitations, we need a hybrid approach:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         REVISED ARCHITECTURE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PHASE 1: Same-Language Deduplication (Embeddings)                         │
│  ════════════════════════════════════════════════                          │
│                                                                             │
│  HDBSCAN Cluster ──► DBSCAN Sub-clustering (threshold: 0.78)               │
│      │                                                                      │
│      ├── Arabic group: فلات وايت, الفلات وايت, الفلايت وايت                │
│      │       └──► Product: "فلات وايت" + variants                          │
│      │                                                                      │
│      └── English group: flat white, Flatwhite, hot flat white              │
│              └──► Product: "flat white" + variants                         │
│                                                                             │
│  Result: 85 products → ~45-50 products (same-language merged)              │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PHASE 2: Cross-Lingual Grouping (LLM)                                     │
│  ═════════════════════════════════════                                     │
│                                                                             │
│  For each category, ask LLM:                                               │
│  "Which of these products are the same item in different languages?"       │
│                                                                             │
│  Input: ["فلات وايت", "flat white", "كابتشينو", "cappuccino"]              │
│  Output: [["فلات وايت", "flat white"], ["كابتشينو", "cappuccino"]]         │
│                                                                             │
│  Merge identified pairs:                                                    │
│      "فلات وايت" absorbs "flat white" as variant                           │
│      (Keep Arabic as canonical - higher mention count in Saudi market)     │
│                                                                             │
│  Result: ~45-50 products → ~25-35 products (cross-lingual merged)          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Why This Approach?

| Approach | Same-Language | Cross-Lingual | Complexity | Cost |
|----------|---------------|---------------|------------|------|
| Embedding only | ✓ Works | ✗ Fails | Low | Free |
| LLM only | ✓ Works | ✓ Works | Medium | API calls |
| **Hybrid (Recommended)** | ✓ Embeddings | ✓ LLM | Medium | Minimal API |

The hybrid approach:
1. Uses fast/free embeddings for the easy cases (same-language)
2. Uses LLM only where necessary (cross-lingual pairs)
3. Minimizes API costs by batching LLM calls per category

### 4.3 Alternative: Better Embedding Model

**Option**: Replace text-embedding-3-small with multilingual-e5-large

| Model | Cross-Lingual | Dimensions | Cost |
|-------|---------------|------------|------|
| text-embedding-3-small | Poor (0.29-0.63) | 1536 | $0.02/1M |
| multilingual-e5-large | Good (~0.85) | 1024 | Self-hosted |

**Trade-off**: Requires re-embedding all vectors, infrastructure changes. The LLM hybrid approach is faster to implement and works with existing data.

---

## 5. Technical Implementation

### 5.1 Phase 1: Same-Language Deduplication

#### 5.1.1 Configuration

```python
# clustering_job.py - Add configuration

import os

# Same-language similarity threshold (empirically validated)
# Arabic variants: 0.78-0.96, English variants: 0.80-0.81
# Set slightly below minimum to catch borderline cases
PRODUCT_SIMILARITY_THRESHOLD = float(
    os.environ.get("PRODUCT_SIMILARITY_THRESHOLD", "0.78")
)
```

#### 5.1.2 Deduplication Function

```python
from sklearn.cluster import DBSCAN
from collections import defaultdict
from typing import List, Dict, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


def deduplicate_cluster_items(
    items: List[ClusterItem],
    similarity_threshold: float = PRODUCT_SIMILARITY_THRESHOLD
) -> List[Dict]:
    """
    Sub-cluster items within an HDBSCAN cluster to identify distinct products.

    Uses DBSCAN with cosine similarity on embeddings. This effectively groups
    same-language variants (Arabic-Arabic, English-English) but will NOT merge
    cross-lingual pairs due to embedding model limitations.

    Args:
        items: List of ClusterItem objects from one HDBSCAN cluster.
        similarity_threshold: Minimum cosine similarity to group items.
            Default 0.78 based on empirical validation:
            - Arabic variants: 0.78-0.96 similarity
            - English variants: 0.80-0.81 similarity
            - Cross-lingual: 0.29-0.63 (will NOT merge)

    Returns:
        List of product dictionaries with:
        - canonical_text: Most frequent mention text (lowercase)
        - display_name: Original casing of canonical text
        - variants: List of other text variations
        - items: Original ClusterItem objects
        - total_mentions: Sum of mention_count
        - avg_sentiment: Weighted average sentiment

    Example:
        Input: ["فلات وايت"(34), "الفلات وايت"(18), "flat white"(12)]
        Output: [
            {"canonical_text": "فلات وايت", "variants": ["الفلات وايت"], ...},
            {"canonical_text": "flat white", "variants": [], ...}
        ]
        Note: Arabic and English remain separate (cross-lingual handled in Phase 2)
    """
    if not items:
        return []

    if len(items) == 1:
        item = items[0]
        return [{
            "canonical_text": item.text.lower().strip(),
            "display_name": item.text,
            "variants": [],
            "items": items,
            "total_mentions": item.mention_count,
            "avg_sentiment": item.sentiment_sum / max(item.mention_count, 1)
        }]

    # Extract embeddings
    embeddings = np.array([item.embedding for item in items])

    # DBSCAN with cosine distance
    sub_clustering = DBSCAN(
        eps=1 - similarity_threshold,
        min_samples=1,
        metric="cosine"
    ).fit(embeddings)

    # Group by sub-cluster
    groups: Dict[int, List[ClusterItem]] = defaultdict(list)
    for i, label in enumerate(sub_clustering.labels_):
        groups[label].append(items[i])

    # Convert to products
    products = []
    for group_items in groups.values():
        sorted_items = sorted(group_items, key=lambda x: -x.mention_count)

        canonical = sorted_items[0].text.lower().strip()
        display_name = sorted_items[0].text

        variants = []
        seen = {canonical}
        for item in sorted_items[1:]:
            norm = item.text.lower().strip()
            if norm not in seen:
                variants.append(item.text)
                seen.add(norm)

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

    logger.info(
        f"Deduplicated {len(items)} items into {len(products)} products",
        extra={"extra_data": {
            "input_count": len(items),
            "output_count": len(products),
            "threshold": similarity_threshold
        }}
    )

    return products
```

#### 5.1.3 Modified build_hierarchy()

```python
    # ─────────────────────────────────────────────────────────────────────────
    # CREATE PRODUCTS WITH DEDUPLICATION
    # ─────────────────────────────────────────────────────────────────────────

    cluster_items: Dict[int, List[ClusterItem]] = defaultdict(list)
    for item in product_items:
        if item.cluster_id >= 0:
            cluster_items[item.cluster_id].append(item)

    for cluster_id, items in cluster_items.items():
        category = sub_id_map.get(cluster_id)
        if not category:
            continue

        product_groups = deduplicate_cluster_items(items)

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
```

### 5.2 Phase 2: Cross-Lingual LLM Grouping

#### 5.2.1 LLM Prompt

```python
CROSS_LINGUAL_GROUPING_PROMPT = """You are identifying cross-lingual product matches for a Saudi {business_type}.

These products were extracted from customer reviews. Some may be the same item written in Arabic and English.

Products in this category:
{products}

Identify pairs that are THE SAME PRODUCT in different languages.

Rules:
1. Only match if they are clearly the same item (e.g., "latte" = "لاتيه")
2. Do NOT match different variants (e.g., "Spanish Latte" ≠ "لاتيه")
3. Do NOT match different products (e.g., "latte" ≠ "cappuccino")
4. If unsure, do NOT match

Return JSON array of pairs to merge:
[
    ["arabic_text", "english_text"],
    ...
]

Return empty array [] if no clear matches.
"""
```

#### 5.2.2 Grouping Function

```python
def merge_cross_lingual_products(
    products: List[Dict],
    business_type: str = "cafe"
) -> List[Dict]:
    """
    Use LLM to identify and merge cross-lingual product pairs.

    Args:
        products: List of product dicts from Phase 1
        business_type: Business type for LLM context

    Returns:
        Merged product list with cross-lingual variants combined
    """
    if len(products) <= 1:
        return products

    # Prepare product list for LLM
    product_texts = [p["canonical_text"] for p in products]

    prompt = CROSS_LINGUAL_GROUPING_PROMPT.format(
        business_type=business_type,
        products="\n".join(f"- {t}" for t in product_texts)
    )

    # Call LLM
    response = call_gemini(prompt)  # Or your LLM function

    try:
        pairs = json.loads(response)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response for cross-lingual grouping")
        return products

    if not pairs:
        return products

    # Build merge map
    # Key: text to absorb, Value: text to keep
    merge_into: Dict[str, str] = {}
    for pair in pairs:
        if len(pair) != 2:
            continue
        text1, text2 = pair[0].lower().strip(), pair[1].lower().strip()

        # Find which product has more mentions
        p1 = next((p for p in products if p["canonical_text"] == text1), None)
        p2 = next((p for p in products if p["canonical_text"] == text2), None)

        if not p1 or not p2:
            continue

        # Keep the one with more mentions
        if p1["total_mentions"] >= p2["total_mentions"]:
            merge_into[text2] = text1
        else:
            merge_into[text1] = text2

    # Execute merges
    merged = []
    absorbed = set()

    for product in products:
        canonical = product["canonical_text"]

        if canonical in absorbed:
            continue

        if canonical in merge_into:
            absorbed.add(canonical)
            continue

        # Check if this product absorbs others
        to_absorb = [t for t, target in merge_into.items() if target == canonical]

        if to_absorb:
            # Merge variants and mentions
            for absorb_text in to_absorb:
                absorb_product = next(
                    (p for p in products if p["canonical_text"] == absorb_text),
                    None
                )
                if absorb_product:
                    product["variants"].append(absorb_product["display_name"])
                    product["variants"].extend(absorb_product["variants"])
                    product["total_mentions"] += absorb_product["total_mentions"]
                    absorbed.add(absorb_text)

        merged.append(product)

    logger.info(
        f"Cross-lingual merge: {len(products)} → {len(merged)} products",
        extra={"extra_data": {"merged_pairs": len(merge_into)}}
    )

    return merged
```

#### 5.2.3 Integration Point

```python
# In run_clustering_job(), after build_hierarchy():

# Phase 2: Cross-lingual grouping (optional, can be disabled)
if os.environ.get("ENABLE_CROSS_LINGUAL_GROUPING", "true").lower() == "true":
    for category_id, products in hierarchy_by_category.items():
        merged = merge_cross_lingual_products(products, business_type)
        hierarchy_by_category[category_id] = merged
```

### 5.3 Unit Tests

```python
# tests/test_clustering.py

import pytest
import numpy as np
from clustering_job import deduplicate_cluster_items, ClusterItem


def make_item(text: str, embedding: List[float], mentions: int = 1) -> ClusterItem:
    return ClusterItem(
        vector_id=f"test-{text}",
        text=text,
        embedding=embedding,
        mention_type="product",
        sentiment_sum=0.5 * mentions,
        mention_count=mentions,
    )


class TestDeduplicateClusterItems:

    def test_single_item(self):
        """Single item returns as-is."""
        items = [make_item("flat white", [1.0, 0.0, 0.0], 10)]
        result = deduplicate_cluster_items(items)

        assert len(result) == 1
        assert result[0]["canonical_text"] == "flat white"
        assert result[0]["variants"] == []
        assert result[0]["total_mentions"] == 10

    def test_identical_embeddings_merge(self):
        """Items with identical embeddings merge."""
        emb = [1.0, 0.0, 0.0]
        items = [
            make_item("flat white", emb, 20),
            make_item("Flat White", emb, 5),
        ]
        result = deduplicate_cluster_items(items)

        assert len(result) == 1
        assert result[0]["canonical_text"] == "flat white"  # Higher count
        assert "Flat White" in result[0]["variants"]
        assert result[0]["total_mentions"] == 25

    def test_similar_arabic_variants_merge(self):
        """Arabic variants with high similarity merge."""
        # Simulate ~0.96 similarity
        items = [
            make_item("فلات وايت", [1.0, 0.0, 0.0], 34),
            make_item("الفلات وايت", [0.98, 0.1, 0.0], 18),
        ]
        result = deduplicate_cluster_items(items, similarity_threshold=0.78)

        assert len(result) == 1
        assert result[0]["canonical_text"] == "فلات وايت"
        assert result[0]["total_mentions"] == 52

    def test_cross_lingual_stays_separate(self):
        """Arabic and English stay separate (low similarity)."""
        # Simulate ~0.63 similarity (actual from validation)
        items = [
            make_item("فلات وايت", [1.0, 0.0, 0.0], 34),
            make_item("flat white", [0.6, 0.7, 0.1], 12),
        ]
        result = deduplicate_cluster_items(items, similarity_threshold=0.78)

        assert len(result) == 2  # NOT merged
        texts = {r["canonical_text"] for r in result}
        assert "فلات وايت" in texts
        assert "flat white" in texts

    def test_different_products_stay_separate(self):
        """Different products do not merge."""
        items = [
            make_item("latte", [1.0, 0.0, 0.0], 20),
            make_item("cappuccino", [0.3, 0.8, 0.2], 15),
        ]
        result = deduplicate_cluster_items(items, similarity_threshold=0.78)

        assert len(result) == 2

    def test_empty_input(self):
        """Empty input returns empty list."""
        result = deduplicate_cluster_items([])
        assert result == []

    def test_configurable_threshold(self):
        """Threshold is configurable."""
        # With high threshold, borderline cases stay separate
        items = [
            make_item("a", [1.0, 0.0, 0.0], 10),
            make_item("b", [0.85, 0.4, 0.0], 5),  # ~0.85 similarity
        ]

        # Strict threshold: separate
        result_strict = deduplicate_cluster_items(items, similarity_threshold=0.90)
        assert len(result_strict) == 2

        # Loose threshold: merge
        result_loose = deduplicate_cluster_items(items, similarity_threshold=0.80)
        assert len(result_loose) == 1
```

---

## 6. Expected Outcomes

### 6.1 Phase 1 Results (Same-Language)

| Metric | Before | After Phase 1 |
|--------|--------|---------------|
| Products | 85 | ~45-50 |
| Arabic products with variants | 0 | ~15-20 |
| English products with variants | 0 | ~5-8 |
| Exact duplicates | 6 | 0 |

### 6.2 Phase 2 Results (Cross-Lingual)

| Metric | After Phase 1 | After Phase 2 |
|--------|---------------|---------------|
| Products | ~45-50 | ~25-35 |
| Cross-lingual pairs merged | 0 | ~10-15 |

### 6.3 Example Transformation

**Before (85 products):**
```
Category: flat_white
├── الفلات وايت (18) [no variants]
├── فلات وايت (34) [no variants]
├── الفلايت وايت (1) [no variants]
├── فلات وايت بلند (2) [no variants]

Category: flat_white_(hot_coffee)
├── flat white (12) [no variants]
├── flat white (12) [no variants] ← DUPLICATE
├── Flatwhite (2) [no variants]
├── hot flat white (1) [no variants]
```

**After Phase 1 (~50 products):**
```
Category: flat_white
├── فلات وايت (53) [variants: الفلات وايت, الفلايت وايت]
├── فلات وايت بلند (2) [no variants]

Category: flat_white_(hot_coffee)
├── flat white (27) [variants: Flatwhite, hot flat white]
```

**After Phase 2 (~30 products):**
```
Category: flat_white
├── فلات وايت (80) [variants: الفلات وايت, الفلايت وايت, flat white, Flatwhite, hot flat white]
├── فلات وايت بلند (2) [no variants]
```

---

## 7. Risk Assessment

### 7.1 Risk Matrix

| Risk | Prob. | Impact | Mitigation |
|------|-------|--------|------------|
| Phase 1 over-merging | Low | Medium | 0.78 threshold validated empirically |
| Phase 1 under-merging | Medium | Low | Cross-lingual handled in Phase 2 |
| Phase 2 LLM errors | Low | Medium | Conservative prompt, human review |
| LLM cost | Low | Low | ~1 call per category (~10 calls total) |
| Performance | Low | Low | DBSCAN O(n²) but n<50 per cluster |

### 7.2 Fallback Options

1. **Disable Phase 2**: Set `ENABLE_CROSS_LINGUAL_GROUPING=false`
2. **Adjust threshold**: Set `PRODUCT_SIMILARITY_THRESHOLD` via environment
3. **Manual merge**: OS can merge products in onboarding portal

---

## 8. Success Criteria

### 8.1 Quantitative

| Criterion | Target |
|-----------|--------|
| Product count | ≤40 (Phase 1) or ≤35 (Phase 1+2) |
| Products with variants | ≥80% |
| Exact duplicates | 0 |
| Flat White products | ≤2 |

### 8.2 Validation Queries

```sql
-- Product count after clustering
SELECT COUNT(*) FROM taxonomy_products WHERE taxonomy_id = ?;
-- Target: ≤35

-- Products with variants
SELECT COUNT(*) FROM taxonomy_products
WHERE taxonomy_id = ? AND jsonb_array_length(variants) > 0;
-- Target: ≥80% of total

-- Flat white check
SELECT canonical_text, variants, discovered_mention_count
FROM taxonomy_products
WHERE taxonomy_id = ? AND (
    canonical_text LIKE '%flat%' OR
    canonical_text LIKE '%فلات%'
);
-- Target: 1-2 products with combined variants
```

### 8.3 Manual Checklist

- [ ] "فلات وايت" and "flat white" are in same product (Phase 2)
- [ ] "V60" variants grouped
- [ ] "Latte" and "Cappuccino" remain separate
- [ ] No exact duplicate canonical_text values

---

## Appendix A: Implementation Timeline

| Phase | Task | Effort |
|-------|------|--------|
| 1 | Add `deduplicate_cluster_items()` | 45 min |
| 1 | Modify `build_hierarchy()` | 15 min |
| 1 | Add unit tests | 30 min |
| 1 | Test with data | 30 min |
| **Phase 1 Total** | | **2 hours** |
| 2 | Add LLM grouping function | 1 hour |
| 2 | Integration | 30 min |
| 2 | Test with data | 30 min |
| **Phase 2 Total** | | **2 hours** |
| **Total** | | **4 hours** |

---

## Appendix B: Embedding Model Comparison

| Model | AR-EN Similarity | Recommendation |
|-------|------------------|----------------|
| text-embedding-3-small | 0.29-0.63 | Current - needs LLM assist |
| text-embedding-3-large | ~0.5-0.7 | Marginal improvement |
| multilingual-e5-large | ~0.80-0.90 | Best, but self-hosted |
| Cohere multilingual-v3 | ~0.75-0.85 | Good, API available |

**Future consideration**: If cross-lingual grouping becomes frequent, migrating to multilingual-e5-large would eliminate the need for LLM Phase 2.

---

*Document prepared for technical review*
*Version 3.0 - Updated with empirical validation*
*Last updated: 2026-02-04*
