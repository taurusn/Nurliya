'use client'

import { useState, useMemo } from 'react'
import { TaxonomyProduct } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Search, GitMerge, ArrowRight, X } from 'lucide-react'

interface MergeProductModalProps {
  isOpen: boolean
  onClose: () => void
  onMerge: (sourceId: string, targetId: string) => Promise<void>
  sourceProduct: TaxonomyProduct
  products: TaxonomyProduct[]
}

export function MergeProductModal({
  isOpen,
  onClose,
  onMerge,
  sourceProduct,
  products,
}: MergeProductModalProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedTarget, setSelectedTarget] = useState<TaxonomyProduct | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Filter out the source product and search
  const availableTargets = useMemo(() => {
    return products.filter((p) => {
      if (p.id === sourceProduct.id) return false
      if (!searchTerm) return true
      const search = searchTerm.toLowerCase()
      return (
        p.display_name?.toLowerCase().includes(search) ||
        p.canonical_text.toLowerCase().includes(search) ||
        p.variants?.some((v) => v.toLowerCase().includes(search))
      )
    })
  }, [products, sourceProduct.id, searchTerm])

  const handleMerge = async () => {
    if (!selectedTarget) return
    setLoading(true)
    setError('')
    try {
      await onMerge(sourceProduct.id, selectedTarget.id)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to merge products')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    setSearchTerm('')
    setSelectedTarget(null)
    setError('')
    onClose()
  }

  if (!isOpen) return null

  const sourceName = sourceProduct.display_name || sourceProduct.canonical_text
  const targetName = selectedTarget?.display_name || selectedTarget?.canonical_text

  // Calculate merged result preview
  const mergedVariants = selectedTarget
    ? [
        ...(selectedTarget.variants || []),
        sourceProduct.canonical_text,
        ...(sourceProduct.variants || []),
      ].filter((v, i, arr) => arr.indexOf(v) === i)
    : []
  const mergedMentions =
    (selectedTarget?.discovered_mention_count || 0) + (sourceProduct.discovered_mention_count || 0)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />
      <div className="relative bg-card border border-border rounded-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <GitMerge className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Merge Products</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={handleClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto flex-1">
          {error && (
            <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm">
              {error}
            </div>
          )}

          {/* Source product */}
          <div className="mb-4">
            <label className="text-sm text-muted mb-2 block">Merging this product:</label>
            <div className="p-3 bg-card-hover border border-border rounded-lg">
              <div className="font-medium text-foreground">{sourceName}</div>
              <div className="flex items-center gap-2 mt-1 text-xs text-muted">
                <span>{sourceProduct.discovered_mention_count} mentions</span>
                {sourceProduct.variants && sourceProduct.variants.length > 0 && (
                  <Badge variant="outline" className="text-xs">
                    +{sourceProduct.variants.length} variants
                  </Badge>
                )}
              </div>
              {sourceProduct.variants && sourceProduct.variants.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {sourceProduct.variants.map((v, i) => (
                    <span key={i} className="text-xs px-2 py-0.5 bg-muted/20 rounded">
                      {v}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center my-3">
            <ArrowRight className="w-5 h-5 text-muted" />
          </div>

          {/* Target selection */}
          <div className="mb-4">
            <label className="text-sm text-muted mb-2 block">Into this product:</label>

            {/* Search */}
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <Input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search products..."
                className="pl-9"
              />
            </div>

            {/* Product list */}
            <div className="border border-border rounded-lg max-h-48 overflow-y-auto">
              {availableTargets.length === 0 ? (
                <div className="p-4 text-center text-muted text-sm">
                  No matching products found
                </div>
              ) : (
                availableTargets.map((product) => {
                  const name = product.display_name || product.canonical_text
                  const isSelected = selectedTarget?.id === product.id
                  return (
                    <button
                      key={product.id}
                      onClick={() => setSelectedTarget(product)}
                      className={`w-full p-3 text-left border-b border-border last:border-b-0 hover:bg-card-hover transition-colors ${
                        isSelected ? 'bg-primary/10 border-primary' : ''
                      }`}
                    >
                      <div className="font-medium text-foreground">{name}</div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted">
                        <span>{product.discovered_mention_count} mentions</span>
                        {product.variants && product.variants.length > 0 && (
                          <span>+{product.variants.length} variants</span>
                        )}
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </div>

          {/* Preview */}
          {selectedTarget && (
            <div className="p-4 bg-success/10 border border-success/20 rounded-lg">
              <div className="text-sm font-medium text-success mb-2">Merge Preview</div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted">Result name:</span>
                  <span className="text-foreground font-medium">{targetName}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted">Total mentions:</span>
                  <span className="text-foreground">{mergedMentions}</span>
                </div>
                <div className="text-sm">
                  <span className="text-muted">All variants:</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {mergedVariants.map((v, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 bg-card rounded">
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-4 border-t border-border">
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleMerge}
            disabled={!selectedTarget || loading}
            className="bg-primary hover:bg-primary/90"
          >
            {loading ? 'Merging...' : 'Confirm Merge'}
          </Button>
        </div>
      </div>
    </div>
  )
}
