'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { X, AlertTriangle } from 'lucide-react'

interface RejectModalProps {
  isOpen: boolean
  onClose: () => void
  onReject: (reason: string) => Promise<void>
  itemName: string
  itemType: 'category' | 'product'
}

export function RejectModal({ isOpen, onClose, onReject, itemName, itemType }: RejectModalProps) {
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!reason.trim()) return

    setLoading(true)
    try {
      await onReject(reason)
      setReason('')
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-md mx-4 animate-fade-in">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-muted hover:text-foreground"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-destructive/20 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-destructive" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">Reject {itemType}</h2>
            <p className="text-sm text-muted">{itemName}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Rejection reason
            </label>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this being rejected?"
              required
            />
          </div>

          <div className="flex gap-3 justify-end">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={loading || !reason.trim()}>
              {loading ? 'Rejecting...' : 'Reject'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
