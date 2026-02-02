'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { X, FolderPlus } from 'lucide-react'
import { TaxonomyCategory } from '@/lib/api'

interface AddCategoryModalProps {
  isOpen: boolean
  onClose: () => void
  onAdd: (
    name: string,
    displayNameEn: string,
    displayNameAr: string,
    parentId: string | null,
    hasProducts: boolean
  ) => Promise<void>
  categories: TaxonomyCategory[]
}

export function AddCategoryModal({ isOpen, onClose, onAdd, categories }: AddCategoryModalProps) {
  const [name, setName] = useState('')
  const [displayNameEn, setDisplayNameEn] = useState('')
  const [displayNameAr, setDisplayNameAr] = useState('')
  const [parentId, setParentId] = useState<string | null>(null)
  const [hasProducts, setHasProducts] = useState(true)
  const [loading, setLoading] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !displayNameEn.trim()) return

    setLoading(true)
    try {
      await onAdd(name, displayNameEn, displayNameAr, parentId, hasProducts)
      setName('')
      setDisplayNameEn('')
      setDisplayNameAr('')
      setParentId(null)
      setHasProducts(true)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  const mainCategories = categories.filter((c) => !c.parent_id)

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
            <FolderPlus className="w-5 h-5 text-primary" />
          </div>
          <h2 className="text-lg font-semibold text-foreground">Add Category</h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Internal name
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="hot_coffee"
              required
            />
            <p className="text-xs text-muted mt-1">Lowercase, underscores for spaces</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Display name (English)
            </label>
            <Input
              value={displayNameEn}
              onChange={(e) => setDisplayNameEn(e.target.value)}
              placeholder="Hot Coffee"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Display name (Arabic)
            </label>
            <Input
              value={displayNameAr}
              onChange={(e) => setDisplayNameAr(e.target.value)}
              placeholder="قهوة ساخنة"
              dir="rtl"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Parent category
            </label>
            <select
              value={parentId || ''}
              onChange={(e) => setParentId(e.target.value || null)}
              className="w-full h-10 rounded-lg border border-border bg-card px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">None (main category)</option>
              {mainCategories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.display_name_en || cat.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="hasProducts"
              checked={hasProducts}
              onChange={(e) => setHasProducts(e.target.checked)}
              className="w-4 h-4 rounded border-border bg-card text-primary focus:ring-primary"
            />
            <label htmlFor="hasProducts" className="text-sm text-foreground">
              Contains products
            </label>
          </div>

          <div className="flex gap-3 justify-end pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading || !name.trim() || !displayNameEn.trim()}>
              {loading ? 'Adding...' : 'Add Category'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
