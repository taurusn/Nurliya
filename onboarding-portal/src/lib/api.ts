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
export async function fetchPendingTaxonomies(status?: string): Promise<{ taxonomies: PendingTaxonomy[], total: number }> {
  const url = status
    ? `${API_URL}/api/onboarding/pending?status=${status}`
    : `${API_URL}/api/onboarding/pending`
  const res = await fetch(url, { headers: getAuthHeaders() })
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

export async function renameCategory(
  categoryId: string,
  displayNameEn?: string,
  displayNameAr?: string
): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/categories/${categoryId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      action: 'rename',
      display_name_en: displayNameEn,
      display_name_ar: displayNameAr,
    }),
  })
  if (!res.ok) throw new Error('Failed to rename category')
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

// Mention types
export interface Mention {
  id: string
  mention_text: string
  mention_type: string
  sentiment: string | null
  review_id: string
  review_text: string
  review_author: string | null
  review_rating: number | null
  review_date: string | null
  similarity_score?: number | null
}

export interface MentionListResponse {
  mentions: Mention[]
  total: number
  matched_count: number
  below_threshold_count: number
}

export interface OrphanMentionsResponse {
  product_orphans: Mention[]
  category_orphans: Mention[]
  total_product_orphans: number
  total_category_orphans: number
}

// Fetch mentions for a product
export async function fetchProductMentions(
  productId: string,
  includeBelow: boolean = true
): Promise<MentionListResponse> {
  const res = await fetch(
    `${API_URL}/api/onboarding/products/${productId}/mentions?include_below_threshold=${includeBelow}`,
    { headers: getAuthHeaders() }
  )
  if (!res.ok) throw new Error('Failed to fetch product mentions')
  return res.json()
}

// Fetch mentions for a category
export async function fetchCategoryMentions(
  categoryId: string,
  includeBelow: boolean = true
): Promise<MentionListResponse> {
  const res = await fetch(
    `${API_URL}/api/onboarding/categories/${categoryId}/mentions?include_below_threshold=${includeBelow}`,
    { headers: getAuthHeaders() }
  )
  if (!res.ok) throw new Error('Failed to fetch category mentions')
  return res.json()
}

// Fetch orphan mentions for a taxonomy
export async function fetchOrphanMentions(taxonomyId: string): Promise<OrphanMentionsResponse> {
  const res = await fetch(
    `${API_URL}/api/onboarding/taxonomies/${taxonomyId}/orphan-mentions`,
    { headers: getAuthHeaders() }
  )
  if (!res.ok) throw new Error('Failed to fetch orphan mentions')
  return res.json()
}
