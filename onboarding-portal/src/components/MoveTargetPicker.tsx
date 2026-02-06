'use client'

import { useState, useMemo } from 'react'
import { TaxonomyCategory, TaxonomyProduct } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Search, X, Package, FolderTree, ArrowRight } from 'lucide-react'

interface MoveTargetPickerProps {
  isOpen: boolean
  onClose: () => void
  onSelect: (targetType: 'product' | 'category', targetId: string, targetName: string) => void
  categories: TaxonomyCategory[]
  products: TaxonomyProduct[]
  mentionCount: number
  currentEntityId?: string // Exclude this from the list
  currentEntityType?: 'product' | 'category'
}

export function MoveTargetPicker({
  isOpen,
  onClose,
  onSelect,
  categories,
  products,
  mentionCount,
  currentEntityId,
  currentEntityType,
}: MoveTargetPickerProps) {
  const [activeTab, setActiveTab] = useState<'products' | 'categories'>('products')
  const [searchTerm, setSearchTerm] = useState('')

  // Filter products
  const filteredProducts = useMemo(() => {
    return products.filter((p) => {
      // Exclude current entity if it's a product
      if (currentEntityType === 'product' && p.id === currentEntityId) return false
      if (!searchTerm) return true
      const search = searchTerm.toLowerCase()
      return (
        p.display_name?.toLowerCase().includes(search) ||
        p.canonical_text.toLowerCase().includes(search)
      )
    })
  }, [products, searchTerm, currentEntityId, currentEntityType])

  // Filter categories
  const filteredCategories = useMemo(() => {
    return categories.filter((c) => {
      // Exclude current entity if it's a category
      if (currentEntityType === 'category' && c.id === currentEntityId) return false
      if (!searchTerm) return true
      const search = searchTerm.toLowerCase()
      return (
        c.name.toLowerCase().includes(search) ||
        c.display_name_en?.toLowerCase().includes(search) ||
        c.display_name_ar?.toLowerCase().includes(search)
      )
    })
  }, [categories, searchTerm, currentEntityId, currentEntityType])

  // Build category hierarchy
  const mainCategories = filteredCategories.filter((c) => !c.parent_id)
  const getChildren = (parentId: string) => filteredCategories.filter((c) => c.parent_id === parentId)

  // Get category name for products
  const getCategoryName = (categoryId: string | null) => {
    if (!categoryId) return null
    const cat = categories.find((c) => c.id === categoryId)
    return cat?.display_name_en || cat?.name
  }

  const handleClose = () => {
    setSearchTerm('')
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />
      <div className="relative bg-card border border-border rounded-xl w-full max-w-lg mx-4 max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <ArrowRight className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Move {mentionCount} Mentions</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={handleClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border">
          <button
            onClick={() => setActiveTab('products')}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === 'products'
                ? 'text-primary border-b-2 border-primary bg-primary/5'
                : 'text-muted hover:text-foreground hover:bg-card-hover'
            }`}
          >
            <Package className="w-4 h-4" />
            Products ({filteredProducts.length})
          </button>
          <button
            onClick={() => setActiveTab('categories')}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === 'categories'
                ? 'text-primary border-b-2 border-primary bg-primary/5'
                : 'text-muted hover:text-foreground hover:bg-card-hover'
            }`}
          >
            <FolderTree className="w-4 h-4" />
            Categories ({filteredCategories.length})
          </button>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-border">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
            <Input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={`Search ${activeTab}...`}
              className="pl-9"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-2">
          {activeTab === 'products' ? (
            <div className="space-y-1">
              {filteredProducts.length === 0 ? (
                <div className="p-4 text-center text-muted text-sm">
                  No products found
                </div>
              ) : (
                filteredProducts.map((product) => {
                  const name = product.display_name || product.canonical_text
                  const categoryName = getCategoryName(product.assigned_category_id)
                  return (
                    <button
                      key={product.id}
                      onClick={() => onSelect('product', product.id, name)}
                      className="w-full p-3 text-left rounded-lg hover:bg-card-hover transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <Package className="w-4 h-4 text-muted flex-shrink-0" />
                        <span className="font-medium text-foreground">{name}</span>
                        {product.is_approved && (
                          <Badge variant="success" className="text-xs">approved</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted ml-6">
                        <span>{product.discovered_mention_count || 0} mentions</span>
                        {categoryName && (
                          <span>in {categoryName}</span>
                        )}
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          ) : (
            <div className="space-y-1">
              {filteredCategories.length === 0 ? (
                <div className="p-4 text-center text-muted text-sm">
                  No categories found
                </div>
              ) : (
                mainCategories.map((category) => {
                  const children = getChildren(category.id)
                  return (
                    <div key={category.id}>
                      <button
                        onClick={() => onSelect('category', category.id, category.display_name_en || category.name)}
                        className="w-full p-3 text-left rounded-lg hover:bg-card-hover transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <FolderTree className="w-4 h-4 text-muted flex-shrink-0" />
                          <span className="font-medium text-foreground">
                            {category.display_name_en || category.name}
                          </span>
                          {category.display_name_ar && (
                            <span className="text-muted text-sm">({category.display_name_ar})</span>
                          )}
                          {category.is_approved && (
                            <Badge variant="success" className="text-xs">approved</Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-xs text-muted ml-6">
                          <span>{category.discovered_mention_count || 0} mentions</span>
                          {category.has_products ? (
                            <Badge variant="outline" className="text-xs">products</Badge>
                          ) : (
                            <Badge variant="default" className="text-xs">aspect</Badge>
                          )}
                        </div>
                      </button>
                      {/* Child categories */}
                      {children.map((child) => (
                        <button
                          key={child.id}
                          onClick={() => onSelect('category', child.id, child.display_name_en || child.name)}
                          className="w-full p-3 pl-8 text-left rounded-lg hover:bg-card-hover transition-colors"
                        >
                          <div className="flex items-center gap-2">
                            <FolderTree className="w-4 h-4 text-muted flex-shrink-0" />
                            <span className="font-medium text-foreground">
                              {child.display_name_en || child.name}
                            </span>
                            {child.display_name_ar && (
                              <span className="text-muted text-sm">({child.display_name_ar})</span>
                            )}
                            {child.is_approved && (
                              <Badge variant="success" className="text-xs">approved</Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-1 text-xs text-muted ml-6">
                            <span>{child.discovered_mention_count || 0} mentions</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  )
                })
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border">
          <p className="text-xs text-muted text-center">
            Select a {activeTab === 'products' ? 'product' : 'category'} to move the mentions to
          </p>
        </div>
      </div>
    </div>
  )
}
