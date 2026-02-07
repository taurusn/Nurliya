'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { AuthGuard } from '@/components/AuthGuard'
import {
  fetchTaxonomyDetail,
  approveCategory,
  rejectCategory,
  moveCategory,
  renameCategory,
  approveProduct,
  rejectProduct,
  moveProduct,
  addProductVariant,
  updateProduct,
  mergeProducts,
  mergeCategories,
  deleteProduct,
  deleteCategory,
  createCategory,
  createProduct,
  publishTaxonomy,
  importTaxonomy,
  TaxonomyDetail,
  TaxonomyCategory,
  TaxonomyProduct,
  TaxonomyImportData,
} from '@/lib/api'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { CategoryTree } from '@/components/CategoryTree'
import { ProductList } from '@/components/ProductList'
import { RejectModal } from '@/components/RejectModal'
import { MoveModal } from '@/components/MoveModal'
import { AddCategoryModal } from '@/components/AddCategoryModal'
import { AddProductModal } from '@/components/AddProductModal'
import { MergeProductModal } from '@/components/MergeProductModal'
import { MergeCategoryModal } from '@/components/MergeCategoryModal'
import { EditProductModal } from '@/components/EditProductModal'
import { EditCategoryModal } from '@/components/EditCategoryModal'
import { ImportModal } from '@/components/ImportModal'
import {
  ArrowLeft,
  Check,
  Package,
  FolderTree,
  Send,
  Plus,
  RefreshCw,
  AlertCircle,
  MessageSquare,
  Upload,
} from 'lucide-react'
import { MentionPanel } from '@/components/MentionPanel'
import { OrphanPanel } from '@/components/OrphanPanel'
import { MenuImagesPanel } from '@/components/MenuImagesPanel'

function TaxonomyEditor() {
  const params = useParams()
  const router = useRouter()
  const taxonomyId = params.taxonomyId as string

  const [taxonomy, setTaxonomy] = useState<TaxonomyDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [publishing, setPublishing] = useState(false)
  const [approvingAll, setApprovingAll] = useState(false)

  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null)

  // Modals
  const [rejectModal, setRejectModal] = useState<{
    type: 'category' | 'product'
    id: string
    name: string
  } | null>(null)
  const [moveModal, setMoveModal] = useState<{
    type: 'category' | 'product'
    id: string
    name: string
    currentCategoryId?: string | null
  } | null>(null)
  const [variantModal, setVariantModal] = useState<{ id: string; name: string } | null>(null)
  const [showAddCategory, setShowAddCategory] = useState(false)
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [mentionPanel, setMentionPanel] = useState<{
    type: 'product' | 'category'
    id: string
    name: string
  } | null>(null)

  // New editor modals
  const [mergeModal, setMergeModal] = useState<TaxonomyProduct | null>(null)
  const [mergeCategoryModal, setMergeCategoryModal] = useState<TaxonomyCategory | null>(null)
  const [editProductModal, setEditProductModal] = useState<TaxonomyProduct | null>(null)
  const [editCategoryModal, setEditCategoryModal] = useState<TaxonomyCategory | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<{
    type: 'product' | 'category'
    id: string
    name: string
  } | null>(null)

  const loadTaxonomy = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchTaxonomyDetail(taxonomyId)
      setTaxonomy(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTaxonomy()
  }, [taxonomyId])

  // Category actions
  const handleApproveCategory = async (categoryId: string) => {
    try {
      await approveCategory(categoryId)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve')
    }
  }

  const handleRejectCategory = async (reason: string) => {
    if (!rejectModal) return
    try {
      await rejectCategory(rejectModal.id, reason)
      setRejectModal(null)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reject')
    }
  }

  const handleMoveCategory = async (parentId: string | null) => {
    if (!moveModal) return
    try {
      await moveCategory(moveModal.id, parentId)
      setMoveModal(null)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to move')
    }
  }

  // Product actions
  const handleApproveProduct = async (productId: string) => {
    try {
      await approveProduct(productId)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve')
    }
  }

  const handleRejectProduct = async (reason: string) => {
    if (!rejectModal) return
    try {
      await rejectProduct(rejectModal.id, reason)
      setRejectModal(null)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reject')
    }
  }

  const handleMoveProduct = async (categoryId: string | null) => {
    if (!moveModal) return
    try {
      await moveProduct(moveModal.id, categoryId)
      setMoveModal(null)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to move')
    }
  }

  const handleAddVariant = async (variant: string) => {
    if (!variantModal) return
    try {
      await addProductVariant(variantModal.id, variant)
      setVariantModal(null)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add variant')
    }
  }

  // Product editor actions
  const handleMergeProducts = async (sourceId: string, targetId: string) => {
    try {
      await mergeProducts(sourceId, targetId)
      setMergeModal(null)
      loadTaxonomy()
    } catch (err) {
      throw err // Let the modal handle the error
    }
  }

  // Category merge
  const handleMergeCategories = async (sourceId: string, targetId: string) => {
    try {
      await mergeCategories(sourceId, targetId)
      setMergeCategoryModal(null)
      loadTaxonomy()
    } catch (err) {
      throw err // Let the modal handle the error
    }
  }

  const handleUpdateProduct = async (
    productId: string,
    updates: { display_name?: string; variants?: string[]; category_id?: string | null }
  ) => {
    try {
      await updateProduct(productId, updates)
      setEditProductModal(null)
      loadTaxonomy()
    } catch (err) {
      throw err
    }
  }

  const handleDeleteProduct = async () => {
    if (!deleteConfirm || deleteConfirm.type !== 'product') return
    try {
      await deleteProduct(deleteConfirm.id)
      setDeleteConfirm(null)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete product')
    }
  }

  // Category editor actions
  const handleUpdateCategory = async (
    categoryId: string,
    updates: { display_name_en?: string; display_name_ar?: string; parent_id?: string | null }
  ) => {
    try {
      // Use rename for display names
      if (updates.display_name_en || updates.display_name_ar) {
        await renameCategory(categoryId, updates.display_name_en, updates.display_name_ar)
      }
      // Use move for parent change
      if (updates.parent_id !== undefined) {
        await moveCategory(categoryId, updates.parent_id)
      }
      setEditCategoryModal(null)
      loadTaxonomy()
    } catch (err) {
      throw err
    }
  }

  const handleDeleteCategory = async () => {
    if (!deleteConfirm || deleteConfirm.type !== 'category') return
    try {
      await deleteCategory(deleteConfirm.id)
      setDeleteConfirm(null)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete category')
    }
  }

  // Create actions
  const handleCreateCategory = async (
    name: string,
    displayNameEn: string,
    displayNameAr: string,
    parentId: string | null,
    hasProducts: boolean
  ) => {
    try {
      await createCategory(taxonomyId, name, displayNameEn, displayNameAr, parentId || undefined, hasProducts)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create category')
    }
  }

  const handleCreateProduct = async (
    displayName: string,
    categoryId: string | null,
    variants: string[]
  ) => {
    try {
      await createProduct(taxonomyId, displayName, categoryId || undefined, variants)
      loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create product')
    }
  }

  // Approve All (skip rejected items)
  const handleApproveAll = async () => {
    if (!taxonomy) return
    setApprovingAll(true)
    try {
      const unapprovedCats = taxonomy.categories.filter(
        (c) => !c.is_approved && !c.rejection_reason
      )
      const unapprovedProds = taxonomy.products.filter(
        (p) => !p.is_approved && !p.rejection_reason
      )

      for (const cat of unapprovedCats) {
        await approveCategory(cat.id)
      }
      for (const prod of unapprovedProds) {
        await approveProduct(prod.id)
      }

      await loadTaxonomy()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve all')
    } finally {
      setApprovingAll(false)
    }
  }

  // Publish
  const handlePublish = async () => {
    if (!taxonomy) return
    setPublishing(true)
    try {
      await publishTaxonomy(taxonomyId)
      router.push('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to publish')
    } finally {
      setPublishing(false)
    }
  }

  // Import
  const handleImport = async (data: TaxonomyImportData) => {
    try {
      await importTaxonomy(taxonomyId, data)
      loadTaxonomy()
    } catch (err) {
      throw err // Let the modal handle the error
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!taxonomy) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="pt-6 text-center">
            <AlertCircle className="w-12 h-12 text-destructive mx-auto mb-4" />
            <p className="text-foreground mb-4">Taxonomy not found</p>
            <Link href="/">
              <Button>Back to list</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  const approvedCategories = taxonomy.categories.filter((c) => c.is_approved).length
  const approvedProducts = taxonomy.products.filter((p) => p.is_approved).length
  const unapprovedCount =
    taxonomy.categories.filter((c) => !c.is_approved && !c.rejection_reason).length +
    taxonomy.products.filter((p) => !p.is_approved && !p.rejection_reason).length
  const canPublish =
    taxonomy.status !== 'active' && (approvedCategories > 0 || approvedProducts > 0)

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/">
                <Button variant="ghost" size="icon">
                  <ArrowLeft className="w-5 h-5" />
                </Button>
              </Link>
              <div>
                <h1 className="text-lg font-semibold text-foreground">{taxonomy.place_name}</h1>
                <div className="flex items-center gap-2 text-sm text-muted">
                  <Badge variant={taxonomy.status === 'active' ? 'success' : 'warning'}>
                    {taxonomy.status}
                  </Badge>
                  {taxonomy.place_category && (
                    <Badge variant="outline">{taxonomy.place_category}</Badge>
                  )}
                  <span>{taxonomy.reviews_sampled} reviews sampled</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={loadTaxonomy}>
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh
              </Button>
              {taxonomy.status !== 'active' && (
                <Button variant="outline" size="sm" onClick={() => setShowImportModal(true)}>
                  <Upload className="w-4 h-4 mr-2" />
                  Import
                </Button>
              )}
              {taxonomy.status !== 'active' && unapprovedCount > 0 && (
                <Button variant="outline" size="sm" onClick={handleApproveAll} disabled={approvingAll}>
                  <Check className="w-4 h-4 mr-2" />
                  {approvingAll ? 'Approving...' : `Approve All (${unapprovedCount})`}
                </Button>
              )}
              {canPublish && (
                <Button onClick={handlePublish} disabled={publishing}>
                  <Send className="w-4 h-4 mr-2" />
                  {publishing ? 'Publishing...' : 'Publish'}
                </Button>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Progress bar */}
      <div className="border-b border-border bg-card">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <FolderTree className="w-4 h-4 text-muted" />
              <span className="text-muted">Categories:</span>
              <span className="text-foreground font-medium">
                {approvedCategories}/{taxonomy.categories.length} approved
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Package className="w-4 h-4 text-muted" />
              <span className="text-muted">Products:</span>
              <span className="text-foreground font-medium">
                {approvedProducts}/{taxonomy.products.length} approved
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {error}
            <button onClick={() => setError('')} className="ml-auto text-sm underline">
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Categories panel */}
          <Card className="lg:col-span-2">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">
                <FolderTree className="w-4 h-4 inline mr-2" />
                Categories
              </CardTitle>
              <Button size="sm" variant="outline" onClick={() => setShowAddCategory(true)}>
                <Plus className="w-4 h-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <CategoryTree
                categories={taxonomy.categories}
                selectedCategoryId={selectedCategoryId}
                onSelectCategory={setSelectedCategoryId}
                onApprove={handleApproveCategory}
                onReject={(id) => {
                  const cat = taxonomy.categories.find((c) => c.id === id)
                  setRejectModal({
                    type: 'category',
                    id,
                    name: cat?.display_name_ar || cat?.display_name_en || cat?.name || 'Category',
                  })
                }}
                onMove={(id) => {
                  const cat = taxonomy.categories.find((c) => c.id === id)
                  setMoveModal({
                    type: 'category',
                    id,
                    name: cat?.display_name_ar || cat?.display_name_en || cat?.name || 'Category',
                    currentCategoryId: cat?.parent_id,
                  })
                }}
                onShowMentions={(id, name) => {
                  setMentionPanel({ type: 'category', id, name })
                }}
                onEdit={(id) => {
                  const cat = taxonomy.categories.find((c) => c.id === id)
                  if (cat) setEditCategoryModal(cat)
                }}
                onDelete={(id) => {
                  const cat = taxonomy.categories.find((c) => c.id === id)
                  setDeleteConfirm({
                    type: 'category',
                    id,
                    name: cat?.display_name_ar || cat?.display_name_en || cat?.name || 'Category',
                  })
                }}
                onMerge={(id) => {
                  const cat = taxonomy.categories.find((c) => c.id === id)
                  if (cat) setMergeCategoryModal(cat)
                }}
              />
            </CardContent>
          </Card>

          {/* Products panel */}
          <Card className="lg:col-span-3">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">
                <Package className="w-4 h-4 inline mr-2" />
                Products
                {selectedCategoryId && (
                  <span className="font-normal text-muted ml-2">
                    in{' '}
                    {taxonomy.categories.find((c) => c.id === selectedCategoryId)?.display_name_ar ||
                      taxonomy.categories.find((c) => c.id === selectedCategoryId)?.display_name_en ||
                      'selected category'}
                  </span>
                )}
              </CardTitle>
              <Button size="sm" variant="outline" onClick={() => setShowAddProduct(true)}>
                <Plus className="w-4 h-4 mr-1" />
                Add
              </Button>
            </CardHeader>
            <CardContent>
              <ProductList
                products={taxonomy.products}
                categories={taxonomy.categories}
                selectedCategoryId={selectedCategoryId}
                onApprove={handleApproveProduct}
                onReject={(id) => {
                  const prod = taxonomy.products.find((p) => p.id === id)
                  setRejectModal({
                    type: 'product',
                    id,
                    name: prod?.display_name || prod?.canonical_text || 'Product',
                  })
                }}
                onMove={(id) => {
                  const prod = taxonomy.products.find((p) => p.id === id)
                  setMoveModal({
                    type: 'product',
                    id,
                    name: prod?.display_name || prod?.canonical_text || 'Product',
                    currentCategoryId: prod?.assigned_category_id,
                  })
                }}
                onAddVariant={(id) => {
                  const prod = taxonomy.products.find((p) => p.id === id)
                  setVariantModal({
                    id,
                    name: prod?.display_name || prod?.canonical_text || 'Product',
                  })
                }}
                onShowMentions={(id, name) => {
                  setMentionPanel({ type: 'product', id, name })
                }}
                onMerge={(id) => {
                  const prod = taxonomy.products.find((p) => p.id === id)
                  if (prod) setMergeModal(prod)
                }}
                onEdit={(id) => {
                  const prod = taxonomy.products.find((p) => p.id === id)
                  if (prod) setEditProductModal(prod)
                }}
                onDelete={(id) => {
                  const prod = taxonomy.products.find((p) => p.id === id)
                  setDeleteConfirm({
                    type: 'product',
                    id,
                    name: prod?.display_name || prod?.canonical_text || 'Product',
                  })
                }}
              />
            </CardContent>
          </Card>
        </div>

        {/* Menu Images Panel */}
        <div className="mt-6">
          <MenuImagesPanel taxonomyId={taxonomyId} />
        </div>

        {/* Orphan Mentions Panel */}
        <div className="mt-6">
          <OrphanPanel
            taxonomyId={taxonomyId}
            categories={taxonomy.categories}
            products={taxonomy.products}
            onMentionsMoved={loadTaxonomy}
          />
        </div>
      </main>

      {/* Mention Panel Modal */}
      {mentionPanel && (
        <MentionPanel
          type={mentionPanel.type}
          itemId={mentionPanel.id}
          itemName={mentionPanel.name}
          onClose={() => setMentionPanel(null)}
          categories={taxonomy.categories}
          products={taxonomy.products}
          onMentionsMoved={loadTaxonomy}
        />
      )}

      {/* Modals */}
      <RejectModal
        isOpen={!!rejectModal}
        onClose={() => setRejectModal(null)}
        onReject={rejectModal?.type === 'category' ? handleRejectCategory : handleRejectProduct}
        itemName={rejectModal?.name || ''}
        itemType={rejectModal?.type || 'category'}
      />

      <MoveModal
        isOpen={!!moveModal}
        onClose={() => setMoveModal(null)}
        onMove={moveModal?.type === 'category' ? handleMoveCategory : handleMoveProduct}
        itemName={moveModal?.name || ''}
        itemType={moveModal?.type || 'category'}
        categories={taxonomy.categories}
        currentCategoryId={moveModal?.currentCategoryId}
      />

      {variantModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setVariantModal(null)} />
          <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-md mx-4">
            <h2 className="text-lg font-semibold mb-4">Add variant to {variantModal.name}</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const form = e.target as HTMLFormElement
                const input = form.elements.namedItem('variant') as HTMLInputElement
                if (input.value.trim()) {
                  handleAddVariant(input.value.trim())
                }
              }}
            >
              <input
                name="variant"
                className="w-full h-10 rounded-lg border border-border bg-card px-4 text-sm text-foreground mb-4"
                placeholder="Alternative spelling..."
                autoFocus
              />
              <div className="flex gap-3 justify-end">
                <Button type="button" variant="outline" onClick={() => setVariantModal(null)}>
                  Cancel
                </Button>
                <Button type="submit">Add</Button>
              </div>
            </form>
          </div>
        </div>
      )}

      <AddCategoryModal
        isOpen={showAddCategory}
        onClose={() => setShowAddCategory(false)}
        onAdd={handleCreateCategory}
        categories={taxonomy.categories}
      />

      <ImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImport={handleImport}
        categories={taxonomy.categories}
        products={taxonomy.products}
      />

      <AddProductModal
        isOpen={showAddProduct}
        onClose={() => setShowAddProduct(false)}
        onAdd={handleCreateProduct}
        categories={taxonomy.categories}
      />

      {/* Editor Modals */}
      {mergeModal && (
        <MergeProductModal
          isOpen={!!mergeModal}
          onClose={() => setMergeModal(null)}
          onMerge={handleMergeProducts}
          sourceProduct={mergeModal}
          products={taxonomy.products}
        />
      )}

      {mergeCategoryModal && (
        <MergeCategoryModal
          isOpen={!!mergeCategoryModal}
          onClose={() => setMergeCategoryModal(null)}
          onMerge={handleMergeCategories}
          sourceCategory={mergeCategoryModal}
          categories={taxonomy.categories}
        />
      )}

      {editProductModal && (
        <EditProductModal
          isOpen={!!editProductModal}
          onClose={() => setEditProductModal(null)}
          onSave={handleUpdateProduct}
          product={editProductModal}
          categories={taxonomy.categories}
        />
      )}

      {editCategoryModal && (
        <EditCategoryModal
          isOpen={!!editCategoryModal}
          onClose={() => setEditCategoryModal(null)}
          onSave={handleUpdateCategory}
          category={editCategoryModal}
          categories={taxonomy.categories}
        />
      )}

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setDeleteConfirm(null)} />
          <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-md mx-4">
            <h2 className="text-lg font-semibold mb-2">Delete {deleteConfirm.type}?</h2>
            <p className="text-muted mb-4">
              Are you sure you want to delete <span className="text-foreground font-medium">{deleteConfirm.name}</span>?
              This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={deleteConfirm.type === 'product' ? handleDeleteProduct : handleDeleteCategory}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function TaxonomyPage() {
  return (
    <AuthGuard>
      <TaxonomyEditor />
    </AuthGuard>
  )
}
