'use client'

import { useState, useEffect } from 'react'
import { TaxonomyProduct, TaxonomyCategory } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { X, Plus, Pencil } from 'lucide-react'

interface EditProductModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (productId: string, updates: {
    display_name?: string
    variants?: string[]
    category_id?: string | null
  }) => Promise<void>
  product: TaxonomyProduct
  categories: TaxonomyCategory[]
}

export function EditProductModal({
  isOpen,
  onClose,
  onSave,
  product,
  categories,
}: EditProductModalProps) {
  const [displayName, setDisplayName] = useState('')
  const [variants, setVariants] = useState<string[]>([])
  const [newVariant, setNewVariant] = useState('')
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Reset form when product changes
  useEffect(() => {
    if (product) {
      setDisplayName(product.display_name || product.canonical_text)
      setVariants(product.variants || [])
      setCategoryId(product.assigned_category_id || product.discovered_category_id)
    }
  }, [product])

  const handleAddVariant = () => {
    const trimmed = newVariant.trim()
    if (trimmed && !variants.includes(trimmed)) {
      setVariants([...variants, trimmed])
      setNewVariant('')
    }
  }

  const handleRemoveVariant = (variant: string) => {
    setVariants(variants.filter((v) => v !== variant))
  }

  const handleSave = async () => {
    setLoading(true)
    setError('')
    try {
      await onSave(product.id, {
        display_name: displayName,
        variants,
        category_id: categoryId,
      })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update product')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    setError('')
    setNewVariant('')
    onClose()
  }

  if (!isOpen) return null

  // Build category options with hierarchy indication
  const categoryOptions = categories
    .filter((c) => c.has_products)
    .map((c) => {
      const parent = categories.find((p) => p.id === c.parent_id)
      const prefix = parent ? `${parent.display_name_en || parent.name} → ` : ''
      return {
        id: c.id,
        label: `${prefix}${c.display_name_en || c.name}`,
      }
    })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />
      <div className="relative bg-card border border-border rounded-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Pencil className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Edit Product</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={handleClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto flex-1 space-y-4">
          {error && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm">
              {error}
            </div>
          )}

          {/* Display Name */}
          <div>
            <label className="text-sm text-muted mb-2 block">Display Name</label>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Product name..."
            />
            <p className="text-xs text-muted mt-1">
              Original: {product.canonical_text}
            </p>
          </div>

          {/* Category */}
          <div>
            <label className="text-sm text-muted mb-2 block">Category</label>
            <select
              value={categoryId || ''}
              onChange={(e) => setCategoryId(e.target.value || null)}
              className="w-full h-10 rounded-lg border border-border bg-card px-3 text-sm text-foreground"
            >
              <option value="">Standalone (no category)</option>
              {categoryOptions.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.label}
                </option>
              ))}
            </select>
          </div>

          {/* Variants */}
          <div>
            <label className="text-sm text-muted mb-2 block">
              Variants ({variants.length})
            </label>

            {/* Existing variants */}
            <div className="space-y-2 mb-3">
              {variants.length === 0 ? (
                <p className="text-xs text-muted italic">No variants added</p>
              ) : (
                variants.map((variant, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-2 bg-card-hover border border-border rounded-lg"
                  >
                    <span className="text-sm text-foreground">{variant}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveVariant(variant)}
                      className="h-6 w-6 p-0"
                    >
                      <X className="w-3 h-3 text-muted hover:text-destructive" />
                    </Button>
                  </div>
                ))
              )}
            </div>

            {/* Add new variant */}
            <div className="flex gap-2">
              <Input
                value={newVariant}
                onChange={(e) => setNewVariant(e.target.value)}
                placeholder="Add a variant..."
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleAddVariant()
                  }
                }}
              />
              <Button
                variant="outline"
                size="icon"
                onClick={handleAddVariant}
                disabled={!newVariant.trim()}
              >
                <Plus className="w-4 h-4" />
              </Button>
            </div>
            <p className="text-xs text-muted mt-1">
              Variants are alternative names/spellings that match this product
            </p>
          </div>

          {/* Mentions info */}
          <div className="p-3 bg-muted/10 border border-border rounded-lg">
            <div className="text-sm text-muted">
              This product has <span className="text-foreground font-medium">{product.discovered_mention_count}</span> mentions
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-4 border-t border-border">
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={loading || !displayName.trim()}>
            {loading ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      </div>
    </div>
  )
}
