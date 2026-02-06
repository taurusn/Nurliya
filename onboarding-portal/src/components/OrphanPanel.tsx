'use client'

import { useState, useEffect, useMemo } from 'react'
import { AlertTriangle, ThumbsUp, ThumbsDown, Minus, Star, ChevronDown, ChevronUp, Package, Layers, List, Grid3X3, ArrowRight, Check, Loader2 } from 'lucide-react'
import {
  fetchOrphanMentions,
  fetchGroupedOrphanMentions,
  bulkMoveMentions,
  Mention,
  OrphanMentionsResponse,
  MentionGroup,
  GroupedOrphansResponse,
  TaxonomyCategory,
  TaxonomyProduct,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MoveTargetPicker } from '@/components/MoveTargetPicker'

interface OrphanPanelProps {
  taxonomyId: string
  categories?: TaxonomyCategory[]
  products?: TaxonomyProduct[]
  onMentionsMoved?: () => void
}

export function OrphanPanel({
  taxonomyId,
  categories = [],
  products = [],
  onMentionsMoved,
}: OrphanPanelProps) {
  const [viewMode, setViewMode] = useState<'list' | 'grouped'>('grouped')
  const [activeTab, setActiveTab] = useState<'products' | 'categories'>('products')

  // List view state
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<OrphanMentionsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedReviews, setExpandedReviews] = useState<Set<string>>(new Set())

  // Grouped view state
  const [groupedData, setGroupedData] = useState<GroupedOrphansResponse | null>(null)
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set())

  // Move state
  const [showMovePicker, setShowMovePicker] = useState(false)
  const [moving, setMoving] = useState(false)

  // Current groups based on active tab
  const currentGroups = useMemo(() => {
    if (!groupedData) return []
    return activeTab === 'products' ? groupedData.product_groups : groupedData.category_groups
  }, [groupedData, activeTab])

  // Get all selected mention IDs
  const selectedMentionIds = useMemo(() => {
    const ids: string[] = []
    for (const group of currentGroups) {
      if (selectedGroups.has(group.normalized_text)) {
        ids.push(...group.mention_ids)
      }
    }
    return ids
  }, [currentGroups, selectedGroups])

  // Load list view data
  useEffect(() => {
    if (viewMode !== 'list') return

    async function loadOrphans() {
      setLoading(true)
      setError(null)
      try {
        const result = await fetchOrphanMentions(taxonomyId)
        setData(result)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load orphan mentions')
      } finally {
        setLoading(false)
      }
    }
    loadOrphans()
  }, [taxonomyId, viewMode])

  // Load grouped view data
  useEffect(() => {
    if (viewMode !== 'grouped') return

    async function loadGrouped() {
      setLoading(true)
      setError(null)
      setSelectedGroups(new Set())
      try {
        const result = await fetchGroupedOrphanMentions(taxonomyId)
        setGroupedData(result)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load grouped orphan mentions')
      } finally {
        setLoading(false)
      }
    }
    loadGrouped()
  }, [taxonomyId, viewMode])

  // Clear selection when switching tabs
  useEffect(() => {
    setSelectedGroups(new Set())
  }, [activeTab])

  const toggleReview = (reviewId: string) => {
    setExpandedReviews(prev => {
      const next = new Set(prev)
      if (next.has(reviewId)) {
        next.delete(reviewId)
      } else {
        next.add(reviewId)
      }
      return next
    })
  }

  const toggleGroupSelection = (normalizedText: string) => {
    setSelectedGroups(prev => {
      const next = new Set(prev)
      if (next.has(normalizedText)) {
        next.delete(normalizedText)
      } else {
        next.add(normalizedText)
      }
      return next
    })
  }

  const selectAllGroups = () => {
    setSelectedGroups(new Set(currentGroups.map(g => g.normalized_text)))
  }

  const deselectAllGroups = () => {
    setSelectedGroups(new Set())
  }

  const handleMove = async (targetType: 'product' | 'category', targetId: string, targetName: string) => {
    if (selectedMentionIds.length === 0) return

    setMoving(true)
    try {
      await bulkMoveMentions(selectedMentionIds, targetType, targetId)
      setShowMovePicker(false)
      setSelectedGroups(new Set())
      // Refresh the data
      if (viewMode === 'grouped') {
        const result = await fetchGroupedOrphanMentions(taxonomyId)
        setGroupedData(result)
      } else {
        const result = await fetchOrphanMentions(taxonomyId)
        setData(result)
      }
      onMentionsMoved?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to move mentions')
    } finally {
      setMoving(false)
    }
  }

  const getSentimentIcon = (sentiment: string | null) => {
    switch (sentiment) {
      case 'positive':
        return <ThumbsUp className="w-3 h-3 text-success" />
      case 'negative':
        return <ThumbsDown className="w-3 h-3 text-destructive" />
      default:
        return <Minus className="w-3 h-3 text-muted" />
    }
  }

  const getSentimentBg = (sentiment: string | null) => {
    switch (sentiment) {
      case 'positive':
        return 'bg-success/10 border-success/20'
      case 'negative':
        return 'bg-destructive/10 border-destructive/20'
      default:
        return 'bg-muted/10 border-muted/20'
    }
  }

  const getDominantSentiment = (sentiments: MentionGroup['sentiments']) => {
    const { positive, negative, neutral } = sentiments
    if (positive >= negative && positive >= neutral) return 'positive'
    if (negative >= positive && negative >= neutral) return 'negative'
    return 'neutral'
  }

  // Calculate totals based on view mode
  const totalProductOrphans = viewMode === 'grouped'
    ? groupedData?.total_product_mentions || 0
    : data?.total_product_orphans || 0
  const totalCategoryOrphans = viewMode === 'grouped'
    ? groupedData?.total_category_mentions || 0
    : data?.total_category_orphans || 0
  const totalOrphans = totalProductOrphans + totalCategoryOrphans

  const currentOrphans = activeTab === 'products' ? data?.product_orphans : data?.category_orphans
  const currentTotal = activeTab === 'products' ? totalProductOrphans : totalCategoryOrphans
  const currentGroupCount = activeTab === 'products'
    ? groupedData?.total_product_groups || 0
    : groupedData?.total_category_groups || 0

  if (loading) {
    return (
      <div className="bg-card border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="w-5 h-5 text-warning" />
          <h3 className="text-lg font-semibold text-foreground">Orphan Mentions</h3>
        </div>
        <div className="text-center py-4 text-muted">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-card border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="w-5 h-5 text-warning" />
          <h3 className="text-lg font-semibold text-foreground">Orphan Mentions</h3>
        </div>
        <div className="text-center py-4 text-destructive">{error}</div>
      </div>
    )
  }

  if (totalOrphans === 0) {
    return (
      <div className="bg-card border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="w-5 h-5 text-success" />
          <h3 className="text-lg font-semibold text-foreground">Orphan Mentions</h3>
        </div>
        <div className="text-center py-4 text-success">No orphan mentions - all mentions resolved!</div>
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-warning" />
          <h3 className="text-lg font-semibold text-foreground">Orphan Mentions</h3>
          <span className="text-sm text-muted">({totalOrphans} total)</span>
        </div>
        {/* View toggle */}
        <div className="flex bg-card-hover rounded-lg p-0.5">
          <button
            onClick={() => setViewMode('grouped')}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              viewMode === 'grouped' ? 'bg-card text-foreground shadow-sm' : 'text-muted hover:text-foreground'
            }`}
            title="Grouped view"
          >
            <Grid3X3 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              viewMode === 'list' ? 'bg-card text-foreground shadow-sm' : 'text-muted hover:text-foreground'
            }`}
            title="List view"
          >
            <List className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setActiveTab('products')}
          className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm ${
            activeTab === 'products'
              ? 'bg-primary/20 text-primary border border-primary/30'
              : 'bg-card-hover text-muted hover:text-foreground'
          }`}
        >
          <Package className="w-4 h-4" />
          Products ({totalProductOrphans})
        </button>
        <button
          onClick={() => setActiveTab('categories')}
          className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm ${
            activeTab === 'categories'
              ? 'bg-primary/20 text-primary border border-primary/30'
              : 'bg-card-hover text-muted hover:text-foreground'
          }`}
        >
          <Layers className="w-4 h-4" />
          Categories ({totalCategoryOrphans})
        </button>
      </div>

      {/* Selection controls for grouped view */}
      {viewMode === 'grouped' && currentGroups.length > 0 && (
        <div className="flex items-center justify-between mb-3 p-2 bg-card-hover rounded-lg">
          <span className="text-sm text-muted">
            {currentGroupCount} groups
          </span>
          <div className="flex items-center gap-2">
            {selectedGroups.size > 0 ? (
              <>
                <span className="text-sm text-primary">
                  {selectedGroups.size} groups ({selectedMentionIds.length} mentions)
                </span>
                <Button size="sm" variant="ghost" onClick={deselectAllGroups}>
                  Clear
                </Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" onClick={selectAllGroups}>
                Select All
              </Button>
            )}
          </div>
        </div>
      )}

      {/* List view */}
      {viewMode === 'list' && (
        <div className="space-y-2 max-h-[400px] overflow-y-auto">
          {currentOrphans && currentOrphans.length === 0 && (
            <div className="text-center py-4 text-muted">
              No orphan {activeTab} mentions
            </div>
          )}

          {currentOrphans && currentOrphans.map((mention) => (
            <div
              key={mention.id}
              className={`p-3 rounded-lg border ${getSentimentBg(mention.sentiment)}`}
            >
              {/* Mention header */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  {getSentimentIcon(mention.sentiment)}
                  <span className="text-sm font-medium text-foreground">
                    "{mention.mention_text}"
                  </span>
                  <span className="text-xs px-1.5 py-0.5 bg-warning/20 text-warning rounded">
                    Orphan
                  </span>
                </div>
                {mention.review_rating && (
                  <div className="flex items-center gap-1 text-warning">
                    <Star className="w-3 h-3 fill-current" />
                    <span className="text-xs">{mention.review_rating}</span>
                  </div>
                )}
              </div>

              {/* Review preview */}
              <div className="mt-2">
                <button
                  onClick={() => toggleReview(mention.id)}
                  className="flex items-center gap-1 text-xs text-muted hover:text-foreground"
                >
                  {expandedReviews.has(mention.id) ? (
                    <ChevronUp className="w-3 h-3" />
                  ) : (
                    <ChevronDown className="w-3 h-3" />
                  )}
                  {mention.review_author || 'Anonymous'}
                  {mention.review_date && ` • ${new Date(mention.review_date).toLocaleDateString()}`}
                </button>

                {expandedReviews.has(mention.id) && (
                  <div className="mt-2 p-2 bg-card-hover rounded text-sm text-muted">
                    {mention.review_text || 'No review text available'}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Show more indicator */}
          {currentTotal && currentOrphans && currentTotal > currentOrphans.length && (
            <div className="mt-3 text-center text-sm text-muted">
              Showing {currentOrphans.length} of {currentTotal} orphan mentions
            </div>
          )}
        </div>
      )}

      {/* Grouped view */}
      {viewMode === 'grouped' && (
        <div className="max-h-[400px] overflow-y-auto">
          <div className="flex flex-wrap gap-2">
            {currentGroups.length === 0 && (
              <div className="text-center py-4 text-muted w-full">
                No orphan {activeTab} mentions
              </div>
            )}

            {currentGroups.map((group) => {
              const isSelected = selectedGroups.has(group.normalized_text)
              const dominant = getDominantSentiment(group.sentiments)
              return (
                <button
                  key={group.normalized_text}
                  onClick={() => toggleGroupSelection(group.normalized_text)}
                  className={`relative flex items-center gap-2 px-3 py-2 rounded-lg border transition-all ${
                    isSelected
                      ? 'bg-primary/20 border-primary ring-2 ring-primary/30'
                      : `${getSentimentBg(dominant)} hover:ring-2 hover:ring-primary/20`
                  }`}
                >
                  {isSelected && (
                    <div className="absolute -top-1 -right-1 w-4 h-4 bg-primary rounded-full flex items-center justify-center">
                      <Check className="w-3 h-3 text-white" />
                    </div>
                  )}
                  {getSentimentIcon(dominant)}
                  <span className="text-sm font-medium text-foreground">
                    {group.display_text}
                  </span>
                  <Badge variant="outline" className="text-xs">
                    {group.count}
                  </Badge>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Move action footer */}
      {viewMode === 'grouped' && selectedGroups.size > 0 && (categories.length > 0 || products.length > 0) && (
        <div className="mt-4 pt-4 border-t border-border flex items-center justify-between">
          <span className="text-sm text-muted">
            {selectedMentionIds.length} mentions selected
          </span>
          <Button
            onClick={() => setShowMovePicker(true)}
            disabled={moving}
          >
            {moving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Moving...
              </>
            ) : (
              <>
                <ArrowRight className="w-4 h-4 mr-2" />
                Assign to {activeTab === 'products' ? 'Product' : 'Category'}...
              </>
            )}
          </Button>
        </div>
      )}

      {/* Move target picker */}
      <MoveTargetPicker
        isOpen={showMovePicker}
        onClose={() => setShowMovePicker(false)}
        onSelect={handleMove}
        categories={categories}
        products={products}
        mentionCount={selectedMentionIds.length}
      />
    </div>
  )
}
