# Taxonomy Editor UI Plan

**Created**: 2026-02-04
**Status**: Planning
**Location**: Onboarding Portal (`onboarding-portal/`)

---

## Overview

A drag-and-drop editor that allows OS (Operations Specialist) to refine the auto-generated taxonomy before approval.

---

## User Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. CLUSTERING COMPLETES                                        │
│     System creates draft taxonomy (auto)                        │
│     - 40-50 products discovered                                 │
│     - 10-15 categories                                          │
│     - Some AR/EN duplicates                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. OS OPENS EDITOR                                             │
│     Sees all products and categories                            │
│     Can drag, merge, rename, organize                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. OS REFINES                                                  │
│     - Merges "flat white" → "فلات وايت"                         │
│     - Creates hierarchy (Hot Drinks → Latte, Cappuccino)        │
│     - Fixes misplaced products                                  │
│     - Deletes irrelevant items                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. OS APPROVES                                                 │
│     Taxonomy goes live                                          │
│     Future reviews matched against it                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## UI Design

### Main Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TAXONOMY EDITOR - Specialty Bean Roastery              [Save] [Approve All]│
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────────┐  │
│  │  CATEGORIES             │  │  PRODUCTS                               │  │
│  │  ═══════════════════    │  │  ═══════════════════════════════════    │  │
│  │                         │  │                                         │  │
│  │  ▼ Hot Drinks           │  │  Search: [________________] 🔍          │  │
│  │    ├── Espresso Based   │  │                                         │  │
│  │    └── Filter Coffee    │  │  ┌─────────────────────────────────┐   │  │
│  │  ▼ Cold Drinks          │  │  │ ≡ فلات وايت              (52)  │   │  │
│  │  ▼ Desserts             │  │  │   variants: الفلات وايت         │   │  │
│  │  ─────────────────────  │  │  │   category: flat_white          │   │  │
│  │  UNCATEGORIZED          │  │  │   [Edit] [Delete]               │   │  │
│  │  └── (drag here)        │  │  └─────────────────────────────────┘   │  │
│  │                         │  │                                         │  │
│  │  [+ Add Category]       │  │  ┌─────────────────────────────────┐   │  │
│  │                         │  │  │ ≡ flat white              (13)  │   │  │
│  │                         │  │  │   variants: flatwhite           │   │  │
│  │                         │  │  │   category: flat_white_hot      │   │  │
│  │                         │  │  │   [Edit] [Delete] [Merge ▼]     │   │  │
│  │                         │  │  └─────────────────────────────────┘   │  │
│  │                         │  │                                         │  │
│  │                         │  │  ┌─────────────────────────────────┐   │  │
│  │                         │  │  │ ≡ V60                     (30)  │   │  │
│  │                         │  │  │   variants: v60                 │   │  │
│  │                         │  │  │   category: v60_coffee          │   │  │
│  │                         │  │  └─────────────────────────────────┘   │  │
│  │                         │  │                                         │  │
│  └─────────────────────────┘  └─────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Interaction: Merge Products

```
┌─────────────────────────────────────────────────────────────────┐
│  MERGE PRODUCTS                                          [X]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Merging "flat white" INTO "فلات وايت"                         │
│                                                                 │
│  Result:                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Product: فلات وايت                                      │   │
│  │  Mentions: 65 (52 + 13)                                  │   │
│  │  Variants:                                               │   │
│  │    • الفلات وايت                                         │   │
│  │    • flat white  ← NEW                                   │   │
│  │    • flatwhite   ← NEW                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│                              [Cancel]  [Confirm Merge]          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Interaction: Edit Product

```
┌─────────────────────────────────────────────────────────────────┐
│  EDIT PRODUCT                                            [X]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Display Name (AR): [فلات وايت_______________]                 │
│  Display Name (EN): [Flat White______________]                 │
│                                                                 │
│  Category: [Hot Drinks ▼]                                       │
│                                                                 │
│  Variants:                                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  الفلات وايت                                    [X]     │   │
│  │  الفلايت وايت                                   [X]     │   │
│  │  flat white                                     [X]     │   │
│  │  flatwhite                                      [X]     │   │
│  │  [+ Add variant]                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│                              [Cancel]  [Save Changes]           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Interaction: Organize Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│  CATEGORIES                                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Drag categories to organize hierarchy:                         │
│                                                                 │
│  ▼ Hot Drinks ─────────────────────────────── [Edit] [Delete]  │
│    │                                                            │
│    ├── ≡ Espresso Based ──────────────────── [Edit] [Delete]   │
│    │     (drag products here)                                   │
│    │                                                            │
│    └── ≡ Filter Coffee ───────────────────── [Edit] [Delete]   │
│          (drag products here)                                   │
│                                                                 │
│  ▼ Cold Drinks ────────────────────────────── [Edit] [Delete]  │
│    │                                                            │
│    └── ≡ Iced Coffee ─────────────────────── [Edit] [Delete]   │
│                                                                 │
│  ▶ Desserts (collapsed) ──────────────────── [Edit] [Delete]   │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│  UNCATEGORIZED                                                  │
│    • flat_white_(hot_coffee) ← drag to Hot Drinks              │
│    • cleanliness            ← maybe delete?                    │
│                                                                 │
│  [+ Add Category]                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features Breakdown

### P0 - Must Have (MVP)

| Feature | Description | API Endpoint |
|---------|-------------|--------------|
| **View products** | List all products with search/filter | `GET /taxonomy/:id/products` |
| **View categories** | Tree view of categories | `GET /taxonomy/:id/categories` |
| **Merge products** | Combine two products into one | `POST /taxonomy/products/merge` |
| **Move product** | Change product's category | `PATCH /taxonomy/products/:id` |
| **Edit product** | Rename, add variants | `PATCH /taxonomy/products/:id` |
| **Delete product** | Remove unwanted product | `DELETE /taxonomy/products/:id` |
| **Approve all** | Approve entire taxonomy | `POST /taxonomy/:id/approve` |

### P1 - Should Have

| Feature | Description | API Endpoint |
|---------|-------------|--------------|
| **Edit category** | Rename category | `PATCH /taxonomy/categories/:id` |
| **Create category** | Add new category | `POST /taxonomy/categories` |
| **Delete category** | Remove category (move products) | `DELETE /taxonomy/categories/:id` |
| **Set parent** | Create hierarchy | `PATCH /taxonomy/categories/:id` |
| **Drag-drop reorder** | Visual organization | (Frontend only) |

### P2 - Nice to Have

| Feature | Description |
|---------|-------------|
| **Undo/Redo** | Revert recent changes |
| **Bulk operations** | Select multiple, merge/delete |
| **AI suggestions** | "Did you mean to merge these?" |
| **Preview** | See how taxonomy looks to end user |

---

## API Design

### Merge Products

```
POST /api/taxonomy/products/merge

Request:
{
  "source_product_id": "uuid-of-flat-white-english",
  "target_product_id": "uuid-of-فلات-وايت",
  "keep_as_variant": true
}

Response:
{
  "success": true,
  "product": {
    "id": "uuid-of-فلات-وايت",
    "canonical_text": "فلات وايت",
    "variants": ["الفلات وايت", "flat white", "flatwhite"],
    "mention_count": 65
  }
}
```

### Move Product to Category

```
PATCH /api/taxonomy/products/:id

Request:
{
  "category_id": "uuid-of-hot-drinks"
}

Response:
{
  "success": true,
  "product": { ... }
}
```

### Update Product

```
PATCH /api/taxonomy/products/:id

Request:
{
  "display_name": "Flat White / فلات وايت",
  "variants": ["الفلات وايت", "flat white", "flatwhite", "hot flat white"],
  "category_id": "uuid-of-hot-drinks"
}

Response:
{
  "success": true,
  "product": { ... }
}
```

### Set Category Parent

```
PATCH /api/taxonomy/categories/:id

Request:
{
  "parent_id": "uuid-of-hot-drinks",
  "name": "Espresso Based"
}

Response:
{
  "success": true,
  "category": { ... }
}
```

### Create Category

```
POST /api/taxonomy/categories

Request:
{
  "taxonomy_id": "uuid",
  "name": "Hot Drinks",
  "display_name_en": "Hot Drinks",
  "display_name_ar": "مشروبات ساخنة",
  "parent_id": null
}

Response:
{
  "success": true,
  "category": { ... }
}
```

---

## Database Changes

**None required** - existing schema supports all features:

```sql
-- taxonomy_products already has:
- canonical_text
- display_name
- variants (JSONB)
- discovered_category_id
- assigned_category_id  ← Use this for moves

-- taxonomy_categories already has:
- name
- display_name_en
- display_name_ar
- parent_id  ← Use this for hierarchy
- has_products
```

---

## Frontend Components

### New Components Needed

| Component | Description | Library |
|-----------|-------------|---------|
| `TaxonomyEditor` | Main editor page | - |
| `CategoryTree` | Collapsible tree view | react-arborist or custom |
| `ProductCard` | Draggable product item | @dnd-kit |
| `MergeModal` | Merge confirmation dialog | shadcn/dialog |
| `EditProductModal` | Edit product form | shadcn/dialog |
| `EditCategoryModal` | Edit category form | shadcn/dialog |

### Drag-Drop Library

Recommend: **@dnd-kit** (modern, accessible, React 18 compatible)

```bash
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
```

---

## Implementation Order

### Phase 1: Core Editing (4-5 hours)

1. **API endpoints**: merge, move, update, delete
2. **ProductCard component**: display with edit/delete buttons
3. **MergeModal**: select target, confirm merge
4. **EditProductModal**: rename, manage variants

### Phase 2: Categories (3-4 hours)

1. **CategoryTree component**: collapsible tree
2. **Drag product to category**: change assignment
3. **EditCategoryModal**: rename, set parent
4. **Create/delete category**

### Phase 3: Polish (2-3 hours)

1. **Search/filter products**
2. **Visual improvements**
3. **Loading states**
4. **Error handling**

**Total: ~10-12 hours**

---

## File Structure

```
onboarding-portal/src/
├── app/
│   └── taxonomy/
│       └── [id]/
│           └── edit/
│               └── page.tsx         # Editor page
├── components/
│   └── taxonomy-editor/
│       ├── TaxonomyEditor.tsx       # Main container
│       ├── CategoryTree.tsx         # Category sidebar
│       ├── ProductList.tsx          # Products grid
│       ├── ProductCard.tsx          # Single product
│       ├── MergeModal.tsx           # Merge dialog
│       ├── EditProductModal.tsx     # Edit product
│       └── EditCategoryModal.tsx    # Edit category
└── lib/
    └── api/
        └── taxonomy.ts              # API calls
```

---

## Success Criteria

- [ ] OS can merge AR/EN products in <5 seconds
- [ ] OS can organize 50 products in <10 minutes
- [ ] No page refresh needed for any action
- [ ] Clear visual feedback on changes
- [ ] Works on desktop (mobile not required)

---

*Ready for implementation*
