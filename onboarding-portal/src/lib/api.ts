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

export async function updateProduct(
  productId: string,
  updates: {
    display_name?: string
    variants?: string[]
    category_id?: string | null
  }
): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/products/${productId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      action: 'update',
      display_name: updates.display_name,
      variants: updates.variants,
      assigned_category_id: updates.category_id,
    }),
  })
  if (!res.ok) throw new Error('Failed to update product')
  return res.json()
}

export async function mergeProducts(
  sourceProductId: string,
  targetProductId: string
): Promise<{ success: boolean, message: string, target_id: string, merged_mention_count: number }> {
  const res = await fetch(`${API_URL}/api/onboarding/products/merge`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      source_id: sourceProductId,
      target_id: targetProductId,
    }),
  })
  if (!res.ok) throw new Error('Failed to merge products')
  return res.json()
}

export async function mergeCategories(
  sourceCategoryId: string,
  targetCategoryId: string
): Promise<{ success: boolean, message: string, target_id: string, merged_mention_count: number }> {
  const res = await fetch(`${API_URL}/api/onboarding/categories/merge`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      source_id: sourceCategoryId,
      target_id: targetCategoryId,
    }),
  })
  if (!res.ok) throw new Error('Failed to merge categories')
  return res.json()
}

export async function deleteProduct(productId: string): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/products/${productId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  })
  if (!res.ok) throw new Error('Failed to delete product')
  return res.json()
}

export async function deleteCategory(categoryId: string): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/categories/${categoryId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  })
  if (!res.ok) throw new Error('Failed to delete category')
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

// Import types
export interface ImportProduct {
  name: string
  display_name: string
  variants: string[]
}

export interface ImportCategory {
  name: string
  display_name_en: string
  display_name_ar?: string
  is_aspect: boolean
  is_parent?: boolean  // True for parent/container categories
  parent?: string      // Name of parent category (for hierarchy)
  examples: string[]
  products: ImportProduct[]
}

export interface TaxonomyImportData {
  categories: ImportCategory[]
}

export async function importTaxonomy(
  taxonomyId: string,
  data: TaxonomyImportData
): Promise<{ success: boolean, message: string }> {
  const res = await fetch(`${API_URL}/api/onboarding/taxonomies/${taxonomyId}/import`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to import taxonomy')
  return res.json()
}

// Menu Images
export interface MenuImage {
  id: string
  image_url: string
  original_url: string | null
  created_at: string | null
}

export interface MenuImagesResponse {
  images: MenuImage[]
  total: number
  place_name: string | null
}

export async function fetchMenuImages(taxonomyId: string): Promise<MenuImagesResponse> {
  const res = await fetch(`${API_URL}/api/onboarding/taxonomies/${taxonomyId}/menu-images`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch menu images')
  }
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

// Grouped mentions types
export interface MentionGroup {
  normalized_text: string
  display_text: string
  mention_ids: string[]
  count: number
  sentiments: { positive: number; negative: number; neutral: number }
  avg_similarity: number | null
  sample_reviews: string[]
}

export interface GroupedMentionsResponse {
  groups: MentionGroup[]
  total_mentions: number
  total_groups: number
  entity_id: string
  entity_name: string
}

export interface GroupedOrphansResponse {
  product_groups: MentionGroup[]
  category_groups: MentionGroup[]
  total_product_mentions: number
  total_category_mentions: number
  total_product_groups: number
  total_category_groups: number
}

export interface BulkMoveResponse {
  success: boolean
  moved_count: number
  message: string
}

// Fetch mentions for a product
export async function fetchProductMentions(
  productId: string,
  includeBelow: boolean = true,
  limit: number = 50,
  offset: number = 0
): Promise<MentionListResponse> {
  const res = await fetch(
    `${API_URL}/api/onboarding/products/${productId}/mentions?include_below_threshold=${includeBelow}&limit=${limit}&offset=${offset}`,
    { headers: getAuthHeaders() }
  )
  if (!res.ok) throw new Error('Failed to fetch product mentions')
  return res.json()
}

// Fetch mentions for a category
export async function fetchCategoryMentions(
  categoryId: string,
  includeBelow: boolean = true,
  limit: number = 50,
  offset: number = 0
): Promise<MentionListResponse> {
  const res = await fetch(
    `${API_URL}/api/onboarding/categories/${categoryId}/mentions?include_below_threshold=${includeBelow}&limit=${limit}&offset=${offset}`,
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

// Fetch grouped product mentions
export async function fetchGroupedProductMentions(productId: string): Promise<GroupedMentionsResponse> {
  const res = await fetch(
    `${API_URL}/api/onboarding/products/${productId}/mentions/grouped`,
    { headers: getAuthHeaders() }
  )
  if (!res.ok) throw new Error('Failed to fetch grouped product mentions')
  return res.json()
}

// Fetch grouped category mentions
export async function fetchGroupedCategoryMentions(categoryId: string): Promise<GroupedMentionsResponse> {
  const res = await fetch(
    `${API_URL}/api/onboarding/categories/${categoryId}/mentions/grouped`,
    { headers: getAuthHeaders() }
  )
  if (!res.ok) throw new Error('Failed to fetch grouped category mentions')
  return res.json()
}

// Fetch grouped orphan mentions
export async function fetchGroupedOrphanMentions(taxonomyId: string): Promise<GroupedOrphansResponse> {
  const res = await fetch(
    `${API_URL}/api/onboarding/taxonomies/${taxonomyId}/orphan-mentions/grouped`,
    { headers: getAuthHeaders() }
  )
  if (!res.ok) throw new Error('Failed to fetch grouped orphan mentions')
  return res.json()
}

// Bulk move mentions to a product or category
export async function bulkMoveMentions(
  mentionIds: string[],
  targetType: 'product' | 'category',
  targetId: string
): Promise<BulkMoveResponse> {
  const res = await fetch(`${API_URL}/api/onboarding/mentions/move`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      mention_ids: mentionIds,
      target_type: targetType,
      target_id: targetId,
    }),
  })
  if (!res.ok) throw new Error('Failed to move mentions')
  return res.json()
}
