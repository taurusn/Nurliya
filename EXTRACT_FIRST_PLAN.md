# Extract-First Pipeline Refactor Plan

## Overview

Refactor the worker pipeline to a **two-phase approach**:

1. **Phase 1: Extraction Only** - Extract mentions, build taxonomy, wait for approval
2. **Phase 2: Sentiment Analysis** - After taxonomy approved, analyze with taxonomy context

```
CURRENT (wrong order):
  Review → analyze_review() → save → extract_mentions() → save
           [sentiment first]        [extraction second]

NEW (correct order):
  PHASE 1: Review → extract_mentions() → RawMention → Clustering → Taxonomy → OS Approves
                    [extraction only]

  PHASE 2: Review → analyze_with_taxonomy() → ReviewAnalysis
                    [sentiment WITH approved products/categories]
```

---

## Why This Order?

| Aspect | Current | New |
|--------|---------|-----|
| **Topics** | LLM guesses generic topics | LLM matches to APPROVED products/categories |
| **Accuracy** | "drinks was good" | "Spanish Latte was good" (actual product) |
| **Taxonomy-aligned** | Mentions are afterthought | Taxonomy is foundation for analysis |
| **Summaries** | Generic | References actual approved products |

---

## Two-Phase Flow

### Phase 1: Extraction (New Places)

```
New Scrape Job
      ↓
┌─────────────────────────────────────────────────────────┐
│  EXTRACTION_ONLY_MODE = true                             │
│                                                          │
│  For each review:                                        │
│    1. extract_mentions(review_text) → products, aspects  │
│    2. Entity resolution via Qdrant                       │
│    3. Save to RawMention table                           │
│                                                          │
│  After job complete:                                     │
│    4. trigger_taxonomy_clustering()                      │
│    5. Draft taxonomy created                             │
└─────────────────────────────────────────────────────────┘
      ↓
OS Reviews in Onboarding Portal
      ↓
OS Clicks "Publish" → Taxonomy becomes ACTIVE
      ↓
Trigger Phase 2
```

### Phase 2: Sentiment Analysis (After Approval)

```
Taxonomy Published
      ↓
┌─────────────────────────────────────────────────────────┐
│  SENTIMENT_ANALYSIS_MODE (new)                           │
│                                                          │
│  1. Fetch approved taxonomy for place                    │
│     - List of approved products (Spanish Latte, V60...)  │
│     - List of approved categories (Hot Coffee, Service)  │
│                                                          │
│  2. For each review:                                     │
│     a. Get already-extracted mentions from RawMention    │
│     b. Match mentions to approved products/categories    │
│     c. analyze_with_taxonomy(review_text, matched_items) │
│        → LLM returns: sentiment, score, summaries, reply │
│        → LLM told: "This review mentions these products" │
│     d. Save to ReviewAnalysis                            │
│                                                          │
│  3. After all reviews analyzed:                          │
│     - Send email report                                  │
│     - Detect anomalies                                   │
└─────────────────────────────────────────────────────────┘
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `pipline/llm_client.py` | Add `analyze_with_taxonomy()` function + new prompt |
| `pipline/worker.py` | Add sentiment analysis mode, modify flow |
| `pipline/api.py` | Trigger sentiment analysis after publish |
| `pipline/rabbitmq.py` | Add `SENTIMENT_ANALYSIS_QUEUE` (optional) |

**No schema changes needed** - ReviewAnalysis table stays the same

---

## Implementation Steps

### Step 1: Add analyze_with_taxonomy() to llm_client.py

New prompt that receives approved products/categories:

```python
TAXONOMY_AWARE_PROMPT = """You are a review analysis assistant for Saudi businesses.

You will receive:
1. The original review text
2. The APPROVED products/categories for this business

Your job is to:
1. Determine overall sentiment (positive/neutral/negative)
2. Identify which APPROVED products/categories are mentioned in this review
3. Generate summaries that reference the SPECIFIC products mentioned
4. Generate a reply that addresses the SPECIFIC products/issues

APPROVED PRODUCTS FOR THIS BUSINESS:
{products_list}

APPROVED CATEGORIES FOR THIS BUSINESS:
{categories_list}

RULES:
- Only match to products/categories from the approved list above
- If review mentions something not in the list, note it but focus on approved items
- Summaries should mention the specific product names
- Reply should acknowledge specific products praised or complained about

OUTPUT FORMAT (JSON only):
{
  "sentiment": "positive" | "neutral" | "negative",
  "score": 0.0-1.0,
  "matched_products": ["product_id1", "product_id2"],
  "matched_categories": ["category_id1"],
  "language": "ar" | "en" | "arabizi",
  "urgent": true | false,
  "summary_ar": "ملخص يذكر المنتجات المحددة",
  "summary_en": "Summary mentioning specific products",
  "suggested_reply_ar": "رد يذكر المنتج المحدد"
}"""
```

### Step 2: Modify Worker Flow

Add `mode` parameter to message processing:
- `"extraction"` - Only extract mentions, no sentiment analysis
- `"sentiment"` - Only sentiment analysis (taxonomy already exists)
- `"full"` - Both (for new reviews after taxonomy approved)

### Step 3: Trigger After Publish

When taxonomy is published, queue all reviews for sentiment analysis.

### Step 4: Default to Extraction-Only

New scrapes should default to extraction-only mode until taxonomy is approved.

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| New scrape, no taxonomy | Extraction only, wait for approval |
| Taxonomy exists, new review | Full flow (extract + sentiment with taxonomy) |
| Re-scrape existing place | Extract new reviews, sentiment uses existing taxonomy |
| Taxonomy rejected/deleted | Fall back to original `analyze_review()` |

---

## Backward Compatibility

- `ReviewAnalysis` schema unchanged
- Original `analyze_review()` kept as fallback
- Existing data unaffected
- Easy rollback by setting `mode="full"`

---

## Related Documents

- Progress tracker: `/home/42group/nurliya/EXTRACT_FIRST_PROGRESS.md`
- Taxonomy plan: `/home/42group/nurliya/TAXONOMY_PLAN.md`
- Phase 4 plan: `/home/42group/nurliya/PHASE4_PLAN.md`
