'use client'

import { useState, useEffect } from 'react'
import { TaxonomyCategory } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { X, FolderEdit } from 'lucide-react'

interface EditCategoryModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (categoryId: string, updates: {
    display_name_en?: string
    display_name_ar?: string
    parent_id?: string | null
  }) => Promise<void>
  category: TaxonomyCategory
  categories: TaxonomyCategory[]
}

export function EditCategoryModal({
  isOpen,
  onClose,
  onSave,
  category,
  categories,
}: EditCategoryModalProps) {
  const [displayNameEn, setDisplayNameEn] = useState('')
  const [displayNameAr, setDisplayNameAr] = useState('')
  const [parentId, setParentId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Reset form when category changes
  useEffect(() => {
    if (category) {
      setDisplayNameEn(category.display_name_en || category.name)
      setDisplayNameAr(category.display_name_ar || '')
      setParentId(category.parent_id)
    }
  }, [category])

  const handleSave = async () => {
    setLoading(true)
    setError('')
    try {
      await onSave(category.id, {
        display_name_en: displayNameEn,
        display_name_ar: displayNameAr,
        parent_id: parentId,
      })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update category')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    setError('')
    onClose()
  }

  if (!isOpen) return null

  // Filter out the current category and its descendants for parent selection
  const getDescendantIds = (catId: string): string[] => {
    const children = categories.filter((c) => c.parent_id === catId)
    return [catId, ...children.flatMap((c) => getDescendantIds(c.id))]
  }
  const excludeIds = getDescendantIds(category.id)

  const availableParents = categories.filter(
    (c) => !excludeIds.includes(c.id) && !c.has_products
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />
      <div className="relative bg-card border border-border rounded-xl w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <FolderEdit className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Edit Category</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={handleClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {error && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm">
              {error}
            </div>
          )}

          {/* Internal Name (read-only) */}
          <div>
            <label className="text-sm text-muted mb-2 block">Internal Name</label>
            <div className="h-10 px-3 flex items-center rounded-lg border border-border bg-muted/20 text-sm text-muted">
              {category.name}
            </div>
          </div>

          {/* Display Name EN */}
          <div>
            <label className="text-sm text-muted mb-2 block">Display Name (English)</label>
            <Input
              value={displayNameEn}
              onChange={(e) => setDisplayNameEn(e.target.value)}
              placeholder="Category name in English..."
            />
          </div>

          {/* Display Name AR */}
          <div>
            <label className="text-sm text-muted mb-2 block">Display Name (Arabic)</label>
            <Input
              value={displayNameAr}
              onChange={(e) => setDisplayNameAr(e.target.value)}
              placeholder="اسم الفئة بالعربية..."
              dir="rtl"
            />
          </div>

          {/* Parent Category */}
          <div>
            <label className="text-sm text-muted mb-2 block">Parent Category</label>
            <select
              value={parentId || ''}
              onChange={(e) => setParentId(e.target.value || null)}
              className="w-full h-10 rounded-lg border border-border bg-card px-3 text-sm text-foreground"
            >
              <option value="">None (root level)</option>
              {availableParents.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.display_name_en || cat.name}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted mt-1">
              Only categories without products can be parents
            </p>
          </div>

          {/* Category info */}
          <div className="p-3 bg-muted/10 border border-border rounded-lg space-y-1">
            <div className="text-sm text-muted">
              {category.has_products ? 'Contains products' : 'Container category (no products)'}
            </div>
            <div className="text-sm text-muted">
              <span className="text-foreground font-medium">{category.discovered_mention_count}</span> mentions
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-4 border-t border-border">
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={loading || !displayNameEn.trim()}>
            {loading ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      </div>
    </div>
  )
}
