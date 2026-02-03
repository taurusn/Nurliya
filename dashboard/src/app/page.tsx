'use client'

import { useEffect, useState, useCallback } from 'react'
import useSWR from 'swr'
import { motion } from 'framer-motion'
import { useWebSocket } from '@/lib/useWebSocket'
import { fetchStats, fetchQueueStatus, fetchRecentAnalyses, fetchSystemHealth, fetchJobs } from '@/lib/api'
import { Card } from '@/components/Card'
import { StatValue } from '@/components/StatValue'
import { StatusIndicator } from '@/components/StatusIndicator'
import { JobProgress } from '@/components/JobProgress'
import { ActivityFeed } from '@/components/ActivityFeed'
import { ScrapeForm } from '@/components/ScrapeForm'
import { ConnectionStatus } from '@/components/ConnectionStatus'
import { LogsTable } from '@/components/LogsTable'
import { Overview } from '@/components/Overview'
import { PipelineStatus } from '@/components/PipelineStatus'
import { Database, Server, Cpu, MessageSquare, Layers } from 'lucide-react'

export default function Dashboard() {
  const { isConnected, stats: wsStats, recentAnalysis } = useWebSocket()
  
  // Initial data fetch
  const { data: initialStats, mutate: mutateStats } = useSWR('stats', fetchStats, {
    refreshInterval: 10000,
    revalidateOnFocus: false,
  })
  
  const { data: queueStatus } = useSWR('queue', fetchQueueStatus, {
    refreshInterval: 5000,
    revalidateOnFocus: false,
  })
  
  const { data: healthData } = useSWR('health', fetchSystemHealth, {
    refreshInterval: 10000,
    revalidateOnFocus: false,
  })
  
  const { data: analysesData, mutate: mutateAnalyses } = useSWR('analyses', fetchRecentAnalyses, {
    refreshInterval: 5000,
    revalidateOnFocus: false,
  })
  
  const { data: jobsData, mutate: mutateJobs } = useSWR('jobs', () => fetchJobs(5), {
    refreshInterval: 5000,
    revalidateOnFocus: false,
  })

  // Use WebSocket stats if available, otherwise fall back to REST
  const stats = wsStats || initialStats
  const activeJobs = wsStats?.active_jobs || jobsData?.jobs?.filter((j: any) => 
    ['pending', 'scraping', 'processing'].includes(j.status)
  ) || []

  // Prepend new analysis from WebSocket
  const [analyses, setAnalyses] = useState<any[]>([])
  
  useEffect(() => {
    if (analysesData?.analyses) {
      setAnalyses(analysesData.analyses)
    }
  }, [analysesData])

  useEffect(() => {
    if (recentAnalysis) {
      setAnalyses(prev => {
        const exists = prev.some(a => a.review_id === recentAnalysis.review_id)
        if (exists) return prev
        return [recentAnalysis, ...prev].slice(0, 15)
      })
    }
  }, [recentAnalysis])

  const getHealthStatus = (key: string): 'ok' | 'error' | 'loading' => {
    if (!healthData) return 'loading'
    return healthData[key] ? 'ok' : 'error'
  }

  const handleScrapeSuccess = useCallback(() => {
    mutateJobs()
    mutateStats()
  }, [mutateJobs, mutateStats])

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-sm border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-zinc-600 to-zinc-800 flex items-center justify-center">
              <span className="text-sm font-bold text-white">N</span>
            </div>
            <h1 className="text-lg font-semibold text-foreground">Nurliya</h1>
            <span className="text-xs text-muted px-2 py-0.5 bg-card rounded">dev</span>
          </div>
          <ConnectionStatus isConnected={isConnected} />
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        {/* System Status */}
        <section>
          <h2 className="text-xs font-medium text-muted uppercase tracking-wider mb-3">System Status</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <StatusIndicator 
              status={getHealthStatus('api')} 
              label="API" 
              sublabel="FastAPI"
            />
            <StatusIndicator 
              status={getHealthStatus('scraper')} 
              label="Scraper" 
              sublabel="Go service"
            />
            <StatusIndicator 
              status={getHealthStatus('vllm')} 
              label="vLLM" 
              sublabel="Llama 3.1"
            />
            <StatusIndicator 
              status={getHealthStatus('database')} 
              label="Postgres" 
              sublabel="Database"
            />
            <StatusIndicator 
              status={getHealthStatus('rabbitmq')} 
              label="RabbitMQ" 
              sublabel="Queue"
            />
          </div>
        </section>

        {/* Active Jobs */}
        {activeJobs.length > 0 && (
          <section>
            <h2 className="text-xs font-medium text-muted uppercase tracking-wider mb-3">Active Jobs</h2>
            <div className="space-y-3">
              {activeJobs.map((job: any) => (
                <JobProgress key={job.id} job={job} />
              ))}
            </div>
          </section>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Database Stats */}
          <Card title="Database">
            <div className="space-y-1">
              <StatValue label="Places" value={stats?.places_count ?? '-'} />
              <StatValue label="Reviews" value={stats?.reviews_count ?? '-'} />
              <StatValue label="Analyzed" value={stats?.analyses_count ?? '-'} />
              <StatValue label="Mentions" value={stats?.mentions_count ?? '-'} />
            </div>
          </Card>

          {/* Pipeline Status - Real-time via WebSocket */}
          <Card title="Pipeline Status">
            <PipelineStatus stats={stats} />
          </Card>

          {/* Jobs Summary */}
          <Card title="Jobs">
            <div className="space-y-1">
              <StatValue label="Completed" value={stats?.scrape_jobs?.completed ?? '-'} />
              <StatValue label="Processing" value={stats?.scrape_jobs?.processing ?? '-'} />
              <StatValue label="Scraping" value={stats?.scrape_jobs?.scraping ?? '-'} />
              <StatValue label="Failed" value={stats?.scrape_jobs?.failed ?? '-'} />
            </div>
          </Card>
        </div>

        {/* Analytics Overview */}
        <section>
          <h2 className="text-xs font-medium text-muted uppercase tracking-wider mb-3">Analytics Overview</h2>
          <Overview />
        </section>

        {/* Activity Feed */}
        <Card title="Recent Activity" className="md:col-span-2">
          <ActivityFeed analyses={analyses} />
        </Card>

        {/* System Logs */}
        <Card title="System Logs">
          <LogsTable />
        </Card>

        {/* New Scrape Form */}
        <Card title="New Scrape">
          <ScrapeForm onSuccess={handleScrapeSuccess} />
        </Card>
      </main>
    </div>
  )
}
