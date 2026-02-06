'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { X, FolderTree } from 'lucide-react'
import { TaxonomyCategory } from '@/lib/api'

interface MoveModalProps {
  isOpen: boolean
  onClose: () => void
  onMove: (targetId: string | null) => Promise<void>
  itemName: string
  itemType: 'category' | 'product'
  categories: TaxonomyCategory[]
  currentCategoryId?: string | null
}

export function MoveModal({
  isOpen,
  onClose,
  onMove,
  itemName,
  itemType,
  categories,
  currentCategoryId,
}: MoveModalProps) {
  const [selectedId, setSelectedId] = useState<string | null>(currentCategoryId || null)
  const [loading, setLoading] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async () => {
    setLoading(true)
    try {
      await onMove(selectedId)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  // Build hierarchy for display
  const mainCategories = categories.filter((c) => !c.parent_id)
  const getChildren = (parentId: string) => categories.filter((c) => c.parent_id === parentId)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-md mx-4 animate-fade-in max-h-[80vh] overflow-hidden flex flex-col">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-muted hover:text-foreground"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
            <FolderTree className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">Move {itemType}</h2>
            <p className="text-sm text-muted">{itemName}</p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto space-y-1 mb-4">
          {/* For products: standalone option. For categories: root level option */}
          <button
            onClick={() => setSelectedId(null)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm ${
              selectedId === null
                ? 'bg-primary/20 text-primary'
                : 'hover:bg-card-hover text-foreground'
            }`}
          >
            {itemType === 'product' ? 'Standalone (no category)' : 'Root level (no parent)'}
          </button>

          {mainCategories.map((cat) => (
            <div key={cat.id}>
              <button
                onClick={() => setSelectedId(cat.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm ${
                  selectedId === cat.id
                    ? 'bg-primary/20 text-primary'
                    : 'hover:bg-card-hover text-foreground'
                }`}
              >
                {cat.display_name_en || cat.name}
              </button>
              {getChildren(cat.id).map((child) => (
                <button
                  key={child.id}
                  onClick={() => setSelectedId(child.id)}
                  className={`w-full text-left px-3 py-2 pl-8 rounded-lg text-sm ${
                    selectedId === child.id
                      ? 'bg-primary/20 text-primary'
                      : 'hover:bg-card-hover text-foreground'
                  }`}
                >
                  {child.display_name_en || child.name}
                </button>
              ))}
            </div>
          ))}
        </div>

        <div className="flex gap-3 justify-end pt-4 border-t border-border">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? 'Moving...' : 'Move'}
          </Button>
        </div>
      </div>
    </div>
  )
}
