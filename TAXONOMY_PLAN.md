# Dynamic Taxonomy System - Implementation Plan

## Overview

Replace the current fixed 12-topic system with a dynamic, place-specific taxonomy that:
1. **Discovers** categories/products from review mentions via embedding + clustering
2. **Resolves** entities (handles "Spanish latte" vs "spanish latté")
3. **Requires internal team approval** before going live

---

## What Changes for Users

### Current System (Before)
```
Client submits scrape → Reviews analyzed with 12 fixed topics → Generic insights
                        (service, food, drinks, price, etc.)

Problem: "Spanish latte" and "V60" both become "drinks"
         Can't answer: "How is our Spanish latte performing vs Cappuccino?"
```

### New System (After)
```
Client submits scrape → Reviews analyzed → Mentions extracted
                                                   ↓
                        ┌──────────────────────────┴──────────────────────────┐
                        ↓                                                      ↓
              System discovers:                                    Onboarding Specialist
              • "Spanish latte" (product)                          reviews & approves
              • "V60" (product)                                    in Onboarding Portal
              • "slow service" (aspect)                                    ↓
                        ↓                                          Published Taxonomy
                        └──────────────────────────┬──────────────────────────┘
                                                   ↓
                        Client sees category/product-level insights:
                        • "Spanish latte: 92% positive, 89 mentions"
                        • "Service Speed: 45% negative, trending down"
```

### User Impact by Role

| Role | Before | After |
|------|--------|-------|
| **Client** | Generic topic insights | Specific product/category insights for THEIR business |
| **Onboarding Specialist** | No involvement | Reviews and approves discovered taxonomy before client sees it |
| **System** | Fixed 12 topics | Dynamic, place-specific taxonomy |

---

## The Onboarding Portal (New)

### What It Is
A new internal portal where you (onboarding specialist) review system-discovered taxonomies before they go live for clients.

### When You Use It
1. Client submits a scrape job (e.g., "cafes in Riyadh")
2. System scrapes 1,247 reviews from 15 places
3. System extracts mentions and clusters them into categories/products
4. **You get notified**: "Café Riyadh - taxonomy ready for review"
5. You open Onboarding Portal and review/approve/reject
6. Once published, client sees product-level insights

### Your Workflow

```
Step 1: NOTIFICATION
────────────────────
You receive: "Café Riyadh - 1,247 reviews analyzed, taxonomy ready for review"


Step 2: OPEN ONBOARDING PORTAL
──────────────────────────────
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  ONBOARDING PORTAL                                                      [Hatim ▾]  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  PLACES PENDING REVIEW                                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ ⚠️  Café Riyadh                                                  [Review →] │   │
│  │     Reviews: 1,247  │  Categories: 7  │  Products: 45                       │   │
│  │     Discovered: Jan 15, 2026                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ ⚠️  Coffee House Jeddah                                          [Review →] │   │
│  │     Reviews: 892  │  Categories: 5  │  Products: 32                         │   │
│  │     Discovered: Jan 14, 2026                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  RECENTLY PUBLISHED                                                                 │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ ✓  Restaurant Al-Khobar                                            [View]   │   │
│  │     Published: Jan 10, 2026 by Ahmed                                        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


Step 3: REVIEW TAXONOMY
───────────────────────
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TAXONOMY EDITOR - Café Riyadh                                          [Hatim ▾]  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  Status: ⚠️ Pending Review    Reviews: 1,247    Discovered: Jan 15, 2026           │
│                                                                                     │
│  ┌─────────────────────────────────┬───────────────────────────────────────────┐   │
│  │  CATEGORIES                     │  PRODUCTS                                 │   │
│  │                                 │                                           │   │
│  │  ▼ ☑ Beverages           [⚙️]  │  Viewing: Hot Coffee (23 products)        │   │
│  │    │ has_products: ✓           │                                           │   │
│  │    │                           │  ┌─────────────────────────────────────┐  │   │
│  │    ├── ☑ Hot Coffee      [⚙️]  │  │ ☑ Spanish latte              (89)  │  │   │
│  │    │     23 products           │  │   Category: Hot Coffee              │  │   │
│  │    │                           │  │   Variants: spanish latté [+]       │  │   │
│  │    ├── ☑ Cold Coffee     [⚙️]  │  ├─────────────────────────────────────┤  │   │
│  │    │     12 products           │  │ ☑ V60                        (67)  │  │   │
│  │    │                           │  │   Category: Hot Coffee              │  │   │
│  │    └── ☐ Tea             [⚙️]  │  ├─────────────────────────────────────┤  │   │
│  │          ⚠️ pending            │  │ ☐ flat white                 (12)  │  │   │
│  │                                 │  │   ⚠️ Pending review                │  │   │
│  │  ▶ ☑ Food                [⚙️]  │  │   System suggested: Hot Coffee      │  │   │
│  │      has_products: ✓           │  │   [Approve] [Reject] [Move to ▾]   │  │   │
│  │                                 │  └─────────────────────────────────────┘  │   │
│  │  ▶ ☑ Service             [⚙️]  │                                           │   │
│  │      has_products: ✗           │  STANDALONE PRODUCTS (3)                  │   │
│  │      ├── Staff                 │  ┌─────────────────────────────────────┐  │   │
│  │      └── Speed                 │  │ ☑ Gift card                  (12)  │  │   │
│  │                                 │  │   Category: None (standalone)       │  │   │
│  │  [+ Add Category]              │  └─────────────────────────────────────┘  │   │
│  │                                 │                                           │   │
│  │                                 │  [+ Add Product Manually]                 │   │
│  └─────────────────────────────────┴───────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  Progress: 42/45 products approved    4/7 categories approved               │   │
│  │                                                                             │   │
│  │                                         [Save Draft]  [Publish Taxonomy ✓] │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


Step 4: YOUR ACTIONS
────────────────────
For each CATEGORY you can:
  ✓ Approve     - Accept as-is (optionally rename)
  ✗ Reject      - Remove (with reason)
  ↔ Move        - Change parent (promote sub to main, or demote)
  ⚙️ Edit       - Rename, toggle has_products

For each PRODUCT you can:
  ✓ Approve     - Accept with current category
  ✗ Reject      - Remove (noise, not relevant)
  ↔ Move        - Assign to different category
  + Variants    - Add alternative spellings ("spanish latté")

Manual additions:
  + Add Category  - If system missed something
  + Add Product   - If system missed something


Step 5: PUBLISH
───────────────
Once you've reviewed everything:
  • Click "Publish Taxonomy"
  • Taxonomy becomes active for this client
  • Client portal shows category/product insights
  • Future reviews automatically use this taxonomy
```

### What Happens After You Publish

```
CLIENT PORTAL (what client sees after you publish)
──────────────────────────────────────────────────

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  CAFÉ RIYADH - Sentiment Analysis                                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  CATEGORY BREAKDOWN                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Beverages        ████████████████████░░░░  82% positive   (456 mentions)    │   │
│  │   Hot Coffee     █████████████████████░░░  89% positive   (234 mentions)    │   │
│  │   Cold Coffee    ████████████████░░░░░░░░  72% positive   (156 mentions)    │   │
│  │   Tea            ██████████████████░░░░░░  78% positive   (66 mentions)     │   │
│  │                                                                             │   │
│  │ Service          ████████████░░░░░░░░░░░░  54% positive   (312 mentions)    │   │
│  │   Staff          ████████████████░░░░░░░░  71% positive   (189 mentions)    │   │
│  │   Speed          ██████░░░░░░░░░░░░░░░░░░  32% positive   (123 mentions)  ⚠️│   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  TOP PRODUCTS                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 1. Spanish latte    92% positive   89 mentions   ↑ trending                 │   │
│  │ 2. V60              87% positive   67 mentions   → stable                   │   │
│  │ 3. Cappuccino       84% positive   54 mentions   → stable                   │   │
│  │ 4. Croissant        78% positive   45 mentions   ↓ declining                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

Now the client can answer:
• "How is our Spanish latte performing?" → 92% positive, 89 mentions
• "What's hurting our Service category?" → Speed is 32% positive, needs attention
• "Which products are trending up/down?" → Spanish latte up, Croissant down
```

---

## Decisions

| Decision | Choice |
|----------|--------|
| **Portal users** | Internal team only (simplifies auth) |
| **Scope** | Full system (12 weeks) |
| **Arabic support** | Saudi dialects priority (Najdi, Hijazi) |

## Architecture

```
Phase 1 (Real-time)     Phase 2 (Batch)          Phase 3 (Manual)
───────────────────     ────────────────         ─────────────────
Review                  Triggered after scrape   Onboarding Portal
   │                         │                         │
   ▼                         ▼                         ▼
Extract mentions ──▶ HDBSCAN clustering ──▶ Human approval ──▶ Active Taxonomy
   │                         │
   ▼                         ▼
Embed + resolve         LLM labels clusters
   │
   ▼
Qdrant (vectors)
```

---

## Files to Modify

| File | Change |
|------|--------|
| `pipline/database.py` | Add 5 new taxonomy tables |
| `pipline/llm_client.py` | Add `extract_mentions()` function |
| `pipline/worker.py` | Add mention extraction (dual-write) |
| `pipline/api.py` | Add taxonomy/onboarding endpoints |
| `docker-compose.yml` | Add Qdrant service |
| `pipline/requirements.txt` | Add qdrant-client, hdbscan, sentence-transformers |

## New Files

| File | Purpose |
|------|---------|
| `pipline/embedding_client.py` | Arabic-aware embedding generation |
| `pipline/vector_store.py` | Qdrant client wrapper |
| `pipline/clustering_job.py` | HDBSCAN clustering + LLM labeling |
| `client-portal/src/app/onboarding/*` | Approval portal UI |

---

## Key Technical Decisions

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Embedding model** | MiniLM → CAMeL-BERT | Start small (~80MB), upgrade if Arabic quality insufficient (~400MB) |
| **Vector DB** | Qdrant | Better clustering, scales well |
| **Clustering** | HDBSCAN | Handles variable density, finds outliers |
| **Cold start** | Seed 12 defaults | Graceful degradation for new places |
| **Threshold** | 0.85 cosine | Balance precision/recall for entity resolution |

---

## Implementation Phases

### Phase 1A: Infrastructure (Weeks 1-2)
- Add Qdrant to docker-compose.yml
- Add 5 taxonomy tables to database.py
- Create embedding_client.py with Arabic normalization
- Create vector_store.py with Qdrant wrapper + fallback

### Phase 1B: Worker Integration (Weeks 3-4)
- Add `extract_mentions()` to llm_client.py
- Modify worker.py for dual-write (keep old topics + new mentions)
- Entity resolution via Qdrant similarity
- **GATE**: Test Arabic embedding quality before Phase 2

### Phase 2: Discovery (Weeks 5-6)
- Create clustering_job.py (HDBSCAN + LLM labeling)
- Trigger after scrape completes or 50+ new mentions
- Build hierarchy (Main → Sub → Products)
- Save as draft taxonomy

### Phase 3: Onboarding Portal (Weeks 7-9)
- API endpoints for approve/reject/move/link/publish
- Portal UI: pending list, tree editor, bulk operations
- Audit logging for all decisions

### Phase 4: Integration (Weeks 10-11)
- Match mentions to approved taxonomy
- Add resolved_products/categories to ReviewAnalysis
- Analytics endpoints (by category, by product, timeline)
- Client portal category/product breakdown

### Phase 5: Polish (Week 12)
- Migration script for existing reviews
- New discovery alerts (dashboard badge + email)
- Performance tuning
- Documentation

---

## Database Schema

```sql
-- Per-place taxonomy container
CREATE TABLE place_taxonomies (
    id UUID PRIMARY KEY,
    place_id UUID REFERENCES places(id),
    status VARCHAR(20) DEFAULT 'draft',  -- draft/review/active
    discovered_at TIMESTAMP,
    reviews_sampled INT,
    entities_discovered INT,
    published_at TIMESTAMP,
    published_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Hierarchical categories
CREATE TABLE taxonomy_categories (
    id UUID PRIMARY KEY,
    taxonomy_id UUID REFERENCES place_taxonomies(id),
    parent_id UUID REFERENCES taxonomy_categories(id),  -- NULL = main category
    name VARCHAR(100),
    display_name_en VARCHAR(100),
    display_name_ar VARCHAR(100),
    has_products BOOLEAN DEFAULT false,
    -- Approval workflow
    is_approved BOOLEAN DEFAULT false,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    -- Analytics
    discovered_mention_count INT,  -- frozen at discovery (audit)
    mention_count INT DEFAULT 0,   -- live, updated continuously
    avg_sentiment FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Products (leaf nodes or standalone)
CREATE TABLE taxonomy_products (
    id UUID PRIMARY KEY,
    taxonomy_id UUID REFERENCES place_taxonomies(id),
    discovered_category_id UUID REFERENCES taxonomy_categories(id),  -- system suggestion
    assigned_category_id UUID REFERENCES taxonomy_categories(id),    -- human decision (NULL = standalone)
    canonical_text VARCHAR(200),
    display_name VARCHAR(200),
    variants JSONB DEFAULT '[]',
    vector_id UUID,
    -- Approval workflow
    is_approved BOOLEAN DEFAULT false,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    -- Analytics
    discovered_mention_count INT,
    mention_count INT DEFAULT 0,
    avg_sentiment FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Raw mentions (from reviews)
CREATE TABLE raw_mentions (
    id UUID PRIMARY KEY,
    review_id UUID REFERENCES reviews(id),
    place_id UUID REFERENCES places(id),
    mention_text TEXT,
    mention_type VARCHAR(20),  -- 'product' | 'aspect'
    sentiment VARCHAR(20),
    qdrant_point_id VARCHAR(100),
    resolved_product_id UUID REFERENCES taxonomy_products(id),
    resolved_category_id UUID REFERENCES taxonomy_categories(id),
    created_at TIMESTAMP DEFAULT NOW(),
    -- NOTE: CHECK constraint below is optional - can be enforced in application logic instead.
    -- If using SQLAlchemy, add via CheckConstraint in Phase 1B when table is in active use.
    CHECK (
        (mention_type = 'product' AND resolved_product_id IS NOT NULL AND resolved_category_id IS NULL) OR
        (mention_type = 'aspect' AND resolved_category_id IS NOT NULL AND resolved_product_id IS NULL) OR
        (resolved_product_id IS NULL AND resolved_category_id IS NULL)
    )
);

-- Audit log
CREATE TABLE taxonomy_audit_log (
    id UUID PRIMARY KEY,
    taxonomy_id UUID REFERENCES place_taxonomies(id),
    user_id UUID REFERENCES users(id),
    action VARCHAR(50),
    entity_type VARCHAR(20),
    entity_id UUID,
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Qdrant Payload Schema

```javascript
{
  "id": "uuid",
  "vector": [0.23, -0.12, ...],  // 384-dim MiniLM or 768-dim CAMeL
  "payload": {
    "text": "Spanish latte",
    "place_id": "abc123",
    "mention_type": "product",
    "is_canonical": true,
    "canonical_id": "uuid",
    "sentiment_sum": 71.2,
    "mention_count": 89
  }
}
```

---

## Operational Flows

### Initial Setup (New Client)
```
1. Client submits scrape job
2. System scrapes reviews
3. System extracts mentions + clusters them
4. Status: "Pending Review"
5. You review in Onboarding Portal
6. You publish → Client sees insights
```

### Re-discovery (Existing Client Gets New Reviews)
```
1. Client submits another scrape (or scheduled re-scrape)
2. System finds new products not in current taxonomy
3. After 50+ new unresolved mentions:
   → You get notified: "Café Riyadh: 15 new products discovered"
4. You open Onboarding Portal
5. You see: "New Discoveries" section with pending items
6. You approve/reject → Added to existing taxonomy
7. Client sees updated insights
```

### What You See for Re-discovery
```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  TAXONOMY EDITOR - Café Riyadh                                          [Hatim ▾]  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  Status: ✓ Active (Published Jan 15)    ⚠️ 15 new discoveries pending              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  🆕 NEW DISCOVERIES (15 items)                              [Review All →]  │   │
│  │                                                                             │   │
│  │  Products:                                                                  │   │
│  │  • "Matcha latte" (34 mentions) - suggested: Cold Coffee                   │   │
│  │  • "Pistachio croissant" (23 mentions) - suggested: Pastries               │   │
│  │  • "Oat milk" (18 mentions) - suggested: None (standalone?)                │   │
│  │                                                                             │   │
│  │  Categories:                                                                │   │
│  │  • "Delivery" (45 mentions) - suggested as new main category               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  EXISTING TAXONOMY (unchanged until you approve new items)                         │
│  ...                                                                               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Fallback (Qdrant down)
- Queue mention for retry (embedding_retry queue)
- Continue analyze_review() normally
- Background job processes retry queue when Qdrant recovers

### Alerts You'll Receive
| Event | Notification |
|-------|--------------|
| New taxonomy ready | "Café Riyadh - taxonomy ready for review" |
| New discoveries | "Café Riyadh - 15 new products discovered" |
| Taxonomy published | Confirmation + link to client view |

---

## Verification

1. **Unit tests**: Arabic normalization, entity resolution, clustering
2. **Integration tests**: Review → Mention → Cluster → Topic flow
3. **Arabic quality**: Verify "قهوة اسبانش" clusters with "Spanish latte"
4. **Load testing**: 100K+ vectors, concurrent clustering
5. **E2E**: Full scrape → discover → approve → analyze cycle
