'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/cn'

interface Job {
  id: string
  query: string
  status: string
  places_found: number
  reviews_total: number
  reviews_processed: number
}

interface JobProgressProps {
  job: Job
}

export function JobProgress({ job }: JobProgressProps) {
  const reviewsProcessed = job.reviews_processed ?? 0
  const reviewsTotal = job.reviews_total ?? 0
  const progress = reviewsTotal > 0
    ? (reviewsProcessed / reviewsTotal) * 100
    : 0

  const statusColors: Record<string, string> = {
    pending: 'text-muted',
    scraping: 'text-warning',
    processing: 'text-blue-400',
    completed: 'text-success',
    failed: 'text-error',
  }

  return (
    <div className="p-4 bg-card-hover rounded-lg border border-border animate-slide-up">
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground truncate">{job.query}</p>
          <p className="text-xs text-muted mt-0.5">
            {job.places_found ?? 0} places · {reviewsTotal} reviews
          </p>
        </div>
        <span className={cn(
          'text-xs font-medium uppercase tracking-wide px-2 py-0.5 rounded',
          statusColors[job.status] || 'text-muted',
          job.status === 'processing' && 'bg-blue-400/10',
          job.status === 'scraping' && 'bg-warning/10',
        )}>
          {job.status}
        </span>
      </div>
      
      <div className="relative h-1.5 bg-border rounded-full overflow-hidden">
        <motion.div 
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-zinc-500 to-zinc-400 rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
      
      <p className="text-xs text-muted mt-2 font-mono">
        {reviewsProcessed.toLocaleString()} / {reviewsTotal.toLocaleString()} processed
      </p>
    </div>
  )
}
