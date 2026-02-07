# Nurliya Onboarding API Reference

Base URL: `http://localhost:8000`

All endpoints require JWT authentication unless noted.

---

## Authentication

### Login
```
POST /api/auth/login
Content-Type: application/json

Body: {"email": "user@example.com", "password": "secret"}

Response: {
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {"id": "uuid", "email": "...", "name": "...", "created_at": "..."}
}
```

Use the access_token in all subsequent requests:
```
-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"
```

---

## Read Endpoints

### Get Taxonomy Detail
```
GET /api/onboarding/taxonomies/{taxonomy_id}

Response: {
  "id": "uuid",
  "place_id": "uuid",
  "place_name": "Nefisa Coffee",
  "place_category": "Coffee shop",
  "status": "draft" | "active",
  "reviews_sampled": 150,
  "entities_discovered": 45,
  "discovered_at": "2026-02-04T...",
  "published_at": null,
  "published_by": null,
  "categories": [TaxonomyCategoryResponse...],
  "products": [TaxonomyProductResponse...]
}
```

**TaxonomyCategoryResponse:**
```json
{
  "id": "uuid",
  "parent_id": "uuid" | null,
  "name": "espresso_drinks",
  "display_name_en": "Espresso Drinks",
  "display_name_ar": "مشروبات اسبرسو",
  "has_products": true,
  "is_approved": false,
  "approved_by": null,
  "approved_at": null,
  "rejection_reason": null,
  "discovered_mention_count": 26,
  "mention_count": 0,
  "avg_sentiment": 0.85
}
```

**TaxonomyProductResponse:**
```json
{
  "id": "uuid",
  "discovered_category_id": "uuid",
  "assigned_category_id": "uuid" | null,
  "canonical_text": "كابتشينو",
  "display_name": "كابتشينو",
  "variants": ["الكابتشينو", "cappuccino"],
  "is_approved": false,
  "approved_by": null,
  "approved_at": null,
  "rejection_reason": null,
  "discovered_mention_count": 52,
  "mention_count": 0,
  "avg_sentiment": null
}
```

IMPORTANT: A product's effective category is `assigned_category_id` if set, otherwise `discovered_category_id`.

---

### Get Grouped Mentions for Category
```
GET /api/onboarding/categories/{category_id}/mentions/grouped

Response: {
  "groups": [MentionGroupResponse...],
  "total_mentions": 120,
  "total_groups": 11,
  "entity_id": "uuid",
  "entity_name": "Cafe Experience"
}
```

**MentionGroupResponse:**
```json
{
  "normalized_text": "اجواء",
  "display_text": "أجواء",
  "mention_ids": ["uuid1", "uuid2", "..."],
  "count": 48,
  "sentiments": {"positive": 40, "negative": 5, "neutral": 3},
  "avg_similarity": 0.92,
  "sample_reviews": ["review excerpt 1...", "review excerpt 2..."]
}
```

---

### Get Grouped Mentions for Product
```
GET /api/onboarding/products/{product_id}/mentions/grouped

Response: same as category grouped mentions
```

---

### Get Grouped Orphan Mentions
```
GET /api/onboarding/taxonomies/{taxonomy_id}/orphan-mentions/grouped

Response: {
  "product_groups": [MentionGroupResponse...],
  "category_groups": [MentionGroupResponse...],
  "total_product_mentions": 28,
  "total_category_mentions": 269,
  "total_product_groups": 19,
  "total_category_groups": 52
}
```

Orphans are mentions not assigned to any active category or product.

---

## Mutation Endpoints

### Update Product (Move / Approve / Reject / Add Variant)
```
PATCH /api/onboarding/products/{product_id}

Body (move):
{"action": "move", "assigned_category_id": "target-category-uuid"}

Body (approve):
{"action": "approve"}

Body (reject):
{"action": "reject", "rejection_reason": "duplicate of X"}

Body (add variant):
{"action": "add_variant", "variant": "الكابتشينو"}

Response: {"success": true, "message": "Product 'كابتشينو' moved"}
```

CRITICAL: Use `assigned_category_id` (not `category_id`) for moves.

---

### Update Category (Rename / Move / Approve / Reject)
```
PATCH /api/onboarding/categories/{category_id}

Body (rename):
{"action": "rename", "display_name_en": "Desserts", "display_name_ar": "حلويات"}

Body (move - change parent):
{"action": "move", "parent_id": "new-parent-uuid"}

Body (move - make standalone):
{"action": "move", "parent_id": null}

Body (approve):
{"action": "approve"}

Body (reject):
{"action": "reject", "rejection_reason": "empty category, products moved out"}

Response: {"success": true, "message": "Category 'desserts' renamed"}
```

---

### Create Category
```
POST /api/onboarding/categories

Body: {
  "taxonomy_id": "uuid",
  "parent_id": "uuid" | null,
  "name": "espresso_drinks",
  "display_name_en": "Espresso Drinks",
  "display_name_ar": "مشروبات اسبرسو",
  "has_products": true
}

Response: TaxonomyCategoryResponse (see above)
```

The `name` field is auto-normalized to lowercase. Use snake_case.
Category is auto-approved when manually created.

---

### Create Product
```
POST /api/onboarding/products

Body: {
  "taxonomy_id": "uuid",
  "assigned_category_id": "uuid",
  "display_name": "كيك برتقال",
  "variants": ["كيكة البرتقال", "orange cake"]
}

Response: TaxonomyProductResponse (see above)
```

Product is auto-approved when manually created.

---

### Merge Products
```
POST /api/onboarding/products/merge

Body: {
  "source_id": "uuid-to-absorb-and-delete",
  "target_id": "uuid-that-survives"
}

Response: {
  "success": true,
  "message": "Merged 'التيراميسو' into 'تراميسو'",
  "target_id": "uuid",
  "merged_mention_count": 5,
  "merged_variant_count": 1
}
```

Source product is deleted. Its variants and mentions are transferred to target.

---

### Merge Categories
```
POST /api/onboarding/categories/merge

Body: {
  "source_id": "uuid-to-absorb-and-delete",
  "target_id": "uuid-that-survives"
}

Response: {
  "success": true,
  "message": "Merged 'Food & Coffee' into 'Cakes & Coffee' (0 products, 0 mentions)",
  "target_id": "uuid",
  "merged_mention_count": 0,
  "merged_variant_count": 0
}
```

Source category is deleted. Its products, mentions, and child categories are transferred to target.

---

### Bulk Move Mentions
```
POST /api/onboarding/mentions/move

Body: {
  "mention_ids": ["uuid1", "uuid2", "uuid3"],
  "target_type": "category" | "product",
  "target_id": "uuid"
}

Response: {
  "success": true,
  "moved_count": 23,
  "message": "Moved 23 mentions to Espresso Drinks (learned 14 new patterns)"
}
```

This endpoint also triggers anchor learning from corrections — moved mentions create new classification patterns for future clustering.

For draft taxonomies: updates `discovered_product_id` / `discovered_category_id`.
For active taxonomies: updates `resolved_product_id` / `resolved_category_id`.

---

## Curl Template

All mutation calls should follow this pattern:

```bash
TOKEN=$(cat /tmp/login.json | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X {METHOD} "http://localhost:8000{PATH}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{JSON_BODY}'
```

Always parse responses with python3 for correct Arabic text handling:
```bash
curl -s ... | python3 -c "import sys,json; data=json.load(sys.stdin); print(json.dumps(data, ensure_ascii=False, indent=2))"
```

Or save to file and parse separately:
```bash
curl -s ... > /tmp/result.json
python3 << 'PYEOF'
import json
with open('/tmp/result.json') as f:
    data = json.load(f)
# process data...
PYEOF
```
