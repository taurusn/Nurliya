'use client'

import { useState } from 'react'
import { TaxonomyCategory } from '@/lib/api'
import { ApprovalBadge } from '@/components/ApprovalBadge'
import { Button } from '@/components/ui/button'
import {
  ChevronRight,
  ChevronDown,
  Check,
  X,
  Move,
  FolderTree,
  Package,
  MessageSquare,
} from 'lucide-react'

interface CategoryTreeProps {
  categories: TaxonomyCategory[]
  selectedCategoryId: string | null
  onSelectCategory: (categoryId: string | null) => void
  onApprove: (categoryId: string) => void
  onReject: (categoryId: string) => void
  onMove: (categoryId: string) => void
  onShowMentions?: (categoryId: string, categoryName: string) => void
}

interface CategoryNodeProps {
  category: TaxonomyCategory
  children: TaxonomyCategory[]
  allCategories: TaxonomyCategory[]
  depth: number
  selectedCategoryId: string | null
  onSelectCategory: (categoryId: string | null) => void
  onApprove: (categoryId: string) => void
  onReject: (categoryId: string) => void
  onMove: (categoryId: string) => void
  onShowMentions?: (categoryId: string, categoryName: string) => void
}

function CategoryNode({
  category,
  children,
  allCategories,
  depth,
  selectedCategoryId,
  onSelectCategory,
  onApprove,
  onReject,
  onMove,
  onShowMentions,
}: CategoryNodeProps) {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = children.length > 0
  const isSelected = selectedCategoryId === category.id

  return (
    <div>
      <div
        className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-colors ${
          isSelected ? 'bg-primary/20' : 'hover:bg-card-hover'
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onSelectCategory(category.id)}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(!expanded)
            }}
            className="p-0.5 hover:bg-card rounded"
          >
            {expanded ? (
              <ChevronDown className="w-4 h-4 text-muted" />
            ) : (
              <ChevronRight className="w-4 h-4 text-muted" />
            )}
          </button>
        ) : (
          <span className="w-5" />
        )}

        <div className="flex-1 flex items-center gap-2 min-w-0">
          {category.has_products ? (
            <Package className="w-4 h-4 text-muted flex-shrink-0" />
          ) : (
            <FolderTree className="w-4 h-4 text-muted flex-shrink-0" />
          )}
          <span className="text-sm text-foreground truncate">
            {category.display_name_en || category.name}
          </span>
          <ApprovalBadge
            isApproved={category.is_approved}
            rejectionReason={category.rejection_reason}
          />
          {category.discovered_mention_count > 0 && (
            <span className="text-xs text-muted">({category.discovered_mention_count})</span>
          )}
        </div>

        {isSelected && (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            {!category.is_approved && !category.rejection_reason && (
              <>
                <Button size="sm" variant="ghost" onClick={() => onApprove(category.id)}>
                  <Check className="w-4 h-4 text-success" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onReject(category.id)}>
                  <X className="w-4 h-4 text-destructive" />
                </Button>
              </>
            )}
            <Button size="sm" variant="ghost" onClick={() => onMove(category.id)}>
              <Move className="w-4 h-4 text-muted" />
            </Button>
            {onShowMentions && category.discovered_mention_count > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onShowMentions(category.id, category.display_name_en || category.name)}
              >
                <MessageSquare className="w-4 h-4 text-primary" />
              </Button>
            )}
          </div>
        )}
      </div>

      {expanded && hasChildren && (
        <div>
          {children.map((child) => (
            <CategoryNode
              key={child.id}
              category={child}
              children={allCategories.filter((c) => c.parent_id === child.id)}
              allCategories={allCategories}
              depth={depth + 1}
              selectedCategoryId={selectedCategoryId}
              onSelectCategory={onSelectCategory}
              onApprove={onApprove}
              onReject={onReject}
              onMove={onMove}
              onShowMentions={onShowMentions}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function CategoryTree({
  categories,
  selectedCategoryId,
  onSelectCategory,
  onApprove,
  onReject,
  onMove,
  onShowMentions,
}: CategoryTreeProps) {
  const mainCategories = categories.filter((c) => !c.parent_id)

  return (
    <div className="space-y-1">
      {/* All Products option */}
      <div
        className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-colors ${
          selectedCategoryId === null ? 'bg-primary/20' : 'hover:bg-card-hover'
        }`}
        onClick={() => onSelectCategory(null)}
      >
        <span className="w-5" />
        <Package className="w-4 h-4 text-muted" />
        <span className="text-sm text-foreground font-medium">All Products</span>
      </div>

      {/* Category tree */}
      {mainCategories.map((category) => (
        <CategoryNode
          key={category.id}
          category={category}
          children={categories.filter((c) => c.parent_id === category.id)}
          allCategories={categories}
          depth={0}
          selectedCategoryId={selectedCategoryId}
          onSelectCategory={onSelectCategory}
          onApprove={onApprove}
          onReject={onReject}
          onMove={onMove}
          onShowMentions={onShowMentions}
        />
      ))}
    </div>
  )
}
