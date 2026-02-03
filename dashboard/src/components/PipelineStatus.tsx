'use client'

import { motion } from 'framer-motion'
import { Layers, FileText, Brain, CheckCircle, Clock, AlertCircle, Search, Users, Sparkles } from 'lucide-react'
import { cn } from '@/lib/cn'
import { PipelineStageStatus } from '@/lib/api'

interface PipelineStatusProps {
  stats: {
    reviews_count?: number
    mentions_count?: number
    analyses_count?: number
    queue_messages?: number
    queue_consumers?: number
  } | null
  pipelineStatus?: PipelineStageStatus | null
}

const STAGES = [
  { key: 'scraping', label: 'Scrape', icon: Search },
  { key: 'extracting', label: 'Extract', icon: FileText },
  { key: 'clustering', label: 'Cluster', icon: Sparkles },
  { key: 'approving', label: 'Approve', icon: Users },
  { key: 'analyzing', label: 'Analyze', icon: Brain },
  { key: 'complete', label: 'Done', icon: CheckCircle },
] as const

type StageKey = typeof STAGES[number]['key']

function getStageIndex(stage: string): number {
  return STAGES.findIndex(s => s.key === stage)
}

export function PipelineStatus({ stats, pipelineStatus }: PipelineStatusProps) {
  const reviews = stats?.reviews_count ?? 0
  const mentions = stats?.mentions_count ?? 0
  const analyses = stats?.analyses_count ?? 0
  const queueMessages = stats?.queue_messages ?? 0
  const queueConsumers = stats?.queue_consumers ?? 0

  // Current stage from pipeline status or calculate from stats
  const currentStage = pipelineStatus?.stage || calculateStage(reviews, mentions, analyses)
  const stageProgress = pipelineStatus?.stage_progress ?? 0
  const currentStageIndex = getStageIndex(currentStage)

  // Calculate pipeline stats
  const extractionRate = reviews > 0 ? Math.round((mentions / reviews) * 100) / 100 : 0
  const analysisProgress = reviews > 0 ? Math.round((analyses / reviews) * 100) : 0

  // Queue state
  const isProcessing = queueMessages > 0 && queueConsumers > 0

  return (
    <div className="space-y-4">
      {/* Pipeline Stages - Dynamic */}
      <div className="flex items-center justify-between">
        {STAGES.map((stage, index) => {
          const Icon = stage.icon
          const isActive = stage.key === currentStage
          const isComplete = index < currentStageIndex
          const isFuture = index > currentStageIndex

          return (
            <div key={stage.key} className="flex items-center">
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center transition-all",
                    isComplete && "bg-success/20 text-success",
                    isActive && "bg-blue-500/20 text-blue-400 ring-2 ring-blue-400/50",
                    isFuture && "bg-card-hover text-muted"
                  )}
                >
                  {isActive && isProcessing ? (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                    >
                      <Icon className="w-4 h-4" />
                    </motion.div>
                  ) : (
                    <Icon className="w-4 h-4" />
                  )}
                </div>
                <span
                  className={cn(
                    "text-[10px] mt-1",
                    isComplete && "text-success",
                    isActive && "text-blue-400 font-medium",
                    isFuture && "text-muted"
                  )}
                >
                  {stage.label}
                </span>
              </div>
              {index < STAGES.length - 1 && (
                <div
                  className={cn(
                    "w-4 h-0.5 mx-1 mt-[-12px]",
                    index < currentStageIndex ? "bg-success" : "bg-border"
                  )}
                />
              )}
            </div>
          )
        })}
      </div>

      {/* Stage Progress Bar */}
      {currentStage !== 'complete' && stageProgress > 0 && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-muted capitalize">{currentStage}</span>
            <span className="text-foreground">{stageProgress}%</span>
          </div>
          <div className="h-1.5 bg-border rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-blue-500 rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${stageProgress}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-3">
        {/* Extraction */}
        <div className={cn(
          "rounded-lg p-3 transition-all",
          currentStage === 'extracting' ? "bg-blue-500/10 ring-1 ring-blue-500/30" : "bg-card-hover"
        )}>
          <div className="flex items-center gap-2 mb-2">
            <FileText className={cn("w-4 h-4", currentStage === 'extracting' ? "text-blue-400" : "text-muted")} />
            <span className="text-xs text-muted">Extraction</span>
          </div>
          <div className="text-lg font-semibold text-foreground">
            {mentions.toLocaleString()}
          </div>
          <div className="text-xs text-muted">
            mentions ({extractionRate}/review)
          </div>
        </div>

        {/* Analysis */}
        <div className={cn(
          "rounded-lg p-3 transition-all",
          currentStage === 'analyzing' ? "bg-purple-500/10 ring-1 ring-purple-500/30" : "bg-card-hover"
        )}>
          <div className="flex items-center gap-2 mb-2">
            <Brain className={cn("w-4 h-4", currentStage === 'analyzing' ? "text-purple-400" : "text-muted")} />
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
            {isProcessing ? (
              <>
                <motion.div
                  className="w-2 h-2 rounded-full bg-amber-400"
                  animate={{ opacity: [1, 0.5, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                />
                <span className="text-xs text-amber-400">Processing</span>
              </>
            ) : queueMessages === 0 ? (
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
      </div>

      {/* Taxonomy Status */}
      {pipelineStatus?.taxonomy_status && (
        <div className={cn(
          "flex items-center gap-2 p-2 rounded-lg text-xs",
          pipelineStatus.taxonomy_status === 'active' ? "bg-success/10 text-success" :
          pipelineStatus.taxonomy_status === 'draft' ? "bg-amber-500/10 text-amber-400" :
          "bg-card-hover text-muted"
        )}>
          {pipelineStatus.taxonomy_status === 'active' ? (
            <CheckCircle className="w-4 h-4" />
          ) : pipelineStatus.taxonomy_status === 'draft' ? (
            <AlertCircle className="w-4 h-4" />
          ) : (
            <Clock className="w-4 h-4" />
          )}
          <span>
            Taxonomy: {pipelineStatus.taxonomy_status === 'active' ? 'Published' :
                       pipelineStatus.taxonomy_status === 'draft' ? 'Awaiting approval' :
                       pipelineStatus.taxonomy_status}
          </span>
        </div>
      )}
    </div>
  )
}

function calculateStage(reviews: number, mentions: number, analyses: number): StageKey {
  if (reviews === 0) return 'scraping'
  if (mentions === 0) return 'extracting'
  if (mentions < reviews * 0.3) return 'extracting'
  if (analyses === 0) return 'clustering'
  if (analyses < reviews) return 'analyzing'
  return 'complete'
}
