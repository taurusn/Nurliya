'use client'

import { useState, useMemo } from 'react'
import { TaxonomyCategory } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Search, GitMerge, ArrowRight, X, FolderTree } from 'lucide-react'

interface MergeCategoryModalProps {
  isOpen: boolean
  onClose: () => void
  onMerge: (sourceId: string, targetId: string) => Promise<void>
  sourceCategory: TaxonomyCategory
  categories: TaxonomyCategory[]
}

export function MergeCategoryModal({
  isOpen,
  onClose,
  onMerge,
  sourceCategory,
  categories,
}: MergeCategoryModalProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedTarget, setSelectedTarget] = useState<TaxonomyCategory | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Filter out the source category, its children, and search
  const availableTargets = useMemo(() => {
    return categories.filter((c) => {
      // Exclude source itself
      if (c.id === sourceCategory.id) return false
      // Exclude children of source (can't merge parent into child)
      if (c.parent_id === sourceCategory.id) return false
      // Search filter
      if (!searchTerm) return true
      const search = searchTerm.toLowerCase()
      return (
        c.name.toLowerCase().includes(search) ||
        c.display_name_en?.toLowerCase().includes(search) ||
        c.display_name_ar?.toLowerCase().includes(search)
      )
    })
  }, [categories, sourceCategory.id, searchTerm])

  const handleMerge = async () => {
    if (!selectedTarget) return
    setLoading(true)
    setError('')
    try {
      await onMerge(sourceCategory.id, selectedTarget.id)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to merge categories')
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

  const sourceName = sourceCategory.display_name_ar || sourceCategory.display_name_en || sourceCategory.name
  const targetName = selectedTarget?.display_name_ar || selectedTarget?.display_name_en || selectedTarget?.name

  // Calculate merged result preview
  const sourceProducts = categories.filter(c => c.parent_id === sourceCategory.id).length
  const mergedMentions =
    (selectedTarget?.discovered_mention_count || 0) + (sourceCategory.discovered_mention_count || 0)

  // Build hierarchy info for display
  const getParentName = (parentId: string | null) => {
    if (!parentId) return null
    const parent = categories.find(c => c.id === parentId)
    return parent?.display_name_ar || parent?.display_name_en || parent?.name
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />
      <div className="relative bg-card border border-border rounded-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <GitMerge className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Merge Categories</h2>
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

          {/* Source category */}
          <div className="mb-4">
            <label className="text-sm text-muted mb-2 block">Merging this category:</label>
            <div className="p-3 bg-card-hover border border-border rounded-lg">
              <div className="flex items-center gap-2">
                <FolderTree className="w-4 h-4 text-muted" />
                <span className="font-medium text-foreground">{sourceName}</span>
                {sourceCategory.display_name_en && sourceCategory.display_name_ar && (
                  <span className="text-muted">({sourceCategory.display_name_en})</span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-1 text-xs text-muted">
                <span>{sourceCategory.discovered_mention_count || 0} mentions</span>
                {sourceCategory.has_products && (
                  <Badge variant="outline" className="text-xs">has products</Badge>
                )}
                {!sourceCategory.has_products && (
                  <Badge variant="default" className="text-xs">aspect</Badge>
                )}
              </div>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center my-3">
            <ArrowRight className="w-5 h-5 text-muted" />
          </div>

          {/* Target selection */}
          <div className="mb-4">
            <label className="text-sm text-muted mb-2 block">Into this category:</label>

            {/* Search */}
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <Input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search categories..."
                className="pl-9"
              />
            </div>

            {/* Category list */}
            <div className="border border-border rounded-lg max-h-48 overflow-y-auto">
              {availableTargets.length === 0 ? (
                <div className="p-4 text-center text-muted text-sm">
                  No matching categories found
                </div>
              ) : (
                availableTargets.map((category) => {
                  const name = category.display_name_ar || category.display_name_en || category.name
                  const isSelected = selectedTarget?.id === category.id
                  const parentName = getParentName(category.parent_id)
                  return (
                    <button
                      key={category.id}
                      onClick={() => setSelectedTarget(category)}
                      className={`w-full p-3 text-left border-b border-border last:border-b-0 hover:bg-card-hover transition-colors ${
                        isSelected ? 'bg-primary/10 border-primary' : ''
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">{name}</span>
                        {category.display_name_en && category.display_name_ar && (
                          <span className="text-muted text-sm">({category.display_name_en})</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted">
                        <span>{category.discovered_mention_count || 0} mentions</span>
                        {parentName && (
                          <span className="text-muted/70">in {parentName}</span>
                        )}
                        {category.has_products ? (
                          <Badge variant="outline" className="text-xs">products</Badge>
                        ) : (
                          <Badge variant="default" className="text-xs">aspect</Badge>
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
                <div className="text-xs text-muted mt-2">
                  Products and child categories from "{sourceName}" will be moved to "{targetName}".
                  "{sourceName}" will be deleted.
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
