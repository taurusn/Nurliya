'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { startScrape } from '@/lib/api'
import { Search, Loader2, Mail } from 'lucide-react'

interface ScrapeFormProps {
  onSuccess?: () => void
}

export function ScrapeForm({ onSuccess }: ScrapeFormProps) {
  const [query, setQuery] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim() || loading) return

    setLoading(true)
    setError(null)

    try {
      await startScrape(query.trim(), email.trim() || undefined)
      setQuery('')
      setEmail('')
      onSuccess?.()
    } catch (err) {
      setError('Failed to start scrape')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="coffee shops in riyadh"
            className="w-full pl-10 pr-4 py-2.5 bg-card-hover border border-border rounded-lg text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-border-light transition-colors"
            disabled={loading}
          />
        </div>
        <motion.button
          type="submit"
          disabled={!query.trim() || loading}
          whileTap={{ scale: 0.98 }}
          className="px-4 py-2.5 bg-foreground text-background rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:bg-foreground/90 transition-colors flex items-center gap-2"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            'Start Scrape'
          )}
        </motion.button>
      </div>
      <div className="relative">
        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email for notification (optional)"
          className="w-full pl-10 pr-4 py-2.5 bg-card-hover border border-border rounded-lg text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-border-light transition-colors"
          disabled={loading}
        />
      </div>
      {error && (
        <p className="text-xs text-error">{error}</p>
      )}
    </form>
  )
}
