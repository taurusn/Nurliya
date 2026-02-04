# Hybrid Matching Test Results

## Summary

| Metric | Value |
|--------|-------|
| Unit Tests | **19/19 passed** |
| Orphan Rescue Rate | **7.8%** (8/102 orphans) |
| False Positive Rate | **0%** (with min_length=3) |

## Key Findings

### 1. Text Matching Works for Obvious Cases

**V60 Guatemala problem solved:**
```
Mention: "V60 جواتيمالا"
Product: "V60"
Vector Score: 0.58 (below 0.80 threshold)
Text Match: TRUE (canonical "v60" is substring of mention)
Final: MATCHED with score 1.0
```

### 2. Minimum Length Prevents False Positives

Without min_length:
- "بن" (coffee beans, 2 chars) matched "بنانا" (banana) ❌

With min_length=3:
- "بن" no longer matches ✅

### 3. Variant Quality Matters

Clustering put incorrect items as variants:
- "CORTADO COFFEE" as variant of "قهوة اليوم أثيوبية" (Ethiopian coffee)
- "coffee latte" as variant of "قهوة اليوم أثيوبية"

**Recommendation:** Use canonical-only matching initially, add variants selectively.

## Rescued Orphans (Real Data)

| Mention | Product | Why It Works |
|---------|---------|--------------|
| V60 Guava Banana Beans | V60 | "v60" in mention |
| V60 بارد | V60 | "v60" in mention |
| Semba on V60 | V60 | "v60" in mention |
| Ethiopian V60 | V60 | "v60" in mention |
| V60 اثيوبي قوجي بارد | V60 | "v60" in mention |
| V60 جواتيمالا | V60 | "v60" in mention |
| محصول نفيسه الاثيوبي | اثيوبي | "اثيوبي" in mention |
| اللاتيه الحار | اللاتيه | "اللاتيه" in mention |

## Algorithm

```
hybrid_match(mention, product, vector_score):
    1. Normalize both texts (lowercase, strip)
    2. If len(canonical) >= 3 AND canonical IN mention:
       → return MATCH, score=1.0, method="text"
    3. If len(mention) >= 3 AND mention IN canonical:
       → return MATCH, score=1.0, method="text"
    4. If vector_score >= 0.80:
       → return MATCH, score=vector_score, method="vector"
    5. Else:
       → return NO_MATCH, score=vector_score, method="none"
```

## Integration Points

### Stage 1: Post-Clustering (clustering_job.py)
```python
# After save_draft_taxonomy(), before return:
from hybrid_matcher import rescue_orphan_mentions
rescued = rescue_orphan_mentions(session, taxonomy_id, use_variants=False)
logger.info(f"Text matching rescued {rescued} orphan mentions")
```

### Stage 2: Runtime Resolution (worker.py)
```python
# In _resolve_mention(), before vector search:
from hybrid_matcher import text_matches_product

for product in products:
    if text_matches_product(mention_text, product.canonical_text):
        # Link mention to product with score 1.0
        return product.id, 1.0, "text"

# Fall back to vector search...
```

## Performance

- Text matching: O(n*m) where n=orphans, m=products
- For 102 orphans × 18 products = 1,836 comparisons
- Each comparison: 2-3 string operations
- Total: < 10ms

## Conclusion

Hybrid matching is **safe and effective** for rescuing obvious text matches that vectors miss. The 7.8% rescue rate may seem low, but these are high-confidence matches that would otherwise show as confusing "58% similar" to users.

**Recommended:** Implement in both clustering and runtime resolution paths.
