'use client'

import { useState, useEffect } from 'react'
import { AlertTriangle, ThumbsUp, ThumbsDown, Minus, Star, ChevronDown, ChevronUp, Package, Layers } from 'lucide-react'
import { fetchOrphanMentions, Mention, OrphanMentionsResponse } from '@/lib/api'

interface OrphanPanelProps {
  taxonomyId: string
}

export function OrphanPanel({ taxonomyId }: OrphanPanelProps) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<OrphanMentionsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedReviews, setExpandedReviews] = useState<Set<string>>(new Set())
  const [activeTab, setActiveTab] = useState<'products' | 'categories'>('products')

  useEffect(() => {
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
  }, [taxonomyId])

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

  const currentOrphans = activeTab === 'products' ? data?.product_orphans : data?.category_orphans
  const currentTotal = activeTab === 'products' ? data?.total_product_orphans : data?.total_category_orphans

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

  const totalOrphans = (data?.total_product_orphans || 0) + (data?.total_category_orphans || 0)

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
          Products ({data?.total_product_orphans || 0})
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
          Categories ({data?.total_category_orphans || 0})
        </button>
      </div>

      {/* Orphan list */}
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
      </div>

      {/* Show more indicator */}
      {currentTotal && currentOrphans && currentTotal > currentOrphans.length && (
        <div className="mt-3 text-center text-sm text-muted">
          Showing {currentOrphans.length} of {currentTotal} orphan mentions
        </div>
      )}
    </div>
  )
}
