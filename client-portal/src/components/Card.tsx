'use client'

import { cn } from '@/lib/cn'

interface CardProps {
  title: string
  children: React.ReactNode
  className?: string
}

export function Card({ title, children, className }: CardProps) {
  return (
    <div className={cn('bg-card rounded-xl border border-border', className)}>
      <div className="px-4 py-3 border-b border-border">
        <h3 className="text-xs font-medium text-muted uppercase tracking-wider">{title}</h3>
      </div>
      <div className="p-4">
        {children}
      </div>
    </div>
  )
}
