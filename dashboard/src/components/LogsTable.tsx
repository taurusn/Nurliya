'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/cn'
import { fetchLogs, LogEntry } from '@/lib/api'
import { useWebSocket } from '@/lib/useWebSocket'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Info,
  Mail,
  Search,
  Server,
  Loader2,
  Filter,
  Wifi,
  WifiOff,
} from 'lucide-react'

interface LogsTableProps {
  className?: string
}

const LEVEL_CONFIG = {
  info: { icon: Info, color: 'text-blue-400', bg: 'bg-blue-400/10' },
  success: { icon: CheckCircle, color: 'text-success', bg: 'bg-success/10' },
  warning: { icon: AlertTriangle, color: 'text-yellow-400', bg: 'bg-yellow-400/10' },
  error: { icon: AlertCircle, color: 'text-error', bg: 'bg-error/10' },
}

const CATEGORY_CONFIG = {
  scraper: { icon: Search, label: 'Scraper' },
  analysis: { icon: Activity, label: 'Analysis' },
  job: { icon: Server, label: 'Job' },
  email: { icon: Mail, label: 'Email' },
  worker: { icon: Server, label: 'Worker' },
  system: { icon: AlertCircle, label: 'System' },
}

export function LogsTable({ className }: LogsTableProps) {
  const { isConnected, recentLogs } = useWebSocket()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [isInitialLoad, setIsInitialLoad] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [levelFilter, setLevelFilter] = useState<string>('')

  const containerRef = useRef<HTMLDivElement>(null)
  const observerRef = useRef<IntersectionObserver | null>(null)
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const seenIdsRef = useRef<Set<string>>(new Set())

  const loadLogs = useCallback(async (pageNum: number, reset = false) => {
    if (isLoading) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await fetchLogs(
        pageNum,
        10,
        categoryFilter || undefined,
        levelFilter || undefined
      )

      if (reset) {
        seenIdsRef.current = new Set(response.logs.map(l => l.id))
        setLogs(response.logs)
      } else {
        setLogs(prev => {
          const newLogs = response.logs.filter(l => !seenIdsRef.current.has(l.id))
          newLogs.forEach(l => seenIdsRef.current.add(l.id))
          return [...prev, ...newLogs]
        })
      }
      setHasMore(response.pagination.has_next)
      setPage(pageNum)
    } catch (err) {
      setError('Failed to load logs')
      console.error('Error fetching logs:', err)
    } finally {
      setIsLoading(false)
      setIsInitialLoad(false)
    }
  }, [categoryFilter, levelFilter, isLoading])

  // Initial load and filter changes
  useEffect(() => {
    setPage(1)
    setLogs([])
    setHasMore(true)
    setIsInitialLoad(true)
    seenIdsRef.current = new Set()
    loadLogs(1, true)
  }, [categoryFilter, levelFilter])

  // Merge WebSocket logs in real-time (prepend new logs)
  useEffect(() => {
    if (recentLogs.length > 0 && !categoryFilter && !levelFilter) {
      setLogs(prev => {
        const newLogs = recentLogs.filter(l => !seenIdsRef.current.has(l.id))
        if (newLogs.length === 0) return prev

        newLogs.forEach(l => seenIdsRef.current.add(l.id))
        return [...newLogs, ...prev]
      })
    }
  }, [recentLogs, categoryFilter, levelFilter])

  // Infinite scroll observer
  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect()
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoading && !isInitialLoad) {
          loadLogs(page + 1)
        }
      },
      { threshold: 0.1 }
    )

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current)
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect()
      }
    }
  }, [hasMore, isLoading, isInitialLoad, page, loadLogs])

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return '--:--:--'
    const date = new Date(dateStr)
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    const today = new Date()
    const isToday = date.toDateString() === today.toDateString()
    if (isToday) return 'Today'
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  const getLevelConfig = (level: string) => {
    return LEVEL_CONFIG[level as keyof typeof LEVEL_CONFIG] || LEVEL_CONFIG.info
  }

  const getCategoryConfig = (category: string) => {
    return CATEGORY_CONFIG[category as keyof typeof CATEGORY_CONFIG] || { icon: Activity, label: category }
  }

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header with filters and connection status */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Filter size={14} />
            <span>Filter:</span>
          </div>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="text-xs bg-card border border-border rounded px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-border"
          >
            <option value="">All Categories</option>
            <option value="scraper">Scraper</option>
            <option value="analysis">Analysis</option>
            <option value="job">Job</option>
            <option value="email">Email</option>
            <option value="worker">Worker</option>
            <option value="system">System</option>
          </select>

          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="text-xs bg-card border border-border rounded px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-border"
          >
            <option value="">All Levels</option>
            <option value="info">Info</option>
            <option value="success">Success</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
          </select>

          {(categoryFilter || levelFilter) && (
            <button
              onClick={() => {
                setCategoryFilter('')
                setLevelFilter('')
              }}
              className="text-xs text-muted hover:text-foreground transition-colors"
            >
              Clear
            </button>
          )}
        </div>

        {/* Live indicator */}
        <div className={cn(
          'flex items-center gap-1.5 text-xs px-2 py-1 rounded',
          isConnected ? 'text-success bg-success/10' : 'text-muted bg-card'
        )}>
          {isConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
          <span>{isConnected ? 'Live' : 'Offline'}</span>
        </div>
      </div>

      {/* Logs container */}
      <div
        ref={containerRef}
        className="space-y-2 max-h-[500px] overflow-y-auto pr-1"
      >
        {isInitialLoad ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted" />
          </div>
        ) : error ? (
          <div className="text-center py-8 text-error text-sm">{error}</div>
        ) : logs.length === 0 ? (
          <div className="text-center py-8 text-muted text-sm">No logs found</div>
        ) : (
          <AnimatePresence mode="popLayout">
            {logs.map((log, index) => {
              const levelConfig = getLevelConfig(log.level)
              const categoryConfig = getCategoryConfig(log.category)
              const LevelIcon = levelConfig.icon
              const CategoryIcon = categoryConfig.icon

              return (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.15, delay: index < 10 ? index * 0.02 : 0 }}
                  className="flex items-start gap-3 p-3 rounded-lg bg-card-hover border border-border/50 hover:border-border transition-colors"
                >
                  {/* Timestamp */}
                  <div className="flex flex-col items-end text-right min-w-[60px]">
                    <span className="text-xs text-muted font-mono">
                      {formatTime(log.timestamp)}
                    </span>
                    <span className="text-[10px] text-muted/60">
                      {formatDate(log.timestamp)}
                    </span>
                  </div>

                  {/* Level indicator */}
                  <div className={cn('p-1 rounded', levelConfig.bg)}>
                    <LevelIcon size={14} className={levelConfig.color} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="inline-flex items-center gap-1 text-xs text-muted bg-card px-1.5 py-0.5 rounded">
                        <CategoryIcon size={10} />
                        {categoryConfig.label}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {log.action.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <p className="text-sm text-foreground mt-1 line-clamp-2">
                      {log.message}
                    </p>
                  </div>
                </motion.div>
              )
            })}
          </AnimatePresence>
        )}

        {/* Load more trigger */}
        <div ref={loadMoreRef} className="h-4" />

        {/* Loading more indicator */}
        {isLoading && !isInitialLoad && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="w-4 h-4 animate-spin text-muted" />
            <span className="ml-2 text-xs text-muted">Loading more...</span>
          </div>
        )}

        {/* End of list */}
        {!hasMore && logs.length > 0 && (
          <div className="text-center py-4 text-xs text-muted">
            End of logs ({logs.length} total)
          </div>
        )}
      </div>
    </div>
  )
}
