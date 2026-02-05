'use client'

import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { X, Upload, AlertTriangle, FileJson, FolderTree, Package, Download } from 'lucide-react'
import { TaxonomyImportData, ImportCategory, TaxonomyCategory, TaxonomyProduct } from '@/lib/api'

interface ImportModalProps {
  isOpen: boolean
  onClose: () => void
  onImport: (data: TaxonomyImportData) => Promise<void>
  categories: TaxonomyCategory[]
  products: TaxonomyProduct[]
}

function validateImportData(data: unknown): { valid: boolean; error?: string; parsed?: TaxonomyImportData } {
  if (!data || typeof data !== 'object') {
    return { valid: false, error: 'Invalid JSON structure' }
  }

  const obj = data as Record<string, unknown>
  if (!Array.isArray(obj.categories) || obj.categories.length === 0) {
    return { valid: false, error: 'Must contain a non-empty "categories" array' }
  }

  for (let i = 0; i < obj.categories.length; i++) {
    const cat = obj.categories[i] as Record<string, unknown>
    if (!cat.name || typeof cat.name !== 'string') {
      return { valid: false, error: `Category ${i + 1}: missing "name"` }
    }
    if (!cat.display_name_en || typeof cat.display_name_en !== 'string') {
      return { valid: false, error: `Category "${cat.name}": missing "display_name_en"` }
    }
    if (cat.is_aspect === undefined) {
      return { valid: false, error: `Category "${cat.name}": missing "is_aspect"` }
    }
  }

  const categories: ImportCategory[] = obj.categories.map((cat: Record<string, unknown>) => ({
    name: cat.name as string,
    display_name_en: cat.display_name_en as string,
    display_name_ar: (cat.display_name_ar as string) || undefined,
    is_aspect: cat.is_aspect as boolean,
    examples: Array.isArray(cat.examples) ? cat.examples : [],
    products: Array.isArray(cat.products)
      ? (cat.products as Record<string, unknown>[]).map((p) => ({
          name: (p.name as string) || '',
          display_name: (p.display_name as string) || (p.name as string) || '',
          variants: Array.isArray(p.variants) ? p.variants : [],
        }))
      : [],
  }))

  return { valid: true, parsed: { categories } }
}

function downloadJson(data: object, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function buildBlankTemplate(): TaxonomyImportData {
  return {
    categories: [
      {
        name: 'service',
        display_name_en: 'Service Quality',
        display_name_ar: 'جودة الخدمة',
        is_aspect: true,
        examples: ['الخدمة ممتازة', 'التعامل راقي'],
        products: [],
      },
      {
        name: 'hot_drinks',
        display_name_en: 'Hot Drinks',
        display_name_ar: 'مشروبات ساخنة',
        is_aspect: false,
        examples: [],
        products: [
          {
            name: 'لاتيه',
            display_name: 'Latte / لاتيه',
            variants: ['latte', 'لاتيه'],
          },
        ],
      },
    ],
  }
}

function buildTemplateFromDraft(
  categories: TaxonomyCategory[],
  products: TaxonomyProduct[]
): TaxonomyImportData {
  const parentCats = categories.filter((c) => !c.parent_id)
  const childCats = categories.filter((c) => c.parent_id)

  return {
    categories: parentCats.map((parent) => {
      // Collect products from this parent and all its children
      // Products may be linked via assigned_category_id or discovered_category_id
      const children = childCats.filter((c) => c.parent_id === parent.id)
      const relevantCatIds = [parent.id, ...children.map((c) => c.id)]
      const catProducts = products.filter((p) => {
        const catId = p.assigned_category_id || p.discovered_category_id
        return catId && relevantCatIds.includes(catId)
      })

      return {
        name: parent.name,
        display_name_en: parent.display_name_en || parent.name,
        display_name_ar: parent.display_name_ar || undefined,
        is_aspect: !parent.has_products,
        examples: [],
        products: catProducts.map((p) => ({
          name: p.canonical_text,
          display_name: p.display_name || p.canonical_text,
          variants: p.variants || [],
        })),
      }
    }),
  }
}

export function ImportModal({ isOpen, onClose, onImport, categories, products }: ImportModalProps) {
  const [importData, setImportData] = useState<TaxonomyImportData | null>(null)
  const [fileName, setFileName] = useState('')
  const [parseError, setParseError] = useState('')
  const [loading, setLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  if (!isOpen) return null

  const handleDownloadTemplate = () => {
    downloadJson(buildBlankTemplate(), 'taxonomy-template.json')
  }

  const handleDownloadFromDraft = () => {
    const data = buildTemplateFromDraft(categories, products)
    downloadJson(data, 'taxonomy-draft-export.json')
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setParseError('')
    setImportData(null)
    setFileName(file.name)

    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const json = JSON.parse(event.target?.result as string)
        const result = validateImportData(json)
        if (result.valid && result.parsed) {
          setImportData(result.parsed)
        } else {
          setParseError(result.error || 'Invalid format')
        }
      } catch {
        setParseError('Invalid JSON file')
      }
    }
    reader.readAsText(file)
  }

  const handleSubmit = async () => {
    if (!importData) return
    setLoading(true)
    try {
      await onImport(importData)
      setImportData(null)
      setFileName('')
      onClose()
    } catch (err) {
      setParseError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    setImportData(null)
    setFileName('')
    setParseError('')
    onClose()
  }

  const categoryCount = importData?.categories.length || 0
  const aspectCount = importData?.categories.filter((c) => c.is_aspect).length || 0
  const productCatCount = categoryCount - aspectCount
  const productCount = importData?.categories.reduce(
    (sum, c) => sum + (c.products?.length || 0), 0
  ) || 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />
      <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-lg mx-4 animate-fade-in">
        <button
          onClick={handleClose}
          className="absolute top-4 right-4 text-muted hover:text-foreground"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
            <Upload className="w-5 h-5 text-primary" />
          </div>
          <h2 className="text-lg font-semibold text-foreground">Import Taxonomy</h2>
        </div>

        {/* Templates */}
        <div className="space-y-4">
          <div>
            <p className="text-sm text-muted mb-2">Start from a template</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={handleDownloadTemplate}>
                <Download className="w-4 h-4 mr-2" />
                Blank Template
              </Button>
              {categories.length > 0 && (
                <Button variant="outline" size="sm" onClick={handleDownloadFromDraft}>
                  <Download className="w-4 h-4 mr-2" />
                  From Current Draft
                </Button>
              )}
            </div>
          </div>

          {/* File upload */}
          <div>
            <p className="text-sm text-muted mb-2">Upload JSON file</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleFileChange}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-full border-2 border-dashed border-border rounded-lg p-6 text-center hover:border-primary/50 transition-colors"
            >
              <FileJson className="w-8 h-8 text-muted mx-auto mb-2" />
              {fileName ? (
                <p className="text-sm text-foreground">{fileName}</p>
              ) : (
                <p className="text-sm text-muted">Click to select a JSON file</p>
              )}
            </button>
          </div>

          {/* Parse error */}
          {parseError && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              {parseError}
            </div>
          )}

          {/* Preview */}
          {importData && (
            <div className="p-4 bg-background border border-border rounded-lg space-y-2">
              <p className="text-sm font-medium text-foreground mb-3">Preview</p>
              <div className="flex items-center gap-2 text-sm">
                <FolderTree className="w-4 h-4 text-muted" />
                <span className="text-muted">Categories:</span>
                <span className="text-foreground">{categoryCount}</span>
                <span className="text-muted">({aspectCount} aspect, {productCatCount} product)</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Package className="w-4 h-4 text-muted" />
                <span className="text-muted">Products:</span>
                <span className="text-foreground">{productCount}</span>
              </div>
              <div className="mt-3 max-h-32 overflow-y-auto space-y-1">
                {importData.categories.map((cat, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-muted">
                    <span className={cat.is_aspect ? 'text-primary' : 'text-warning'}>
                      {cat.is_aspect ? 'aspect' : 'product'}
                    </span>
                    <span className="text-foreground">{cat.display_name_en}</span>
                    {cat.products && cat.products.length > 0 && (
                      <span>({cat.products.length} products)</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Warning */}
          {importData && (
            <div className="p-3 bg-warning/10 border border-warning/20 rounded-lg text-warning text-sm flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              This will replace all existing discovered categories and trigger re-clustering.
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 justify-end pt-2">
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!importData || loading}
            >
              {loading ? 'Importing...' : 'Import & Re-cluster'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
