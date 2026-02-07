---
name: review-taxonomy
description: Review and reorganize a Nurliya taxonomy — analyzes categories, identifies misplaced mentions, reorganizes structure, handles orphans. Interactive with user confirmation before mutations.
argument-hint: [taxonomy-id]
allowed-tools: Bash, Read, Grep, Glob
---

# Taxonomy Review Workflow

You are reviewing a Nurliya taxonomy for a Saudi business. The taxonomy was auto-generated from Google Maps reviews using LLM extraction and HDBSCAN clustering. Your job is to clean it up: fix structure, move misplaced mentions, handle orphans, and leave it ready for human approval.

Read the API reference at `.claude/skills/review-taxonomy/api-reference.md` before starting.

The taxonomy ID is: `$ARGUMENTS`

---

## Step 1: Authenticate & Load

### 1a. Auth
Ask the user for their email and password. Authenticate:

```
POST http://localhost:8000/api/auth/login
Body: {"email": "...", "password": "..."}
```

Save the response to `/tmp/login.json`. Extract the `access_token` — use it in ALL subsequent requests as:
```
-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"
```

### 1b. Load Taxonomy
```
GET http://localhost:8000/api/onboarding/taxonomies/$ARGUMENTS
```

Save response to `/tmp/taxonomy_detail.json`.

### 1c. Display Structure
Parse the taxonomy and display a formatted tree. Use python3 for all JSON parsing (handles Arabic text correctly). Show:

```
=== TAXONOMY: {place_name} ({place_category}) ===
Status: {status}

[parent]  قهوة (Coffee)                    0 mentions, 0 products
  [sub]   مشروبات اسبرسو (Espresso)       26 mentions, 2 products
            - كابتشينو [3 variants]
            - فلات وايت [2 variants]
  [sub]   قهوة مُحضّرة (Brewed Coffee)    119 mentions, 8 products
[standalone] حلويات (Desserts)              69 mentions, 9 products
[aspect]  تجربة المقهى (Cafe Experience)   311 mentions, 0 products

REJECTED: فلات وايت (Flat White), ...
```

Rules:
- Arabic name (display_name_ar) FIRST, English in parentheses
- Show hierarchy with indentation
- Categories: type tag [parent/sub/standalone/aspect], mention count, product count
- Products: display_name, variant count
- Separate rejected categories at the bottom

---

## Step 2: Analyze Structure

Review the taxonomy tree and identify ALL issues. Check for:

1. **Empty categories** — 0 mentions AND 0 products. Candidate for rejection.
2. **Duplicate categories** — Same or very similar Arabic/English names.
3. **Misplaced hierarchy** — Categories under the wrong parent (e.g. desserts under coffee should be standalone).
4. **Wrong naming** — Clustering artifacts, unclear names, missing Arabic names.
5. **Missing categories** — Expected categories for the business type that are absent.
6. **Over-fragmented** — Multiple categories that should be one (e.g. "coffee_quality" + "coffee_taste").
7. **Products in wrong category** — Product name clearly belongs elsewhere.

### Business Type Heuristics

Use the taxonomy's `place_category` to set expectations:

- **Cafe/Coffee shop**: Espresso Drinks, Brewed Coffee, Cold Drinks, Desserts/Pastries, Service & Staff, Ambiance
- **Restaurant**: Food Quality, Menu Variety, Service, Ambiance, Cleanliness, Value/Pricing
- **Bakery**: Bread, Pastries, Cakes, Service, Freshness, Variety, Pricing

Present ALL identified issues in a numbered list. Ask:
> "I found N issues. Shall I proceed with fixes, or do you want to adjust?"

**WAIT for user confirmation before proceeding.**

---

## Step 3: Review Grouped Mentions

For each non-empty category (highest mention count first):

```
GET http://localhost:8000/api/onboarding/categories/{category_id}/mentions/grouped
```

Display each group:
```
  تجربة المقهى (311 mentions, 48 groups):
    أجواء                        x 55  (+45 -6 ~4)
    القهوة                       x 52  (+45 -4 ~3)
    الموظفين                     x 37  (+33 -4 ~0)
    ...
```

For each group, classify as:
- **BELONGS** — Correctly in this category
- **MISPLACED → [target]** — Should be in a different existing category
- **NEW CATEGORY** — Represents a distinct topic not covered by any existing category (3+ mentions)
- **NEW PRODUCT → [category]** — Is a specific product/item that should be tracked as a product
- **AMBIGUOUS** — Could go either way (ask user)

Process categories in batches of 3-5. After each batch, present findings.

After all categories reviewed, present the full misplacement plan:
```
MISPLACEMENT PLAN:
  From حلويات → مشروبات اسبرسو: الاسبرسو (10), كابتشينو (4), لاتيه (3)
  From حلويات → قهوة مُحضّرة: بلاك كوفي (2), ايس دريب (2)
  NEW CATEGORY needed: مشروبات باردة (Cold Drinks) for: ايس تي (3), ماتشا (2)
  NEW PRODUCT in حلويات: كيك برتقال for: كيك برتقال (4)
```

**WAIT for user confirmation before proceeding.**

---

## Step 4: Execute Reorganization

Execute fixes in this exact dependency order:

### 4a. Create new categories
```
POST http://localhost:8000/api/onboarding/categories
Body: {"taxonomy_id": "...", "parent_id": "..." or null, "name": "snake_case_name", "display_name_en": "...", "display_name_ar": "...", "has_products": true/false}
```
Report: "Created: {display_name_ar} ({display_name_en}) — ID: {id}"

### 4b. Rename categories
```
PATCH http://localhost:8000/api/onboarding/categories/{id}
Body: {"action": "rename", "display_name_en": "...", "display_name_ar": "..."}
```

### 4c. Move categories (fix hierarchy)
```
PATCH http://localhost:8000/api/onboarding/categories/{id}
Body: {"action": "move", "parent_id": "..." or null}
```
Use `null` to make a category top-level (standalone).

### 4d. Merge duplicate categories
```
POST http://localhost:8000/api/onboarding/categories/merge
Body: {"source_id": "...", "target_id": "..."}
```
Target (survivor) = the one with Arabic name + more mentions.

### 4e. Move misplaced products
```
PATCH http://localhost:8000/api/onboarding/products/{id}
Body: {"action": "move", "assigned_category_id": "..."}
```
IMPORTANT: The field is `assigned_category_id`, NOT `category_id`.

### 4f. Create new products (for orphans/mentions that need product tracking)
```
POST http://localhost:8000/api/onboarding/products
Body: {"taxonomy_id": "...", "assigned_category_id": "...", "display_name": "...", "variants": [...]}
```

### 4g. Merge duplicate products
```
POST http://localhost:8000/api/onboarding/products/merge
Body: {"source_id": "...", "target_id": "..."}
```

### 4h. Reject empty/invalid categories (LAST — after products moved out)
```
PATCH http://localhost:8000/api/onboarding/categories/{id}
Body: {"action": "reject", "rejection_reason": "..."}
```

Report each action. If any call fails, show the error and continue with the next.

---

## Step 5: Bulk Move Misplaced Mentions

For each target identified in Step 3:

1. If target is a **new category** — it was already created in Step 4a
2. If target is a **new product** — it was already created in Step 4f
3. Collect all mention_ids for that target
4. Execute:
```
POST http://localhost:8000/api/onboarding/mentions/move
Body: {"mention_ids": [...], "target_type": "category" or "product", "target_id": "..."}
```

Process moves grouped by target (one API call per target category/product).
Report: "Moved N mentions to {target_name}"

---

## Step 6: Handle Orphans

```
GET http://localhost:8000/api/onboarding/taxonomies/$ARGUMENTS/orphan-mentions/grouped
```

If total orphans = 0, report "No orphans" and skip to Step 7.

Otherwise, for each orphan group (both `product_groups` and `category_groups`):

Classify into one of three outcomes:
1. **MOVE** — Fits an existing category → note target category
2. **NEW CATEGORY** — Distinct topic with 3+ mentions, not covered by existing categories → will create new category first
3. **NEW PRODUCT** — Specific product/item that belongs in an existing category but isn't tracked yet → will create product first, then move mentions to it

For orphans with 1-2 mentions that don't clearly fit, suggest the closest matching category or ask the user.

Present the full orphan classification plan:
```
ORPHAN PLAN:
  MOVE to تجربة المقهى: الموظفين (37), المكان (28), الخدمة (25), ...
  MOVE to قهوة مُحضّرة: قهوة (60), بن (2), ...
  NEW CATEGORY مشروبات باردة: ايس تي (3), شاي مثلج (2)
  NEW PRODUCT كيك برتقال in حلويات: كيك برتقال (4)
```

**WAIT for user confirmation.**

Execute in order:
1. Create any new categories needed
2. Create any new products needed
3. Bulk move all orphan mentions to their targets

Report total resolved per type.

---

## Step 7: Final Verification

1. Re-fetch taxonomy:
```
GET http://localhost:8000/api/onboarding/taxonomies/$ARGUMENTS
```

2. Re-check orphans:
```
GET http://localhost:8000/api/onboarding/taxonomies/$ARGUMENTS/orphan-mentions/grouped
```

3. Re-fetch grouped mentions for each active category to verify clean distribution.

4. Display final summary:

```
=== FINAL TAXONOMY SUMMARY ===

| Category                  | Mentions | Groups | Products |
|---------------------------|----------|--------|----------|
| تجربة المقهى (Cafe Exp.)  |      311 |     48 |        0 |
| قهوة مُحضّرة (Brewed)     |      119 |     35 |        8 |
| حلويات (Desserts)         |       69 |     27 |        9 |
| مشروبات اسبرسو (Espresso) |       26 |      9 |        2 |

Orphans remaining: 0
Total mentions: 525
Total mutations performed: 42
```

5. If orphans remain > 0, offer to do another pass.

6. Tell the user:
> "Taxonomy review complete. Open the onboarding portal to visually verify and approve categories."

---

## Rules

1. **NEVER mutate without presenting the plan and getting user confirmation first.**
2. **Arabic first** — `display_name_ar` is the PRIMARY display. Always show it first, English in parentheses.
3. **curl format** — All API calls: `curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"`
4. **python3 for JSON** — Always parse JSON with python3, not jq. Handles Arabic text and Unicode correctly.
5. **Error handling** — On API error, show the full error response and ask the user how to proceed. Don't silently skip.
6. **Merge survivors** — For merges, the target (survivor) should be the item with: Arabic name preferred, more mentions preferred, cleaner display name.
7. **Category names** — The `name` field in create requests must be lowercase_with_underscores.
8. **Bilingual** — Always provide both `display_name_en` and `display_name_ar` when creating categories.
9. **Top-level** — Use `"parent_id": null` in move requests to make a category standalone.
10. **Product moves** — Use `assigned_category_id` field (NOT `category_id`) when moving products.
11. **Mutation count** — Keep a running count of all mutations and report at the end.
12. **Batch processing** — Process categories in batches of 3-5 when reviewing mentions to keep output manageable.
