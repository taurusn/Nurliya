import { Badge } from '@/components/ui/badge'
import { Check, X, Clock } from 'lucide-react'

interface ApprovalBadgeProps {
  isApproved: boolean
  rejectionReason?: string | null
}

export function ApprovalBadge({ isApproved, rejectionReason }: ApprovalBadgeProps) {
  if (isApproved) {
    return (
      <Badge variant="success" className="gap-1">
        <Check className="w-3 h-3" />
        Approved
      </Badge>
    )
  }

  if (rejectionReason) {
    return (
      <Badge variant="destructive" className="gap-1">
        <X className="w-3 h-3" />
        Rejected
      </Badge>
    )
  }

  return (
    <Badge variant="warning" className="gap-1">
      <Clock className="w-3 h-3" />
      Pending
    </Badge>
  )
}
