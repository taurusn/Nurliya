'use client'

import { useState, useMemo } from 'react'
import { TaxonomyProduct, TaxonomyCategory } from '@/lib/api'
import { ApprovalBadge } from '@/components/ApprovalBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Check, X, Move, Plus, MessageSquare, GitMerge, Pencil, Trash2, Search } from 'lucide-react'

interface ProductListProps {
  products: TaxonomyProduct[]
  categories: TaxonomyCategory[]
  selectedCategoryId: string | null
  onApprove: (productId: string) => void
  onReject: (productId: string) => void
  onMove: (productId: string) => void
  onAddVariant: (productId: string) => void
  onShowMentions?: (productId: string, productName: string) => void
  onMerge?: (productId: string) => void
  onEdit?: (productId: string) => void
  onDelete?: (productId: string) => void
}

export function ProductList({
  products,
  categories,
  selectedCategoryId,
  onApprove,
  onReject,
  onMove,
  onAddVariant,
  onShowMentions,
  onMerge,
  onEdit,
  onDelete,
}: ProductListProps) {
  const [searchTerm, setSearchTerm] = useState('')

  // Filter products based on selected category and search term
  const filteredProducts = useMemo(() => {
    let filtered = selectedCategoryId === null
      ? products
      : products.filter(
          (p) =>
            (p.assigned_category_id ?? p.discovered_category_id) === selectedCategoryId
        )

    // Apply search filter
    if (searchTerm.trim()) {
      const search = searchTerm.toLowerCase()
      filtered = filtered.filter((p) =>
        p.display_name?.toLowerCase().includes(search) ||
        p.canonical_text.toLowerCase().includes(search) ||
        p.variants?.some((v) => v.toLowerCase().includes(search))
      )
    }

    return filtered
  }, [products, selectedCategoryId, searchTerm])

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
    return cat?.display_name_ar || cat?.display_name_en || cat?.name || 'Unknown'
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
            <Button size="sm" variant="ghost" onClick={() => onApprove(product.id)} title="Approve">
              <Check className="w-4 h-4 text-success" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onReject(product.id)} title="Reject">
              <X className="w-4 h-4 text-destructive" />
            </Button>
          </>
        )}
        {onEdit && (
          <Button size="sm" variant="ghost" onClick={() => onEdit(product.id)} title="Edit">
            <Pencil className="w-4 h-4 text-muted" />
          </Button>
        )}
        {onMerge && (
          <Button size="sm" variant="ghost" onClick={() => onMerge(product.id)} title="Merge into another">
            <GitMerge className="w-4 h-4 text-muted" />
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => onMove(product.id)} title="Move to category">
          <Move className="w-4 h-4 text-muted" />
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onAddVariant(product.id)} title="Add variant">
          <Plus className="w-4 h-4 text-muted" />
        </Button>
        {onShowMentions && product.discovered_mention_count > 0 && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onShowMentions(product.id, product.display_name || product.canonical_text)}
            title="View mentions"
          >
            <MessageSquare className="w-4 h-4 text-primary" />
          </Button>
        )}
        {onDelete && (
          <Button size="sm" variant="ghost" onClick={() => onDelete(product.id)} title="Delete">
            <Trash2 className="w-4 h-4 text-muted hover:text-destructive" />
          </Button>
        )}
      </div>
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
        <Input
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search products..."
          className="pl-9"
        />
      </div>

      {filteredProducts.length === 0 ? (
        <div className="text-center py-8 text-muted">
          {searchTerm ? 'No products match your search' : 'No products in this category'}
        </div>
      ) : (
        <>
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
        </>
      )}
    </div>
  )
}
