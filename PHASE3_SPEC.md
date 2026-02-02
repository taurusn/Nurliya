# Phase 3: Onboarding Portal - Implementation Specification

## Overview

**Goal**: Build internal portal for onboarding specialists to review and approve taxonomies before clients see product-level insights.

**Domain**: `onboarding.nurliya.com` (port 3001)

**Status**: ✅ DEPLOYED (2026-02-02) - Live at https://onboarding.nurliya.com

---

## 1. Backend API Specification

### File: `pipline/api.py`

#### 1.1 New Imports Required

```python
from database import (
    Place, Review, ReviewAnalysis, Job, ScrapeJob, ActivityLog, User, AnomalyInsight,
    # Add these:
    PlaceTaxonomy, TaxonomyCategory, TaxonomyProduct, RawMention, TaxonomyAuditLog,
    get_session, create_tables
)
from datetime import datetime
```

#### 1.2 Pydantic Models

```python
# =============================================================================
# ONBOARDING API MODELS
# =============================================================================

# --- Request Models ---

class CategoryUpdateRequest(BaseModel):
    """Request to update a taxonomy category."""
    action: str = Field(..., description="Action: approve, reject, move, rename")
    rejection_reason: Optional[str] = Field(None, description="Required if action=reject")
    parent_id: Optional[UUID] = Field(None, description="New parent ID if action=move")
    display_name_en: Optional[str] = Field(None, description="New English name if action=rename")
    display_name_ar: Optional[str] = Field(None, description="New Arabic name if action=rename")


class ProductUpdateRequest(BaseModel):
    """Request to update a taxonomy product."""
    action: str = Field(..., description="Action: approve, reject, move, add_variant")
    rejection_reason: Optional[str] = Field(None, description="Required if action=reject")
    assigned_category_id: Optional[UUID] = Field(None, description="Category ID if action=move (None=standalone)")
    variant: Optional[str] = Field(None, description="Variant text if action=add_variant")


class CategoryCreateRequest(BaseModel):
    """Request to create a new category manually."""
    taxonomy_id: UUID
    parent_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=100)
    display_name_en: str = Field(..., min_length=1, max_length=100)
    display_name_ar: Optional[str] = Field(None, max_length=100)
    has_products: bool = True


class ProductCreateRequest(BaseModel):
    """Request to create a new product manually."""
    taxonomy_id: UUID
    assigned_category_id: Optional[UUID] = None
    display_name: str = Field(..., min_length=1, max_length=200)
    variants: List[str] = []


# --- Response Models ---

class PendingTaxonomyResponse(BaseModel):
    """Summary of a taxonomy pending review."""
    id: str
    place_id: str
    place_name: str
    place_category: Optional[str]
    status: str  # draft, review, active
    reviews_sampled: int
    categories_count: int
    products_count: int
    approved_categories: int
    approved_products: int
    discovered_at: Optional[str]


class PendingListResponse(BaseModel):
    """List of pending taxonomies."""
    taxonomies: List[PendingTaxonomyResponse]
    total: int


class TaxonomyCategoryResponse(BaseModel):
    """Category in taxonomy detail response."""
    id: str
    parent_id: Optional[str]
    name: str
    display_name_en: Optional[str]
    display_name_ar: Optional[str]
    has_products: bool
    is_approved: bool
    approved_by: Optional[str]
    approved_at: Optional[str]
    rejection_reason: Optional[str]
    discovered_mention_count: int
    mention_count: int
    avg_sentiment: Optional[float]


class TaxonomyProductResponse(BaseModel):
    """Product in taxonomy detail response."""
    id: str
    discovered_category_id: Optional[str]
    assigned_category_id: Optional[str]
    canonical_text: str
    display_name: Optional[str]
    variants: List[str]
    is_approved: bool
    approved_by: Optional[str]
    approved_at: Optional[str]
    rejection_reason: Optional[str]
    discovered_mention_count: int
    mention_count: int
    avg_sentiment: Optional[float]


class TaxonomyDetailResponse(BaseModel):
    """Full taxonomy detail for editor."""
    id: str
    place_id: str
    place_name: str
    place_category: Optional[str]
    status: str
    reviews_sampled: int
    entities_discovered: int
    discovered_at: Optional[str]
    published_at: Optional[str]
    published_by: Optional[str]
    categories: List[TaxonomyCategoryResponse]
    products: List[TaxonomyProductResponse]


class ActionResponse(BaseModel):
    """Generic success response."""
    success: bool
    message: str
```

#### 1.3 Audit Logging Helper

```python
def log_taxonomy_action(
    session,
    taxonomy_id: UUID,
    user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    old_value: dict = None,
    new_value: dict = None
):
    """
    Log an action to TaxonomyAuditLog.

    Actions: approve, reject, move, rename, create, delete, publish
    Entity types: category, product, taxonomy
    """
    log = TaxonomyAuditLog(
        taxonomy_id=taxonomy_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(log)
```

#### 1.4 API Endpoints

```python
# =============================================================================
# ONBOARDING API ENDPOINTS
# =============================================================================

@app.get("/api/onboarding/pending", response_model=PendingListResponse)
async def get_pending_taxonomies(
    status: Optional[str] = None,  # filter by status: draft, review, active
    current_user: User = Depends(get_current_user)
):
    """
    Get list of taxonomies pending review.

    Default: returns draft and review status taxonomies.
    """
    session = get_session()
    try:
        query = session.query(PlaceTaxonomy).join(Place)

        if status:
            query = query.filter(PlaceTaxonomy.status == status)
        else:
            query = query.filter(PlaceTaxonomy.status.in_(["draft", "review"]))

        taxonomies = query.order_by(PlaceTaxonomy.discovered_at.desc()).all()

        result = []
        for tax in taxonomies:
            categories = session.query(TaxonomyCategory).filter_by(taxonomy_id=tax.id).all()
            products = session.query(TaxonomyProduct).filter_by(taxonomy_id=tax.id).all()

            result.append(PendingTaxonomyResponse(
                id=str(tax.id),
                place_id=str(tax.place_id),
                place_name=tax.place.name if tax.place else "Unknown",
                place_category=tax.place.category if tax.place else None,
                status=tax.status,
                reviews_sampled=tax.reviews_sampled or 0,
                categories_count=len(categories),
                products_count=len(products),
                approved_categories=len([c for c in categories if c.is_approved]),
                approved_products=len([p for p in products if p.is_approved]),
                discovered_at=tax.discovered_at.isoformat() if tax.discovered_at else None,
            ))

        return PendingListResponse(taxonomies=result, total=len(result))
    finally:
        session.close()


@app.get("/api/onboarding/taxonomies/{taxonomy_id}", response_model=TaxonomyDetailResponse)
async def get_taxonomy_detail(
    taxonomy_id: UUID,
    current_user: User = Depends(get_current_user)
):
    """Get full taxonomy detail for editor."""
    session = get_session()
    try:
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        categories = session.query(TaxonomyCategory).filter_by(taxonomy_id=taxonomy_id).all()
        products = session.query(TaxonomyProduct).filter_by(taxonomy_id=taxonomy_id).all()

        return TaxonomyDetailResponse(
            id=str(taxonomy.id),
            place_id=str(taxonomy.place_id),
            place_name=taxonomy.place.name if taxonomy.place else "Unknown",
            place_category=taxonomy.place.category if taxonomy.place else None,
            status=taxonomy.status,
            reviews_sampled=taxonomy.reviews_sampled or 0,
            entities_discovered=taxonomy.entities_discovered or 0,
            discovered_at=taxonomy.discovered_at.isoformat() if taxonomy.discovered_at else None,
            published_at=taxonomy.published_at.isoformat() if taxonomy.published_at else None,
            published_by=str(taxonomy.published_by) if taxonomy.published_by else None,
            categories=[
                TaxonomyCategoryResponse(
                    id=str(c.id),
                    parent_id=str(c.parent_id) if c.parent_id else None,
                    name=c.name,
                    display_name_en=c.display_name_en,
                    display_name_ar=c.display_name_ar,
                    has_products=c.has_products,
                    is_approved=c.is_approved,
                    approved_by=str(c.approved_by) if c.approved_by else None,
                    approved_at=c.approved_at.isoformat() if c.approved_at else None,
                    rejection_reason=c.rejection_reason,
                    discovered_mention_count=c.discovered_mention_count or 0,
                    mention_count=c.mention_count or 0,
                    avg_sentiment=float(c.avg_sentiment) if c.avg_sentiment else None,
                ) for c in categories
            ],
            products=[
                TaxonomyProductResponse(
                    id=str(p.id),
                    discovered_category_id=str(p.discovered_category_id) if p.discovered_category_id else None,
                    assigned_category_id=str(p.assigned_category_id) if p.assigned_category_id else None,
                    canonical_text=p.canonical_text,
                    display_name=p.display_name,
                    variants=p.variants or [],
                    is_approved=p.is_approved,
                    approved_by=str(p.approved_by) if p.approved_by else None,
                    approved_at=p.approved_at.isoformat() if p.approved_at else None,
                    rejection_reason=p.rejection_reason,
                    discovered_mention_count=p.discovered_mention_count or 0,
                    mention_count=p.mention_count or 0,
                    avg_sentiment=float(p.avg_sentiment) if p.avg_sentiment else None,
                ) for p in products
            ],
        )
    finally:
        session.close()


@app.patch("/api/onboarding/categories/{category_id}", response_model=ActionResponse)
async def update_category(
    category_id: UUID,
    request: CategoryUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update a taxonomy category (approve, reject, move, rename)."""
    session = get_session()
    try:
        category = session.query(TaxonomyCategory).filter_by(id=category_id).first()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        old_value = {
            "is_approved": category.is_approved,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "display_name_en": category.display_name_en,
            "display_name_ar": category.display_name_ar,
            "rejection_reason": category.rejection_reason,
        }

        if request.action == "approve":
            category.is_approved = True
            category.approved_by = current_user.id
            category.approved_at = datetime.utcnow()
            category.rejection_reason = None
            message = f"Category '{category.name}' approved"

        elif request.action == "reject":
            if not request.rejection_reason:
                raise HTTPException(status_code=400, detail="Rejection reason required")
            category.is_approved = False
            category.rejection_reason = request.rejection_reason
            message = f"Category '{category.name}' rejected"

        elif request.action == "move":
            category.parent_id = request.parent_id
            message = f"Category '{category.name}' moved"

        elif request.action == "rename":
            if request.display_name_en:
                category.display_name_en = request.display_name_en
            if request.display_name_ar:
                category.display_name_ar = request.display_name_ar
            message = f"Category '{category.name}' renamed"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        new_value = {
            "is_approved": category.is_approved,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "display_name_en": category.display_name_en,
            "display_name_ar": category.display_name_ar,
            "rejection_reason": category.rejection_reason,
        }

        log_taxonomy_action(
            session, category.taxonomy_id, current_user.id,
            request.action, "category", category_id, old_value, new_value
        )

        session.commit()
        return ActionResponse(success=True, message=message)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.patch("/api/onboarding/products/{product_id}", response_model=ActionResponse)
async def update_product(
    product_id: UUID,
    request: ProductUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update a taxonomy product (approve, reject, move, add_variant)."""
    session = get_session()
    try:
        product = session.query(TaxonomyProduct).filter_by(id=product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        old_value = {
            "is_approved": product.is_approved,
            "assigned_category_id": str(product.assigned_category_id) if product.assigned_category_id else None,
            "variants": product.variants or [],
            "rejection_reason": product.rejection_reason,
        }

        if request.action == "approve":
            product.is_approved = True
            product.approved_by = current_user.id
            product.approved_at = datetime.utcnow()
            product.rejection_reason = None
            # If no assigned category, use discovered category
            if not product.assigned_category_id and product.discovered_category_id:
                product.assigned_category_id = product.discovered_category_id
            message = f"Product '{product.display_name or product.canonical_text}' approved"

        elif request.action == "reject":
            if not request.rejection_reason:
                raise HTTPException(status_code=400, detail="Rejection reason required")
            product.is_approved = False
            product.rejection_reason = request.rejection_reason
            message = f"Product '{product.display_name or product.canonical_text}' rejected"

        elif request.action == "move":
            product.assigned_category_id = request.assigned_category_id
            message = f"Product '{product.display_name or product.canonical_text}' moved"

        elif request.action == "add_variant":
            if not request.variant:
                raise HTTPException(status_code=400, detail="Variant text required")
            variants = product.variants or []
            if request.variant not in variants:
                variants.append(request.variant)
                product.variants = variants
            message = f"Variant '{request.variant}' added"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        new_value = {
            "is_approved": product.is_approved,
            "assigned_category_id": str(product.assigned_category_id) if product.assigned_category_id else None,
            "variants": product.variants or [],
            "rejection_reason": product.rejection_reason,
        }

        log_taxonomy_action(
            session, product.taxonomy_id, current_user.id,
            request.action, "product", product_id, old_value, new_value
        )

        session.commit()
        return ActionResponse(success=True, message=message)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/onboarding/categories", response_model=TaxonomyCategoryResponse)
async def create_category(
    request: CategoryCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new category manually."""
    session = get_session()
    try:
        # Verify taxonomy exists
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=request.taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        category = TaxonomyCategory(
            taxonomy_id=request.taxonomy_id,
            parent_id=request.parent_id,
            name=request.name.lower().replace(" ", "_"),
            display_name_en=request.display_name_en,
            display_name_ar=request.display_name_ar,
            has_products=request.has_products,
            is_approved=True,  # Manually created = auto-approved
            approved_by=current_user.id,
            approved_at=datetime.utcnow(),
        )
        session.add(category)
        session.flush()

        log_taxonomy_action(
            session, request.taxonomy_id, current_user.id,
            "create", "category", category.id,
            None, {"name": category.name, "display_name_en": category.display_name_en}
        )

        session.commit()

        return TaxonomyCategoryResponse(
            id=str(category.id),
            parent_id=str(category.parent_id) if category.parent_id else None,
            name=category.name,
            display_name_en=category.display_name_en,
            display_name_ar=category.display_name_ar,
            has_products=category.has_products,
            is_approved=category.is_approved,
            approved_by=str(category.approved_by) if category.approved_by else None,
            approved_at=category.approved_at.isoformat() if category.approved_at else None,
            rejection_reason=None,
            discovered_mention_count=0,
            mention_count=0,
            avg_sentiment=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/onboarding/products", response_model=TaxonomyProductResponse)
async def create_product(
    request: ProductCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new product manually."""
    session = get_session()
    try:
        # Verify taxonomy exists
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=request.taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        product = TaxonomyProduct(
            taxonomy_id=request.taxonomy_id,
            assigned_category_id=request.assigned_category_id,
            canonical_text=request.display_name.lower(),
            display_name=request.display_name,
            variants=request.variants,
            is_approved=True,  # Manually created = auto-approved
            approved_by=current_user.id,
            approved_at=datetime.utcnow(),
        )
        session.add(product)
        session.flush()

        log_taxonomy_action(
            session, request.taxonomy_id, current_user.id,
            "create", "product", product.id,
            None, {"display_name": product.display_name}
        )

        session.commit()

        return TaxonomyProductResponse(
            id=str(product.id),
            discovered_category_id=None,
            assigned_category_id=str(product.assigned_category_id) if product.assigned_category_id else None,
            canonical_text=product.canonical_text,
            display_name=product.display_name,
            variants=product.variants or [],
            is_approved=product.is_approved,
            approved_by=str(product.approved_by) if product.approved_by else None,
            approved_at=product.approved_at.isoformat() if product.approved_at else None,
            rejection_reason=None,
            discovered_mention_count=0,
            mention_count=0,
            avg_sentiment=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/onboarding/taxonomies/{taxonomy_id}/publish", response_model=ActionResponse)
async def publish_taxonomy(
    taxonomy_id: UUID,
    current_user: User = Depends(get_current_user)
):
    """
    Publish a taxonomy (draft -> active).

    This will:
    1. Set status to 'active'
    2. Set published_at and published_by
    3. Resolve all RawMentions to approved products/categories
    4. Log the publish action
    """
    session = get_session()
    try:
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
        if not taxonomy:
            raise HTTPException(status_code=404, detail="Taxonomy not found")

        if taxonomy.status == "active":
            raise HTTPException(status_code=400, detail="Taxonomy already published")

        # Check that at least some items are approved
        approved_categories = session.query(TaxonomyCategory).filter_by(
            taxonomy_id=taxonomy_id, is_approved=True
        ).count()
        approved_products = session.query(TaxonomyProduct).filter_by(
            taxonomy_id=taxonomy_id, is_approved=True
        ).count()

        if approved_categories == 0 and approved_products == 0:
            raise HTTPException(status_code=400, detail="No approved categories or products")

        # Update taxonomy status
        old_status = taxonomy.status
        taxonomy.status = "active"
        taxonomy.published_at = datetime.utcnow()
        taxonomy.published_by = current_user.id

        # Resolve RawMentions to approved products
        # Get all approved products for this place
        approved_products_list = session.query(TaxonomyProduct).filter_by(
            taxonomy_id=taxonomy_id, is_approved=True
        ).all()

        # Build mapping: canonical_text -> product_id and variants -> product_id
        text_to_product = {}
        for product in approved_products_list:
            text_to_product[product.canonical_text.lower()] = product.id
            for variant in (product.variants or []):
                text_to_product[variant.lower()] = product.id

        # Update RawMentions
        mentions = session.query(RawMention).filter_by(
            place_id=taxonomy.place_id,
            mention_type="product",
            resolved_product_id=None
        ).all()

        resolved_count = 0
        for mention in mentions:
            mention_text_lower = mention.mention_text.lower().strip()
            if mention_text_lower in text_to_product:
                mention.resolved_product_id = text_to_product[mention_text_lower]
                resolved_count += 1

        # Log publish action
        log_taxonomy_action(
            session, taxonomy_id, current_user.id,
            "publish", "taxonomy", taxonomy_id,
            {"status": old_status},
            {"status": "active", "resolved_mentions": resolved_count}
        )

        session.commit()

        return ActionResponse(
            success=True,
            message=f"Taxonomy published. {resolved_count} mentions resolved."
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()
```

---

## 2. Frontend Specification

### 2.1 Directory Structure

```
onboarding-portal/
├── Dockerfile
├── next.config.js
├── package.json
├── postcss.config.js
├── tailwind.config.js
├── tsconfig.json
├── public/
│   └── favicon.ico
└── src/
    ├── app/
    │   ├── globals.css
    │   ├── layout.tsx
    │   ├── page.tsx                    # Pending list
    │   ├── login/
    │   │   └── page.tsx
    │   └── [taxonomyId]/
    │       └── page.tsx                # Taxonomy editor
    ├── components/
    │   ├── AuthGuard.tsx
    │   ├── CategoryTree.tsx
    │   ├── ProductList.tsx
    │   ├── ApprovalBadge.tsx
    │   ├── MoveModal.tsx
    │   ├── RejectModal.tsx
    │   ├── AddCategoryModal.tsx
    │   ├── AddProductModal.tsx
    │   └── ui/
    │       ├── button.tsx
    │       ├── card.tsx
    │       ├── input.tsx
    │       ├── badge.tsx
    │       └── modal.tsx
    └── lib/
        ├── api.ts
        ├── auth.tsx
        └── cn.ts
```

### 2.2 API Client (`src/lib/api.ts`)

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.nurliya.com'

function getAuthHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

// Types
export interface PendingTaxonomy {
  id: string
  place_id: string
  place_name: string
  place_category: string | null
  status: string
  reviews_sampled: number
  categories_count: number
  products_count: number
  approved_categories: number
  approved_products: number
  discovered_at: string | null
}

export interface TaxonomyCategory {
  id: string
  parent_id: string | null
  name: string
  display_name_en: string | null
  display_name_ar: string | null
  has_products: boolean
  is_approved: boolean
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
  discovered_mention_count: number
  mention_count: number
  avg_sentiment: number | null
}

export interface TaxonomyProduct {
  id: string
  discovered_category_id: string | null
  assigned_category_id: string | null
  canonical_text: string
  display_name: string | null
  variants: string[]
  is_approved: boolean
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
  discovered_mention_count: number
  mention_count: number
  avg_sentiment: number | null
}

export interface TaxonomyDetail {
  id: string
  place_id: string
  place_name: string
  place_category: string | null
  status: string
  reviews_sampled: number
  entities_discovered: number
  discovered_at: string | null
  published_at: string | null
  published_by: string | null
  categories: TaxonomyCategory[]
  products: TaxonomyProduct[]
}

// API Functions
export async function fetchPendingTaxonomies(): Promise<{ taxonomies: PendingTaxonomy[], total: number }> {
  const res = await fetch(`${API_URL}/api/onboarding/pending`, { headers: getAuthHeaders() })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch pending taxonomies')
  }
  return res.json()
}

export async function fetchTaxonomyDetail(taxonomyId: string): Promise<TaxonomyDetail> {
  const res = await fetch(`${API_URL}/api/onboarding/taxonomies/${taxonomyId}`, { headers: getAuthHeaders() })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch taxonomy detail')
  }
  return res.json()
}

export async function approveCategory(categoryId: string): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/categories/${categoryId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'approve' }),
  })
  if (!res.ok) throw new Error('Failed to approve category')
  return res.json()
}

export async function rejectCategory(categoryId: string, reason: string): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/categories/${categoryId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'reject', rejection_reason: reason }),
  })
  if (!res.ok) throw new Error('Failed to reject category')
  return res.json()
}

export async function moveCategory(categoryId: string, parentId: string | null): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/categories/${categoryId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'move', parent_id: parentId }),
  })
  if (!res.ok) throw new Error('Failed to move category')
  return res.json()
}

export async function approveProduct(productId: string): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/products/${productId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'approve' }),
  })
  if (!res.ok) throw new Error('Failed to approve product')
  return res.json()
}

export async function rejectProduct(productId: string, reason: string): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/products/${productId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'reject', rejection_reason: reason }),
  })
  if (!res.ok) throw new Error('Failed to reject product')
  return res.json()
}

export async function moveProduct(productId: string, categoryId: string | null): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/products/${productId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'move', assigned_category_id: categoryId }),
  })
  if (!res.ok) throw new Error('Failed to move product')
  return res.json()
}

export async function addProductVariant(productId: string, variant: string): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/products/${productId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'add_variant', variant }),
  })
  if (!res.ok) throw new Error('Failed to add variant')
  return res.json()
}

export async function createCategory(
  taxonomyId: string,
  name: string,
  displayNameEn: string,
  displayNameAr?: string,
  parentId?: string,
  hasProducts?: boolean
): Promise<TaxonomyCategory> {
  const res = await fetch(`${API_URL}/api/onboarding/categories`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      taxonomy_id: taxonomyId,
      parent_id: parentId || null,
      name,
      display_name_en: displayNameEn,
      display_name_ar: displayNameAr || null,
      has_products: hasProducts ?? true,
    }),
  })
  if (!res.ok) throw new Error('Failed to create category')
  return res.json()
}

export async function createProduct(
  taxonomyId: string,
  displayName: string,
  categoryId?: string,
  variants?: string[]
): Promise<TaxonomyProduct> {
  const res = await fetch(`${API_URL}/api/onboarding/products`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      taxonomy_id: taxonomyId,
      assigned_category_id: categoryId || null,
      display_name: displayName,
      variants: variants || [],
    }),
  })
  if (!res.ok) throw new Error('Failed to create product')
  return res.json()
}

export async function publishTaxonomy(taxonomyId: string): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/taxonomies/${taxonomyId}/publish`, {
    method: 'POST',
    headers: getAuthHeaders(),
  })
  if (!res.ok) throw new Error('Failed to publish taxonomy')
  return res.json()
}
```

### 2.3 Theme (Copy from client-portal)

**tailwind.config.js:**
```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        background: '#09090b',
        foreground: '#fafafa',
        card: '#18181b',
        'card-hover': '#1f1f23',
        border: '#27272a',
        muted: '#71717a',
        primary: {
          DEFAULT: '#3b82f6',
          foreground: '#ffffff',
          hover: '#2563eb',
        },
        destructive: {
          DEFAULT: '#ef4444',
          foreground: '#ffffff',
        },
        success: {
          DEFAULT: '#10b981',
          foreground: '#ffffff',
        },
        warning: {
          DEFAULT: '#f59e0b',
          foreground: '#ffffff',
        },
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
```

---

## 3. Docker Configuration

### 3.1 Dockerfile (onboarding-portal/Dockerfile)

```dockerfile
FROM node:20-alpine AS base

FROM base AS deps
WORKDIR /app
COPY package.json ./
RUN npm install

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=https://api.nurliya.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
```

### 3.2 docker-compose.yml Addition

```yaml
onboarding-portal:
  build:
    context: ./onboarding-portal
    dockerfile: Dockerfile
    args:
      - NEXT_PUBLIC_API_URL=${ONBOARDING_API_URL:-https://api.nurliya.com}
  container_name: nurliya-onboarding-portal
  ports:
    - "3001:3000"
  depends_on:
    - api
  restart: unless-stopped
```

---

## 4. Implementation Checklist

### 4.1 Backend (pipline/api.py)
- [x] Add imports for taxonomy models ✅ (2026-02-02)
- [x] Add Pydantic request/response models ✅ (2026-02-02)
- [x] Add `log_taxonomy_action()` helper ✅ (2026-02-02)
- [x] Add `GET /api/onboarding/pending` ✅ (2026-02-02)
- [x] Add `GET /api/onboarding/taxonomies/{id}` ✅ (2026-02-02)
- [x] Add `PATCH /api/onboarding/categories/{id}` ✅ (2026-02-02)
- [x] Add `PATCH /api/onboarding/products/{id}` ✅ (2026-02-02)
- [x] Add `POST /api/onboarding/categories` ✅ (2026-02-02)
- [x] Add `POST /api/onboarding/products` ✅ (2026-02-02)
- [x] Add `POST /api/onboarding/taxonomies/{id}/publish` ✅ (2026-02-02)

### 4.2 Onboarding Portal Setup
- [x] Create `onboarding-portal/` directory ✅ (2026-02-02)
- [x] Create `package.json` ✅ (2026-02-02)
- [x] Create `next.config.js` ✅ (2026-02-02)
- [x] Create `tailwind.config.js` ✅ (2026-02-02)
- [x] Create `postcss.config.js` ✅ (2026-02-02)
- [x] Create `tsconfig.json` ✅ (2026-02-02)
- [x] Create `Dockerfile` ✅ (2026-02-02)
- [x] Create `src/app/globals.css` ✅ (2026-02-02)
- [x] Create `src/lib/cn.ts` ✅ (2026-02-02)

### 4.3 Auth & Layout
- [x] Create `src/lib/auth.tsx` ✅ (2026-02-02)
- [x] Create `src/lib/api.ts` ✅ (2026-02-02)
- [x] Create `src/app/layout.tsx` ✅ (2026-02-02)
- [x] Create `src/app/login/page.tsx` ✅ (2026-02-02)
- [x] Create `src/components/AuthGuard.tsx` ✅ (2026-02-02)

### 4.4 UI Components
- [x] Copy `src/components/ui/button.tsx` ✅ (2026-02-02)
- [x] Copy `src/components/ui/card.tsx` ✅ (2026-02-02)
- [x] Copy `src/components/ui/input.tsx` ✅ (2026-02-02)
- [x] Copy `src/components/ui/badge.tsx` ✅ (2026-02-02)
- [x] Create `src/components/ApprovalBadge.tsx` ✅ (2026-02-02)
- [x] Create `src/components/MoveModal.tsx` ✅ (2026-02-02)
- [x] Create `src/components/RejectModal.tsx` ✅ (2026-02-02)
- [x] Create `src/components/AddCategoryModal.tsx` ✅ (2026-02-02)
- [x] Create `src/components/AddProductModal.tsx` ✅ (2026-02-02)

### 4.5 Pages
- [x] Create `src/app/page.tsx` (pending list) ✅ (2026-02-02)
- [x] Create `src/components/CategoryTree.tsx` ✅ (2026-02-02)
- [x] Create `src/components/ProductList.tsx` ✅ (2026-02-02)
- [x] Create `src/app/[taxonomyId]/page.tsx` (editor) ✅ (2026-02-02)

### 4.6 Docker & Deployment
- [x] Add onboarding-portal service to `docker-compose.yml` ✅ (2026-02-02)
- [x] Build and start container ✅ (2026-02-02)
- [x] Configure Cloudflare Tunnel for `onboarding.nurliya.com` ✅ (2026-02-02)
- [x] Verify domain access ✅ (2026-02-02)

---

## 5. Testing

### 5.1 API Testing

```bash
# Login and get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"test123"}' | jq -r '.access_token')

# Get pending taxonomies
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/onboarding/pending

# Get taxonomy detail
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/onboarding/taxonomies/{taxonomy_id}

# Approve category
curl -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"approve"}' \
  http://localhost:8000/api/onboarding/categories/{category_id}

# Publish taxonomy
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/onboarding/taxonomies/{taxonomy_id}/publish
```

### 5.2 Frontend Testing

1. Start onboarding portal: `cd onboarding-portal && npm run dev`
2. Open http://localhost:3001
3. Login with valid credentials
4. Verify pending list loads
5. Click into a taxonomy
6. Test approve/reject/move actions
7. Test publish

### 5.3 Docker Testing

```bash
docker-compose up -d onboarding-portal
curl http://localhost:3001
```

---

## 6. Notes

- All specialists share the same user table (existing auth)
- Any specialist can review any pending taxonomy
- Manually created items are auto-approved
- Publish resolves RawMentions by text matching to approved products
- Audit log captures all actions for compliance

---

## 7. Implementation Log

### 2026-02-02 - Backend Models Added

**File: `pipline/api.py`**

Added imports for taxonomy models:
```python
from database import (
    Place, Review, ReviewAnalysis, Job, ScrapeJob, ActivityLog, User, AnomalyInsight,
    PlaceTaxonomy, TaxonomyCategory, TaxonomyProduct, RawMention, TaxonomyAuditLog,
    get_session, create_tables
)
from datetime import datetime
```

Added Pydantic models:
- `CategoryUpdateRequest` - Request to update a taxonomy category
- `ProductUpdateRequest` - Request to update a taxonomy product
- `CategoryCreateRequest` - Request to create a new category
- `ProductCreateRequest` - Request to create a new product
- `PendingTaxonomyResponse` - Summary of a taxonomy pending review
- `PendingListResponse` - List of pending taxonomies
- `TaxonomyCategoryResponse` - Category in taxonomy detail
- `TaxonomyProductResponse` - Product in taxonomy detail
- `TaxonomyDetailResponse` - Full taxonomy detail for editor
- `ActionResponse` - Generic success response

Added helper function:
- `log_taxonomy_action()` - Logs actions to TaxonomyAuditLog

### 2026-02-02 - Deployment Complete

**Docker Build & Deploy:**
- Built onboarding-portal container
- Started via `docker compose up -d onboarding-portal`
- Container running on port 3001

**Cloudflare Tunnel Configuration:**
- Added ingress rule to `/etc/cloudflared/config.yml`:
  ```yaml
  - hostname: onboarding.nurliya.com
    service: http://localhost:3001
  ```
- Routed DNS: `cloudflared tunnel route dns nurliya onboarding.nurliya.com`
- Restarted cloudflared service

**Verification:**
```bash
curl -sI https://onboarding.nurliya.com
# HTTP/2 200
# x-powered-by: Next.js
```

**Portal Live:** https://onboarding.nurliya.com

---

## 8. Phase 3 Summary

| Component | Status |
|-----------|--------|
| Backend API (7 endpoints) | ✅ Deployed |
| Frontend Portal (Next.js 14) | ✅ Deployed |
| Docker Container | ✅ Running |
| Domain (Cloudflare Tunnel) | ✅ Active |
| Documentation | ✅ Updated |

**Phase 3 Complete. Proceed to Phase 4: Integration.**
