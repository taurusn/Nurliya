'use client'

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { X, MessageSquare, ThumbsUp, ThumbsDown, Minus, Star, ChevronDown, ChevronUp, Loader2, List, Grid3X3, ArrowRight, Check } from 'lucide-react'
import {
  fetchProductMentions,
  fetchCategoryMentions,
  fetchGroupedProductMentions,
  fetchGroupedCategoryMentions,
  bulkMoveMentions,
  Mention,
  MentionListResponse,
  MentionGroup,
  GroupedMentionsResponse,
  TaxonomyCategory,
  TaxonomyProduct,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MoveTargetPicker } from '@/components/MoveTargetPicker'

interface MentionPanelProps {
  type: 'product' | 'category'
  itemId: string
  itemName: string
  onClose: () => void
  categories?: TaxonomyCategory[]
  products?: TaxonomyProduct[]
  onMentionsMoved?: () => void  // Callback to refresh parent data
}

const PAGE_SIZE = 50

export function MentionPanel({
  type,
  itemId,
  itemName,
  onClose,
  categories = [],
  products = [],
  onMentionsMoved,
}: MentionPanelProps) {
  const [viewMode, setViewMode] = useState<'list' | 'grouped'>('grouped')

  // List view state
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [mentions, setMentions] = useState<Mention[]>([])
  const [stats, setStats] = useState<{ matched: number; similar: number; total: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedReviews, setExpandedReviews] = useState<Set<string>>(new Set())
  const [hasMore, setHasMore] = useState(true)
  const [offset, setOffset] = useState(0)

  // Grouped view state
  const [groups, setGroups] = useState<MentionGroup[]>([])
  const [groupedStats, setGroupedStats] = useState<{ totalMentions: number; totalGroups: number } | null>(null)
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set())

  // Move state
  const [showMovePicker, setShowMovePicker] = useState(false)
  const [moving, setMoving] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)

  // Get all selected mention IDs
  const selectedMentionIds = useMemo(() => {
    const ids: string[] = []
    for (const group of groups) {
      if (selectedGroups.has(group.normalized_text)) {
        ids.push(...group.mention_ids)
      }
    }
    return ids
  }, [groups, selectedGroups])

  // Initial load - list view
  useEffect(() => {
    if (viewMode !== 'list') return

    async function loadInitial() {
      setLoading(true)
      setError(null)
      setMentions([])
      setOffset(0)
      setHasMore(true)
      try {
        const result = type === 'product'
          ? await fetchProductMentions(itemId, true, PAGE_SIZE, 0)
          : await fetchCategoryMentions(itemId, true, PAGE_SIZE, 0)
        setMentions(result.mentions)
        setStats({
          matched: result.matched_count,
          similar: result.below_threshold_count,
          total: result.total,
        })
        setHasMore(result.mentions.length < result.total)
        setOffset(result.mentions.length)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load mentions')
      } finally {
        setLoading(false)
      }
    }
    loadInitial()
  }, [type, itemId, viewMode])

  // Initial load - grouped view
  useEffect(() => {
    if (viewMode !== 'grouped') return

    async function loadGrouped() {
      setLoading(true)
      setError(null)
      setGroups([])
      setSelectedGroups(new Set())
      try {
        const result = type === 'product'
          ? await fetchGroupedProductMentions(itemId)
          : await fetchGroupedCategoryMentions(itemId)
        setGroups(result.groups)
        setGroupedStats({
          totalMentions: result.total_mentions,
          totalGroups: result.total_groups,
        })
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load grouped mentions')
      } finally {
        setLoading(false)
      }
    }
    loadGrouped()
  }, [type, itemId, viewMode])

  // Load more for list view
  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore || viewMode !== 'list') return
    setLoadingMore(true)
    try {
      const result = type === 'product'
        ? await fetchProductMentions(itemId, true, PAGE_SIZE, offset)
        : await fetchCategoryMentions(itemId, true, PAGE_SIZE, offset)
      setMentions(prev => [...prev, ...result.mentions])
      setHasMore(offset + result.mentions.length < result.total)
      setOffset(prev => prev + result.mentions.length)
    } catch (e) {
      console.error('Failed to load more mentions:', e)
    } finally {
      setLoadingMore(false)
    }
  }, [type, itemId, offset, loadingMore, hasMore, viewMode])

  // Infinite scroll handler
  const handleScroll = useCallback(() => {
    if (!scrollRef.current || viewMode !== 'list') return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    if (scrollHeight - scrollTop - clientHeight < 200) {
      loadMore()
    }
  }, [loadMore, viewMode])

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
    setSelectedGroups(new Set(groups.map(g => g.normalized_text)))
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
      // Refresh the grouped data
      if (viewMode === 'grouped') {
        const result = type === 'product'
          ? await fetchGroupedProductMentions(itemId)
          : await fetchGroupedCategoryMentions(itemId)
        setGroups(result.groups)
        setGroupedStats({
          totalMentions: result.total_mentions,
          totalGroups: result.total_groups,
        })
      }
      // Notify parent to refresh
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-foreground">
              Mentions: {itemName}
            </h2>
          </div>
          <div className="flex items-center gap-2">
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
            <button onClick={onClose} className="p-1 hover:bg-card-hover rounded">
              <X className="w-5 h-5 text-muted" />
            </button>
          </div>
        </div>

        {/* Stats */}
        {viewMode === 'list' && stats && (
          <div className="flex gap-4 p-4 border-b border-border bg-card-hover">
            <div className="text-center">
              <div className="text-2xl font-bold text-success">{stats.matched}</div>
              <div className="text-xs text-muted">Resolved</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-warning">{stats.similar}</div>
              <div className="text-xs text-muted">{stats.matched === 0 ? 'Discovered' : 'Near Match'}</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-foreground">{stats.total}</div>
              <div className="text-xs text-muted">Total</div>
            </div>
          </div>
        )}

        {viewMode === 'grouped' && groupedStats && (
          <div className="flex items-center justify-between p-4 border-b border-border bg-card-hover">
            <div className="flex gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-foreground">{groupedStats.totalMentions}</div>
                <div className="text-xs text-muted">Mentions</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-primary">{groupedStats.totalGroups}</div>
                <div className="text-xs text-muted">Groups</div>
              </div>
            </div>
            {/* Selection controls */}
            {groups.length > 0 && (
              <div className="flex items-center gap-2">
                {selectedGroups.size > 0 ? (
                  <>
                    <span className="text-sm text-muted">
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
            )}
          </div>
        )}

        {/* Content */}
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-4"
        >
          {loading && (
            <div className="text-center py-8 text-muted">Loading mentions...</div>
          )}

          {error && (
            <div className="text-center py-8 text-destructive">{error}</div>
          )}

          {/* List view */}
          {viewMode === 'list' && !loading && (
            <div className="space-y-3">
              {mentions.length === 0 && (
                <div className="text-center py-8 text-muted">No mentions found</div>
              )}

              {mentions.map((mention) => (
                <div
                  key={mention.id}
                  className={`p-3 rounded-lg border ${getSentimentBg(mention.sentiment)} ${
                    mention.similarity_score != null && mention.similarity_score < 0.8 ? 'opacity-75' : ''
                  }`}
                >
                  {/* Mention header */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      {getSentimentIcon(mention.sentiment)}
                      <span className="text-sm font-medium text-foreground">
                        "{mention.mention_text}"
                      </span>
                      {mention.similarity_score != null && mention.similarity_score < 0.8 && mention.similarity_score > 0 && (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          mention.similarity_score >= 0.7
                            ? 'bg-warning/30 text-warning'
                            : mention.similarity_score >= 0.6
                              ? 'bg-warning/20 text-warning'
                              : 'bg-muted/20 text-muted'
                        }`}>
                          {(mention.similarity_score * 100).toFixed(0)}% match
                        </span>
                      )}
                      {mention.similarity_score === 1.0 && (
                        <span className="text-xs px-1.5 py-0.5 bg-success/20 text-success rounded">
                          Exact
                        </span>
                      )}
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

              {/* Loading more indicator */}
              {loadingMore && (
                <div className="flex justify-center py-4">
                  <Loader2 className="w-5 h-5 animate-spin text-muted" />
                </div>
              )}

              {/* End of list */}
              {!hasMore && mentions.length > 0 && (
                <div className="text-center py-4 text-xs text-muted">
                  Showing all {mentions.length} mentions
                </div>
              )}
            </div>
          )}

          {/* Grouped view */}
          {viewMode === 'grouped' && !loading && (
            <div className="flex flex-wrap gap-2">
              {groups.length === 0 && (
                <div className="text-center py-8 text-muted w-full">No mentions found</div>
              )}

              {groups.map((group) => {
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
          )}
        </div>

        {/* Footer with move action */}
        {viewMode === 'grouped' && selectedGroups.size > 0 && (categories.length > 0 || products.length > 0) && (
          <div className="p-4 border-t border-border bg-card-hover flex items-center justify-between">
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
                  Move to...
                </>
              )}
            </Button>
          </div>
        )}
      </div>

      {/* Move target picker */}
      <MoveTargetPicker
        isOpen={showMovePicker}
        onClose={() => setShowMovePicker(false)}
        onSelect={handleMove}
        categories={categories}
        products={products}
        mentionCount={selectedMentionIds.length}
        currentEntityId={itemId}
        currentEntityType={type}
      />
    </div>
  )
}
