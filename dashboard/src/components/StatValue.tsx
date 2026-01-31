'use client'

import { motion } from 'framer-motion'

interface StatValueProps {
  label: string
  value: number | string
  suffix?: string
}

export function StatValue({ label, value, suffix }: StatValueProps) {
  return (
    <div className="flex justify-between items-baseline py-2 border-b border-border/50 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <motion.span 
        key={String(value)}
        initial={{ opacity: 0.5 }}
        animate={{ opacity: 1 }}
        className="text-sm font-mono text-foreground tabular-nums"
      >
        {typeof value === 'number' ? value.toLocaleString() : value}
        {suffix && <span className="text-muted ml-1">{suffix}</span>}
      </motion.span>
    </div>
  )
}
