'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { X, Package, Plus, Trash2 } from 'lucide-react'
import { TaxonomyCategory } from '@/lib/api'

interface AddProductModalProps {
  isOpen: boolean
  onClose: () => void
  onAdd: (displayName: string, categoryId: string | null, variants: string[]) => Promise<void>
  categories: TaxonomyCategory[]
}

export function AddProductModal({ isOpen, onClose, onAdd, categories }: AddProductModalProps) {
  const [displayName, setDisplayName] = useState('')
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [variants, setVariants] = useState<string[]>([])
  const [newVariant, setNewVariant] = useState('')
  const [loading, setLoading] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!displayName.trim()) return

    setLoading(true)
    try {
      await onAdd(displayName, categoryId, variants)
      setDisplayName('')
      setCategoryId(null)
      setVariants([])
      setNewVariant('')
      onClose()
    } finally {
      setLoading(false)
    }
  }

  const addVariant = () => {
    if (newVariant.trim() && !variants.includes(newVariant.trim())) {
      setVariants([...variants, newVariant.trim()])
      setNewVariant('')
    }
  }

  const removeVariant = (index: number) => {
    setVariants(variants.filter((_, i) => i !== index))
  }

  // Build flat list with hierarchy indication
  const categoryOptions: { id: string; label: string }[] = []
  const mainCategories = categories.filter((c) => !c.parent_id && c.has_products)
  mainCategories.forEach((main) => {
    categoryOptions.push({ id: main.id, label: main.display_name_ar || main.display_name_en || main.name })
    const children = categories.filter((c) => c.parent_id === main.id && c.has_products)
    children.forEach((child) => {
      categoryOptions.push({ id: child.id, label: `  ${child.display_name_ar || child.display_name_en || child.name}` })
    })
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-md mx-4 animate-fade-in">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-muted hover:text-foreground"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
            <Package className="w-5 h-5 text-primary" />
          </div>
          <h2 className="text-lg font-semibold text-foreground">Add Product</h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Product name
            </label>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Spanish Latte"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Category
            </label>
            <select
              value={categoryId || ''}
              onChange={(e) => setCategoryId(e.target.value || null)}
              className="w-full h-10 rounded-lg border border-border bg-card px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">Standalone (no category)</option>
              {categoryOptions.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Variants (alternative names)
            </label>
            <div className="flex gap-2 mb-2">
              <Input
                value={newVariant}
                onChange={(e) => setNewVariant(e.target.value)}
                placeholder="spanish latté"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addVariant()
                  }
                }}
              />
              <Button type="button" variant="outline" size="icon" onClick={addVariant}>
                <Plus className="w-4 h-4" />
              </Button>
            </div>
            {variants.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {variants.map((v, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-card-hover rounded text-sm"
                  >
                    {v}
                    <button
                      type="button"
                      onClick={() => removeVariant(i)}
                      className="text-muted hover:text-destructive"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="flex gap-3 justify-end pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading || !displayName.trim()}>
              {loading ? 'Adding...' : 'Add Product'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
