'use client'

import { cn } from '@/lib/cn'

type Status = 'ok' | 'warning' | 'error' | 'loading'

interface StatusIndicatorProps {
  status: Status
  label: string
  sublabel?: string
}

export function StatusIndicator({ status, label, sublabel }: StatusIndicatorProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 bg-card rounded-lg border border-border">
      <div className={cn(
        'w-2 h-2 rounded-full',
        status === 'ok' && 'bg-success animate-pulse-dot',
        status === 'warning' && 'bg-warning',
        status === 'error' && 'bg-error',
        status === 'loading' && 'bg-muted animate-pulse',
      )} />
      <div className="flex flex-col">
        <span className="text-sm font-medium text-foreground">{label}</span>
        {sublabel && (
          <span className="text-xs text-muted">{sublabel}</span>
        )}
      </div>
    </div>
  )
}
