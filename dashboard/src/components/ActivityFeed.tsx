'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/cn'

interface Analysis {
  review_id: string
  place_name: string | null
  sentiment: string | null
  score: number | null
  summary_en: string | null
  review_text?: string | null
  analyzed_at: string | null
}

interface ActivityFeedProps {
  analyses: Analysis[]
}

export function ActivityFeed({ analyses }: ActivityFeedProps) {
  const getSentimentColor = (sentiment: string | null) => {
    switch (sentiment) {
      case 'positive': return 'text-success'
      case 'negative': return 'text-error'
      case 'neutral': return 'text-muted'
      default: return 'text-muted'
    }
  }

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  }

  return (
    <div className="space-y-2 max-h-[400px] overflow-y-auto">
      <AnimatePresence mode="popLayout">
        {analyses.map((analysis, index) => (
          <motion.div
            key={analysis.review_id}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, delay: index * 0.02 }}
            className="flex items-start gap-3 p-3 rounded-lg bg-card-hover border border-border/50 hover:border-border transition-colors"
          >
            <span className="text-xs text-muted font-mono whitespace-nowrap mt-0.5">
              {formatTime(analysis.analyzed_at)}
            </span>
            
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm text-foreground truncate">
                  {analysis.place_name || 'Unknown'}
                </span>
                <span className={cn(
                  'text-xs font-medium',
                  getSentimentColor(analysis.sentiment)
                )}>
                  {analysis.sentiment}
                </span>
                {analysis.score !== null && (
                  <span className="text-xs text-muted font-mono">
                    {analysis.score.toFixed(2)}
                  </span>
                )}
              </div>
              {analysis.summary_en && (
                <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                  {analysis.summary_en}
                </p>
              )}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
      
      {analyses.length === 0 && (
        <p className="text-sm text-muted text-center py-8">No recent activity</p>
      )}
    </div>
  )
}
