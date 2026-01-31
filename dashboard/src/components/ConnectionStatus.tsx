'use client'

import { cn } from '@/lib/cn'
import { Wifi, WifiOff } from 'lucide-react'

interface ConnectionStatusProps {
  isConnected: boolean
}

export function ConnectionStatus({ isConnected }: ConnectionStatusProps) {
  return (
    <div className={cn(
      'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
      isConnected 
        ? 'bg-success/10 text-success' 
        : 'bg-error/10 text-error'
    )}>
      {isConnected ? (
        <>
          <Wifi className="w-3 h-3" />
          <span>Live</span>
        </>
      ) : (
        <>
          <WifiOff className="w-3 h-3" />
          <span>Reconnecting...</span>
        </>
      )}
    </div>
  )
}
