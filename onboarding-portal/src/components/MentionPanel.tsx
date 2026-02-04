'use client'

import { useState, useEffect } from 'react'
import { X, MessageSquare, ThumbsUp, ThumbsDown, Minus, Star, ChevronDown, ChevronUp } from 'lucide-react'
import { fetchProductMentions, fetchCategoryMentions, Mention, MentionListResponse } from '@/lib/api'

interface MentionPanelProps {
  type: 'product' | 'category'
  itemId: string
  itemName: string
  onClose: () => void
}

export function MentionPanel({ type, itemId, itemName, onClose }: MentionPanelProps) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<MentionListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedReviews, setExpandedReviews] = useState<Set<string>>(new Set())

  useEffect(() => {
    async function loadMentions() {
      setLoading(true)
      setError(null)
      try {
        const result = type === 'product'
          ? await fetchProductMentions(itemId)
          : await fetchCategoryMentions(itemId)
        setData(result)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load mentions')
      } finally {
        setLoading(false)
      }
    }
    loadMentions()
  }, [type, itemId])

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
          <button onClick={onClose} className="p-1 hover:bg-card-hover rounded">
            <X className="w-5 h-5 text-muted" />
          </button>
        </div>

        {/* Stats */}
        {data && (
          <div className="flex gap-4 p-4 border-b border-border bg-card-hover">
            <div className="text-center">
              <div className="text-2xl font-bold text-success">{data.matched_count}</div>
              <div className="text-xs text-muted">Matched</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-warning">{data.below_threshold_count}</div>
              <div className="text-xs text-muted">Below Threshold</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-foreground">{data.total}</div>
              <div className="text-xs text-muted">Total</div>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading && (
            <div className="text-center py-8 text-muted">Loading mentions...</div>
          )}

          {error && (
            <div className="text-center py-8 text-destructive">{error}</div>
          )}

          {data && data.mentions.length === 0 && (
            <div className="text-center py-8 text-muted">No mentions found</div>
          )}

          {data && data.mentions.map((mention) => (
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
                  {/* BUG-014 FIX: Show actual similarity score for below-threshold mentions */}
                  {mention.similarity_score != null && mention.similarity_score < 0.8 && (
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      mention.similarity_score >= 0.7
                        ? 'bg-warning/30 text-warning'
                        : mention.similarity_score >= 0.6
                          ? 'bg-warning/20 text-warning'
                          : 'bg-muted/20 text-muted'
                    }`}>
                      {(mention.similarity_score * 100).toFixed(0)}% similar
                    </span>
                  )}
                  {mention.similarity_score === 1.0 && (
                    <span className="text-xs px-1.5 py-0.5 bg-success/20 text-success rounded">
                      Matched
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
        </div>
      </div>
    </div>
  )
}
