# Hybrid Discovery Engine: Seed, Learn, Discover

## Overview

Implement a three-layer intelligence system for taxonomy building:
1. **Seeds (Bootstrap)** - Predefined anchor vectors for cold start
2. **Memory (Learn)** - Vectors learned from approved taxonomies
3. **Discovery** - HDBSCAN clustering for unknown items

**Key Insight**:
- **Aspect categories** → Seeds → Memory → Discovery (Service, Quality, Price)
- **Product categories** → Seeds → Memory → Discovery (Hot Drinks, Pastries, Beans)
- **Individual products** → Discovery only, placed under learned categories (V60, فلات وايت)

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │           SEMANTIC ROUTER               │
                    │         (New: Phase 5 Modified)         │
                    └──────────────┬──────────────────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │   LAYER 1   │         │   LAYER 2   │         │   LAYER 3   │
    │   SEEDS     │         │   MEMORY    │         │  DISCOVERY  │
    │  (Anchors)  │         │  (Learned)  │         │  (HDBSCAN)  │
    └─────────────┘         └─────────────┘         └─────────────┘
    Threshold: 0.85          Threshold: 0.88         No threshold
    Source: seed.py          Source: Approved         Source: Clustering
                             taxonomies
```

## Database Schema Changes

### New Table: `category_anchors`
```sql
CREATE TABLE category_anchors (
    id UUID PRIMARY KEY,
    business_type VARCHAR(100) NOT NULL,  -- 'coffee_shop', 'restaurant'
    category_name VARCHAR(255) NOT NULL,  -- 'Service', 'Quality', 'Price'
    display_name_en VARCHAR(255),
    display_name_ar VARCHAR(255),
    is_aspect BOOLEAN DEFAULT TRUE,       -- Aspects only for now
    centroid_embedding VECTOR(768),       -- Average embedding
    sample_terms TEXT[],                  -- ['الخدمة', 'التعامل', 'شباب']
    mention_count INTEGER DEFAULT 0,      -- Total mentions matched
    source VARCHAR(50) DEFAULT 'seed',    -- 'seed' or 'learned'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(business_type, category_name)
);
```

### New Table: `anchor_examples`
```sql
CREATE TABLE anchor_examples (
    id UUID PRIMARY KEY,
    anchor_id UUID REFERENCES category_anchors(id),
    text VARCHAR(500) NOT NULL,           -- 'الخدمة ممتازة'
    embedding VECTOR(768) NOT NULL,
    mention_count INTEGER DEFAULT 1,
    sentiment_avg FLOAT DEFAULT 0.5,
    source VARCHAR(50) DEFAULT 'seed',    -- 'seed' or 'learned'
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Files to Modify

### 1. `pipline/database.py`
- Add `CategoryAnchor` model
- Add `AnchorExample` model

### 2. `pipline/vector_store.py`
- Add `ANCHORS_COLLECTION` constant
- Add `search_anchors()` function
- Add `upsert_anchor()` function

### 3. `pipline/clustering_job.py` (Main Changes)
**Location: `run_clustering_job()` line 1052**

```python
def run_clustering_job(...):
    # Step 0 (NEW): Load anchors for business type
    anchors = load_anchors_for_business(business_type)

    # Step 2 (MODIFIED): Separate and CLASSIFY aspects
    for item in all_vectors:
        if item.mention_type == "aspect":
            # NEW: Try anchor classification first
            anchor_match = classify_to_anchor(item.embedding, anchors, threshold=0.85)
            if anchor_match:
                item.anchor_id = anchor_match.id
                item.anchor_category = anchor_match.category_name
            else:
                aspect_items.append(item)  # Falls to Discovery
        else:
            product_items.append(item)  # Products always go to Discovery

    # Step 4 (MODIFIED): Cluster ONLY unmatched aspects
    unmatched_aspects = [a for a in aspect_items if not a.anchor_id]
    if unmatched_aspects:
        # Run HDBSCAN only on truly unknown aspects
        aspect_embeddings = np.array([item.embedding for item in unmatched_aspects])
        labels, probs = cluster_mentions(aspect_embeddings)
```

### 4. New File: `pipline/anchor_manager.py`
```python
"""
Anchor Management for Seed, Learn, Discover architecture.
"""

def load_anchors_for_business(business_type: str) -> List[Anchor]:
    """Load all anchors (seeds + learned) for a business type."""

def classify_to_anchor(embedding: List[float], anchors: List[Anchor],
                       threshold: float = 0.85) -> Optional[Anchor]:
    """Classify a mention to the nearest anchor if above threshold."""

def update_anchor_stats(anchor_id: str, mention: dict):
    """Update anchor statistics when a mention is matched."""

def learn_from_approved_taxonomy(taxonomy_id: str):
    """Extract new anchors from an approved taxonomy."""

def create_seed_anchors(business_type: str, anchors: List[dict]):
    """Initialize seed anchors for a business type (cold start)."""
```

### 5. New File: `pipline/seeds/coffee_shop.py`
```python
"""
Seed anchors for Coffee Shop business type.
Includes both ASPECT categories and PRODUCT categories.
"""

# Aspect categories (has_products=False)
ASPECT_SEEDS = [
    {
        "category": "service",
        "display_name_en": "Service Quality",
        "display_name_ar": "جودة الخدمة",
        "is_aspect": True,
        "examples": [
            "الخدمة ممتازة",
            "التعامل راقي",
            "الموظفين محترمين",
            "شباب محترفين",
            "الاستقبال رائع",
        ]
    },
    {
        "category": "quality",
        "display_name_en": "Product Quality",
        "display_name_ar": "جودة المنتج",
        "is_aspect": True,
        "examples": [
            "القهوة لذيذة",
            "جودة عالية",
            "الطعم ممتاز",
            "قهوة احترافية",
        ]
    },
    {
        "category": "atmosphere",
        "display_name_en": "Atmosphere",
        "display_name_ar": "الأجواء",
        "is_aspect": True,
        "examples": [
            "المكان هادئ",
            "الأجواء جميلة",
            "ديكور حلو",
            "مكان مريح",
        ]
    },
    {
        "category": "price",
        "display_name_en": "Price & Value",
        "display_name_ar": "السعر والقيمة",
        "is_aspect": True,
        "examples": [
            "الأسعار معقولة",
            "غالي شوي",
            "سعر مناسب",
            "يستاهل السعر",
        ]
    },
    {
        "category": "cleanliness",
        "display_name_en": "Cleanliness",
        "display_name_ar": "النظافة",
        "is_aspect": True,
        "examples": [
            "المكان نظيف",
            "نظافة ممتازة",
        ]
    },
    {
        "category": "location",
        "display_name_en": "Location & Access",
        "display_name_ar": "الموقع",
        "is_aspect": True,
        "examples": [
            "الموقع ممتاز",
            "سهل الوصول",
            "مواقف متوفرة",
        ]
    },
]

# Product categories (has_products=True) - products discovered under these
PRODUCT_CATEGORY_SEEDS = [
    {
        "category": "hot_drinks",
        "display_name_en": "Hot Drinks",
        "display_name_ar": "مشروبات ساخنة",
        "is_aspect": False,
        "examples": [
            "لاتيه",
            "كابتشينو",
            "فلات وايت",
            "اسبريسو",
            "موكا",
            "أمريكانو",
        ]
    },
    {
        "category": "cold_drinks",
        "display_name_en": "Cold Drinks",
        "display_name_ar": "مشروبات باردة",
        "is_aspect": False,
        "examples": [
            "آيس لاتيه",
            "كولد برو",
            "آيس أمريكانو",
            "فرابتشينو",
        ]
    },
    {
        "category": "pour_over",
        "display_name_en": "Pour Over Coffee",
        "display_name_ar": "قهوة مقطرة",
        "is_aspect": False,
        "examples": [
            "V60",
            "كيمكس",
            "قهوة مفلترة",
            "دريب",
        ]
    },
    {
        "category": "pastries",
        "display_name_en": "Pastries & Desserts",
        "display_name_ar": "حلويات ومعجنات",
        "is_aspect": False,
        "examples": [
            "كرواسون",
            "كيك",
            "تشيز كيك",
            "تيراميسو",
            "كوكيز",
        ]
    },
    {
        "category": "beans",
        "display_name_en": "Coffee Beans",
        "display_name_ar": "حبوب القهوة",
        "is_aspect": False,
        "examples": [
            "اثيوبي",
            "كولومبي",
            "برازيلي",
            "يمني",
        ]
    },
    {
        "category": "food",
        "display_name_en": "Food",
        "display_name_ar": "طعام",
        "is_aspect": False,
        "examples": [
            "ساندويتش",
            "سلطة",
            "فطور",
            "توست",
        ]
    },
]

ALL_SEEDS = ASPECT_SEEDS + PRODUCT_CATEGORY_SEEDS
```

### 6. New CLI: `pipline/seed_anchors.py`
```python
"""
CLI tool to initialize seed anchors.
Usage: python seed_anchors.py coffee_shop
"""

def seed_business_type(business_type: str):
    """Initialize seeds for a business type."""
    from seeds import coffee_shop, restaurant

    seeds_map = {
        "coffee_shop": coffee_shop.ASPECT_SEEDS,
        "restaurant": restaurant.ASPECT_SEEDS,
    }

    seeds = seeds_map.get(business_type)
    if not seeds:
        raise ValueError(f"Unknown business type: {business_type}")

    # Generate embeddings for each example
    for seed in seeds:
        examples = seed["examples"]
        embeddings = embedding_client.generate_embeddings(examples)

        # Compute centroid
        centroid = np.mean(embeddings, axis=0)

        # Save anchor
        anchor = CategoryAnchor(
            business_type=business_type,
            category_name=seed["category"],
            display_name_en=seed["display_name_en"],
            display_name_ar=seed["display_name_ar"],
            is_aspect=True,
            centroid_embedding=centroid.tolist(),
            sample_terms=examples,
            source="seed",
        )
        session.add(anchor)

        # Save individual examples
        for text, emb in zip(examples, embeddings):
            example = AnchorExample(
                anchor_id=anchor.id,
                text=text,
                embedding=emb.tolist(),
                source="seed",
            )
            session.add(example)

    session.commit()
    print(f"Seeded {len(seeds)} anchors for {business_type}")
```

## Modified Clustering Flow

```
BEFORE (Current):
┌─────────────────────────────────────────────────────────────────┐
│  All Aspects ──► HDBSCAN ──► Clusters ──► LLM Label ──► Save   │
│  Result: 1 giant "Coffee & Location" with 1419 mentions        │
│                                                                 │
│  All Products ──► HDBSCAN ──► Clusters ──► LLM Label ──► Save  │
│  Result: Random category names, duplicates                     │
└─────────────────────────────────────────────────────────────────┘

AFTER (Hybrid):
┌─────────────────────────────────────────────────────────────────┐
│  ASPECT MENTIONS (القهوة، الخدمة، المكان)                       │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LAYER 1: Query Seed Anchors (threshold 0.85)            │   │
│  │   "الخدمة ممتازة" → matches "Service" seed → CLASSIFY   │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │ (unmatched)                                             │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LAYER 2: Query Learned Anchors (threshold 0.88)         │   │
│  │   "جبار" → matches learned "Quality" → CLASSIFY         │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │ (unmatched)                                             │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LAYER 3: HDBSCAN Discovery                              │   │
│  │   Unknown aspects → Cluster → LLM Label → New Category  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Result: Service(500), Quality(400), Atmosphere(300), etc.     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  PRODUCT MENTIONS (فلات وايت، V60، كرواسون)                     │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ STEP 1: Classify to CATEGORY anchor                     │   │
│  │   "فلات وايت" → matches "Hot Drinks" category → assign  │   │
│  │   "V60" → matches "Pour Over" category → assign         │   │
│  │   "كرواسون" → matches "Pastries" category → assign      │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ STEP 2: Discover PRODUCTS within category               │   │
│  │   Hot Drinks: [فلات وايت, لاتيه, كابتشينو] (clustered)  │   │
│  │   Pour Over: [V60, كيمكس] (clustered)                   │   │
│  │   Products are NEW, categories are KNOWN                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Result: Consistent categories, unique products per place      │
└─────────────────────────────────────────────────────────────────┘
```

## Learning Loop (Post-Approval)

```python
def learn_from_approved_taxonomy(taxonomy_id: str):
    """Called when a taxonomy is published/approved."""

    taxonomy = get_taxonomy(taxonomy_id)
    business_type = taxonomy.place.category

    for category in taxonomy.categories:
        if not category.is_approved or category.has_products:
            continue  # Only learn from approved aspect categories

        # Get all mentions in this category
        mentions = get_category_mentions(category.id)

        # Check if this matches an existing anchor
        existing_anchor = find_anchor_by_name(business_type, category.name)

        if existing_anchor:
            # UPDATE existing anchor with new examples
            for mention in mentions:
                if not is_example_exists(existing_anchor.id, mention.text):
                    add_anchor_example(existing_anchor.id, mention.text, mention.embedding)

            # Recompute centroid
            update_anchor_centroid(existing_anchor.id)

        else:
            # CREATE new learned anchor
            create_learned_anchor(
                business_type=business_type,
                category_name=category.name,
                display_name_en=category.display_name_en,
                display_name_ar=category.display_name_ar,
                examples=mentions,
                source="learned",
            )
```

## Implementation Order

### Phase 1: Database & Seeds (Day 1)
1. Add `CategoryAnchor` and `AnchorExample` models to `database.py`
2. Create migration
3. Create `seeds/coffee_shop.py` with Arabic aspect seeds
4. Create `seed_anchors.py` CLI tool
5. Run seeding for coffee_shop

### Phase 2: Anchor Classification (Day 2)
1. Create `anchor_manager.py` with core functions
2. Modify `clustering_job.py` to use anchor classification
3. Add Qdrant `ANCHORS_COLLECTION` support
4. Test with existing taxonomy

### Phase 3: Learning Loop (Day 3)
1. Add `learn_from_approved_taxonomy()` function
2. Hook into taxonomy publish API
3. Test learning from Specialty Bean taxonomy

### Phase 4: Verification (Day 4)
1. Re-run clustering for Specialty Bean
2. Verify aspects are properly classified (no more 1419 catch-all)
3. Check learned anchors are created

## Verification Plan

1. **Cold Start Test**:
   - Clear all anchors
   - Run `seed_anchors.py coffee_shop`
   - Verify 6 aspect anchors created in DB
   - Verify embeddings in Qdrant

2. **Classification Test**:
   - Re-run clustering for Specialty Bean
   - Check "Coffee & Location" is split into Service, Quality, Atmosphere, etc.
   - Verify aspect counts are reasonable (~200-500 per category, not 1419)

3. **Learning Test**:
   - Approve Specialty Bean taxonomy
   - Check new learned examples added to anchors
   - Process new cafe
   - Verify learned terms are matched

## Metrics to Track

| Metric | Before | After (Target) |
|--------|--------|----------------|
| Aspects matched to anchors | 0% | >70% |
| Largest aspect category | 1419 | <500 |
| Number of aspect categories | 3 | 6 (Service, Quality, Atmosphere, Price, Cleanliness, Location) |
| Products matched to category anchors | 0% | >80% |
| Product category consistency | Random | Consistent (Hot Drinks, Cold Drinks, etc.) |
| Orphan aspects | 41 | <15 |
| Orphan products | 94 | <30 |
| Cold start time (new business type) | N/A | <5 min (seed loading) |
| Warm start accuracy | N/A | >85% (learned anchors) |

---

## Future: Complete Learning Concept

### Anchor Sources (Priority Order)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WHO PROVIDES ANCHORS?                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  COLD START (First place of a business type):                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ONBOARDING SPECIALIST (OS) - Human Expert                          │   │
│  │                                                                      │   │
│  │  1. OS reviews first draft taxonomy                                  │   │
│  │  2. OS defines/corrects categories: "This should be 'Service'"      │   │
│  │  3. OS provides example terms: "الخدمة، التعامل، شباب"              │   │
│  │  4. System saves as SEED anchors                                     │   │
│  │                                                                      │   │
│  │  UI: Category editor with "Add as Anchor" button                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  WARM START (Subsequent places):                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  LEARNED FROM APPROVED TAXONOMIES - Automatic                        │   │
│  │                                                                      │   │
│  │  1. OS approves taxonomy for Place A                                 │   │
│  │  2. System extracts approved categories + mentions                   │   │
│  │  3. System adds to LEARNED anchors                                   │   │
│  │  4. Place B automatically benefits from Place A's learnings          │   │
│  │                                                                      │   │
│  │  No manual work needed after first few places                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Complete Learning Lifecycle

```
DAY 0 - System Installation
┌─────────────────────────────────────────────────────────────────────────────┐
│  Empty system. No anchors.                                                  │
│  category_anchors table: []                                                 │
│  anchor_examples table: []                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
DAY 1 - First Coffee Shop (Cold Start)
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. Reviews processed → Clustering runs (pure HDBSCAN, no anchors)          │
│  2. Draft taxonomy created with discovered categories                       │
│  3. OS reviews draft:                                                       │
│     - Sees "Coffee & Location" with 1419 mentions (catch-all)              │
│     - Manually splits into: Service, Quality, Atmosphere, etc.              │
│     - Marks categories as "Anchor" (new UI checkbox)                        │
│  4. On APPROVE:                                                             │
│     - System saves OS-defined categories as SEED anchors                    │
│     - Extracts example terms from approved mentions                         │
│     - Generates embeddings, computes centroids                              │
│                                                                             │
│  Result: 6 aspect anchors + 6 product category anchors created             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
DAY 2 - Second Coffee Shop (Warm Start)
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. Reviews processed → Mentions extracted                                  │
│  2. BEFORE clustering:                                                      │
│     - System queries existing anchors for "coffee_shop"                     │
│     - Finds 12 anchors (6 aspect + 6 product categories)                    │
│  3. Semantic Router classifies mentions:                                    │
│     - "الخدمة ممتازة" → 0.92 match to "Service" → CLASSIFIED               │
│     - "التعامل راقي" → 0.87 match to "Service" → CLASSIFIED                │
│     - "جبار" → 0.65 match (below threshold) → DISCOVERY                    │
│  4. HDBSCAN runs only on unclassified mentions                              │
│  5. OS reviews: Much cleaner taxonomy, less work                            │
│  6. On APPROVE:                                                             │
│     - "جبار" added to "Quality" anchor as learned example                  │
│     - Centroid recomputed                                                   │
│                                                                             │
│  Result: System learned "جبار" = Quality                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
DAY 30 - 50th Coffee Shop (Mature System)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Anchors now have:                                                          │
│  - Service: 500+ learned examples, centroid highly refined                  │
│  - Quality: 800+ learned examples, includes dialect ("جبار", "فخم")        │
│  - Hot Drinks: 1200+ examples, all common drinks known                      │
│                                                                             │
│  New place processing:                                                      │
│  - 95% of mentions auto-classified via anchors                             │
│  - Only 5% go to Discovery (truly unique items)                             │
│  - OS review takes minutes, not hours                                       │
│  - Almost no corrections needed                                             │
│                                                                             │
│  Result: Self-improving system, minimal human intervention                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Anchor Data Model (Future)

```python
class CategoryAnchor:
    id: UUID
    business_type: str              # "coffee_shop", "restaurant"
    category_name: str              # "service", "hot_drinks"
    display_name_en: str            # "Service Quality"
    display_name_ar: str            # "جودة الخدمة"
    is_aspect: bool                 # True for aspects, False for product categories

    # Embedding data
    centroid_embedding: List[float] # Average of all examples (768-dim)

    # Learning metadata
    source: str                     # "os" (onboarding specialist) or "learned"
    created_by: UUID                # OS user who created (if source=os)
    example_count: int              # How many examples
    match_count: int                # How many mentions matched to this anchor

    # Quality metrics
    avg_confidence: float           # Average match confidence
    last_updated: datetime          # When centroid was last recomputed


class AnchorExample:
    id: UUID
    anchor_id: UUID                 # FK to CategoryAnchor
    text: str                       # "الخدمة ممتازة"
    embedding: List[float]          # 768-dim vector

    # Learning metadata
    source: str                     # "os" or "learned"
    source_taxonomy_id: UUID        # Which taxonomy it came from (if learned)
    mention_count: int              # How many times this exact text appeared
    sentiment_avg: float            # Average sentiment when mentioned

    created_at: datetime
```

### UI Changes for OS (Future)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TAXONOMY EDITOR                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Category: Service Quality                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Display Name (EN): [Service Quality        ]                        │   │
│  │  Display Name (AR): [جودة الخدمة            ]                        │   │
│  │                                                                      │   │
│  │  ☑ Save as Anchor for future "coffee_shop" places                   │   │
│  │    └─ This category will be pre-created for new coffee shops         │   │
│  │                                                                      │   │
│  │  Example terms (auto-extracted from mentions):                       │   │
│  │  [الخدمة] [التعامل] [الموظفين] [شباب] [الاستقبال] [+ Add]           │   │
│  │                                                                      │   │
│  │  [Approve Category]  [Reject]  [Move Mentions]                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### API Endpoints (Future)

```python
# Get anchors for a business type
GET /api/anchors?business_type=coffee_shop
Response: {
    "aspects": [...],
    "product_categories": [...],
    "total_examples": 1500,
    "last_updated": "2026-02-04"
}

# OS creates new anchor manually
POST /api/anchors
Body: {
    "business_type": "coffee_shop",
    "category_name": "drive_through",
    "display_name_en": "Drive Through",
    "display_name_ar": "طلب سيارات",
    "is_aspect": False,
    "examples": ["درايف ثرو", "طلب خارجي"]
}

# Learn from approved taxonomy (called on publish)
POST /api/anchors/learn
Body: {
    "taxonomy_id": "uuid",
    "categories_to_learn": ["service", "quality"]  # Optional filter
}

# Get anchor statistics
GET /api/anchors/stats?business_type=coffee_shop
Response: {
    "total_anchors": 12,
    "total_examples": 1500,
    "coverage": {
        "aspects": 0.92,      # 92% of aspects matched to anchors
        "products": 0.85      # 85% of products matched to category anchors
    },
    "top_anchors": [
        {"name": "quality", "match_count": 5000},
        {"name": "service", "match_count": 3500}
    ]
}
```

### Summary: Who Provides What

| Source | What They Provide | When |
|--------|-------------------|------|
| **OS (Onboarding Specialist)** | Initial category definitions, corrections, "Save as Anchor" decisions | Cold start, corrections |
| **Learned (Automatic)** | Examples from approved taxonomies, refined centroids | Every approval |
| **Discovery (HDBSCAN)** | New patterns the system hasn't seen | Always (fallback) |

The system evolves from **OS-dependent** → **Self-sufficient** as more data is approved.
