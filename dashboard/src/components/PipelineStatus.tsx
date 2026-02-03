'use client'

import { motion } from 'framer-motion'
import { Layers, FileText, Brain, CheckCircle, Clock, AlertCircle } from 'lucide-react'

interface PipelineStatusProps {
  stats: {
    reviews_count?: number
    mentions_count?: number
    analyses_count?: number
    queue_messages?: number
    queue_consumers?: number
  } | null
}

export function PipelineStatus({ stats }: PipelineStatusProps) {
  const reviews = stats?.reviews_count ?? 0
  const mentions = stats?.mentions_count ?? 0
  const analyses = stats?.analyses_count ?? 0
  const queueMessages = stats?.queue_messages ?? 0
  const queueConsumers = stats?.queue_consumers ?? 0

  // Calculate pipeline stages
  const extractionRate = reviews > 0 ? Math.round((mentions / reviews) * 100) / 100 : 0
  const analysisProgress = reviews > 0 ? Math.round((analyses / reviews) * 100) : 0
  const pendingAnalysis = reviews - analyses

  // Determine pipeline state
  const isExtracting = queueMessages > 0 && queueConsumers > 0
  const isIdle = queueMessages === 0

  return (
    <div className="space-y-4">
      {/* Pipeline Stages */}
      <div className="flex items-center justify-between text-xs text-muted">
        <span>Extract</span>
        <span className="mx-2">→</span>
        <span>Cluster</span>
        <span className="mx-2">→</span>
        <span>Approve</span>
        <span className="mx-2">→</span>
        <span>Analyze</span>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-3">
        {/* Extraction */}
        <div className="bg-card-hover rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-muted">Extraction</span>
          </div>
          <div className="text-lg font-semibold text-foreground">
            {mentions.toLocaleString()}
          </div>
          <div className="text-xs text-muted">
            mentions ({extractionRate} per review)
          </div>
        </div>

        {/* Analysis */}
        <div className="bg-card-hover rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-4 h-4 text-purple-400" />
            <span className="text-xs text-muted">Analysis</span>
          </div>
          <div className="text-lg font-semibold text-foreground">
            {analyses.toLocaleString()}
          </div>
          <div className="text-xs text-muted">
            {analysisProgress}% complete
          </div>
        </div>
      </div>

      {/* Queue Status */}
      <div className="bg-card-hover rounded-lg p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-amber-400" />
            <span className="text-xs text-muted">Queue</span>
          </div>
          <div className="flex items-center gap-1">
            {isExtracting ? (
              <>
                <motion.div
                  className="w-2 h-2 rounded-full bg-amber-400"
                  animate={{ opacity: [1, 0.5, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                />
                <span className="text-xs text-amber-400">Processing</span>
              </>
            ) : isIdle ? (
              <>
                <CheckCircle className="w-3 h-3 text-success" />
                <span className="text-xs text-success">Idle</span>
              </>
            ) : (
              <>
                <Clock className="w-3 h-3 text-muted" />
                <span className="text-xs text-muted">Waiting</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <span className="text-lg font-semibold text-foreground">{queueMessages.toLocaleString()}</span>
            <span className="text-xs text-muted ml-1">messages</span>
          </div>
          <div className="text-right">
            <span className="text-lg font-semibold text-foreground">{queueConsumers}</span>
            <span className="text-xs text-muted ml-1">workers</span>
          </div>
        </div>

        {/* Progress bar */}
        {queueMessages > 0 && (
          <div className="mt-2">
            <div className="h-1 bg-border rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-amber-400 to-amber-500"
                initial={{ width: '100%' }}
                animate={{ width: '100%' }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Pending Analysis Warning */}
      {pendingAnalysis > 100 && (
        <div className="flex items-center gap-2 p-2 bg-amber-500/10 rounded-lg">
          <AlertCircle className="w-4 h-4 text-amber-400" />
          <span className="text-xs text-amber-400">
            {pendingAnalysis.toLocaleString()} reviews pending analysis (waiting for taxonomy approval)
          </span>
        </div>
      )}
    </div>
  )
}
