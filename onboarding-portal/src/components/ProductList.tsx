'use client'

import { TaxonomyProduct, TaxonomyCategory } from '@/lib/api'
import { ApprovalBadge } from '@/components/ApprovalBadge'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Check, X, Move, Plus } from 'lucide-react'

interface ProductListProps {
  products: TaxonomyProduct[]
  categories: TaxonomyCategory[]
  selectedCategoryId: string | null
  onApprove: (productId: string) => void
  onReject: (productId: string) => void
  onMove: (productId: string) => void
  onAddVariant: (productId: string) => void
}

export function ProductList({
  products,
  categories,
  selectedCategoryId,
  onApprove,
  onReject,
  onMove,
  onAddVariant,
}: ProductListProps) {
  // Filter products based on selected category
  const filteredProducts =
    selectedCategoryId === null
      ? products
      : products.filter(
          (p) =>
            p.assigned_category_id === selectedCategoryId ||
            p.discovered_category_id === selectedCategoryId
        )

  // Group products by status for display
  const pendingProducts = filteredProducts.filter(
    (p) => !p.is_approved && !p.rejection_reason
  )
  const approvedProducts = filteredProducts.filter((p) => p.is_approved)
  const rejectedProducts = filteredProducts.filter(
    (p) => !p.is_approved && p.rejection_reason
  )

  const getCategoryName = (categoryId: string | null) => {
    if (!categoryId) return 'Standalone'
    const cat = categories.find((c) => c.id === categoryId)
    return cat?.display_name_en || cat?.name || 'Unknown'
  }

  const ProductRow = ({ product }: { product: TaxonomyProduct }) => (
    <div className="flex items-center gap-3 px-3 py-2 hover:bg-card-hover rounded-lg group">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">
            {product.display_name || product.canonical_text}
          </span>
          <ApprovalBadge
            isApproved={product.is_approved}
            rejectionReason={product.rejection_reason}
          />
        </div>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-muted">
            {getCategoryName(product.assigned_category_id || product.discovered_category_id)}
          </span>
          {product.discovered_mention_count > 0 && (
            <span className="text-xs text-muted">
              ({product.discovered_mention_count} mentions)
            </span>
          )}
          {product.variants && product.variants.length > 0 && (
            <Badge variant="outline" className="text-xs">
              +{product.variants.length} variants
            </Badge>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {!product.is_approved && !product.rejection_reason && (
          <>
            <Button size="sm" variant="ghost" onClick={() => onApprove(product.id)}>
              <Check className="w-4 h-4 text-success" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onReject(product.id)}>
              <X className="w-4 h-4 text-destructive" />
            </Button>
          </>
        )}
        <Button size="sm" variant="ghost" onClick={() => onMove(product.id)}>
          <Move className="w-4 h-4 text-muted" />
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onAddVariant(product.id)}>
          <Plus className="w-4 h-4 text-muted" />
        </Button>
      </div>
    </div>
  )

  if (filteredProducts.length === 0) {
    return (
      <div className="text-center py-8 text-muted">
        No products in this category
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Pending */}
      {pendingProducts.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-warning mb-2 flex items-center gap-2">
            Pending Review ({pendingProducts.length})
          </h4>
          <div className="space-y-1">
            {pendingProducts.map((product) => (
              <ProductRow key={product.id} product={product} />
            ))}
          </div>
        </div>
      )}

      {/* Approved */}
      {approvedProducts.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-success mb-2 flex items-center gap-2">
            Approved ({approvedProducts.length})
          </h4>
          <div className="space-y-1">
            {approvedProducts.map((product) => (
              <ProductRow key={product.id} product={product} />
            ))}
          </div>
        </div>
      )}

      {/* Rejected */}
      {rejectedProducts.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-destructive mb-2 flex items-center gap-2">
            Rejected ({rejectedProducts.length})
          </h4>
          <div className="space-y-1">
            {rejectedProducts.map((product) => (
              <ProductRow key={product.id} product={product} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
