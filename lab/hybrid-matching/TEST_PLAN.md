# Hybrid Text + Vector Matching Test Plan

## Problem Statement

Vector embeddings miss obvious text matches:
- "V60 جواتيمالا" has only 58% vector similarity to "V60"
- But it clearly CONTAINS "V60" - should be 100% match

## Hypothesis

Combining text-based matching with vector similarity will:
1. Catch obvious substring matches that vectors miss
2. Maintain vector matching for synonyms/misspellings
3. Reduce orphan mentions significantly

## Test Cases

### Test Case 1: Substring Match (Product in Mention)
| Mention | Product | Expected | Reason |
|---------|---------|----------|--------|
| "V60 جواتيمالا" | "V60" | MATCH | Product name is substring of mention |
| "اللاتيه الساخن" | "لاتيه" | MATCH | Product name is substring |
| "flat white hot" | "flat white" | MATCH | Product name is substring |

### Test Case 2: Reverse Substring (Mention in Product)
| Mention | Product | Expected | Reason |
|---------|---------|----------|--------|
| "v60" | "V60 كولومبي" | MATCH | Mention is substring of product |
| "latte" | "iced latte" | MATCH | Mention is substring |

### Test Case 3: Variant Matching
| Mention | Product Canonical | Variants | Expected |
|---------|------------------|----------|----------|
| "V60 برازيلي" | "V60" | ["V60 برازيلي", "V60 كولومبي"] | MATCH |
| "iced latte" | "latte" | ["hot latte", "iced latte"] | MATCH |

### Test Case 4: No Text Match - Vector Only
| Mention | Product | Text Match | Vector Score | Expected |
|---------|---------|------------|--------------|----------|
| "قهوة مثلجة" | "iced coffee" | NO | 0.85 | VECTOR MATCH |
| "فلات وايت" | "flat white" | NO | 0.92 | VECTOR MATCH |

### Test Case 5: No Match At All
| Mention | Product | Text Match | Vector Score | Expected |
|---------|---------|------------|--------------|----------|
| "كيكة الشوكولاتة" | "V60" | NO | 0.30 | NO MATCH |

### Test Case 6: Edge Cases
| Mention | Product | Expected | Reason |
|---------|---------|----------|--------|
| "V60" | "V60" | MATCH | Exact match |
| "v60" | "V60" | MATCH | Case insensitive |
| "  V60  " | "V60" | MATCH | Whitespace handling |
| "" | "V60" | NO MATCH | Empty string |
| "V60" | "" | NO MATCH | Empty product |

## Implementation Plan

### Phase 1: Text Matching Function
```python
def text_matches_product(mention_text: str, canonical: str, variants: list) -> bool:
    # Normalize
    # Check substring both ways
    # Check variants
    # Return bool
```

### Phase 2: Hybrid Matching Function
```python
def hybrid_match(mention_text: str, product, vector_score: float) -> tuple[bool, float]:
    # Try text match first
    # If text match: return (True, 1.0)
    # Else if vector_score >= threshold: return (True, vector_score)
    # Else: return (False, vector_score)
```

### Phase 3: Integration Points
1. `save_draft_taxonomy()` - Post-clustering orphan sweep
2. `_resolve_mention()` - Runtime resolution for new reviews

## Success Criteria

1. "V60 جواتيمالا" matches "V60" with score 1.0
2. All Test Cases pass
3. No regression on existing vector matches
4. Performance: Text match < 1ms per mention

## Test Data

Using real data from current taxonomy:
- Taxonomy ID: a56441c9-e1b6-4cf6-85b5-ead7ea9397b8
- Product "V60": 48913a0f-9903-404a-af89-b9b15ca68b3c
- Orphan: "V60 جواتيمالا"
