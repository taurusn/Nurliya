const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function fetchStats(placeId?: string) {
  const url = placeId
    ? `${API_URL}/api/stats?place_id=${placeId}`
    : `${API_URL}/api/stats`
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed to fetch stats')
  return res.json()
}

export interface Place {
  id: string
  name: string
  google_place_id?: string
  address?: string
  rating?: number
  total_reviews?: number
}

export async function fetchPlaces(): Promise<{ places: Place[] }> {
  const res = await fetch(`${API_URL}/api/places?limit=100`)
  if (!res.ok) throw new Error('Failed to fetch places')
  return res.json()
}

export interface PipelineStageStatus {
  place_id: string
  place_name: string
  stage: 'scraping' | 'extracting' | 'clustering' | 'approving' | 'analyzing' | 'complete'
  stage_progress: number
  reviews_count: number
  mentions_count: number
  analyses_count: number
  analyzable_reviews: number
  taxonomy_status: string | null
  taxonomy_id: string | null
  stages: {
    scraping: { reviews: number }
    extracting: { mentions: number; reviews: number }
    clustering: { mentions: number }
    approving: { approved: number; total: number }
    analyzing: { analyzed: number; total: number }
    complete: { reviews: number; mentions: number; analyzed: number }
  }
}

export async function fetchPipelineStatus(placeId?: string): Promise<PipelineStageStatus | { places: PipelineStageStatus[] }> {
  const url = placeId
    ? `${API_URL}/api/pipeline-status?place_id=${placeId}`
    : `${API_URL}/api/pipeline-status`
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed to fetch pipeline status')
  return res.json()
}

export async function fetchQueueStatus() {
  const res = await fetch(`${API_URL}/api/queue-status`)
  if (!res.ok) throw new Error('Failed to fetch queue status')
  return res.json()
}

export async function fetchRecentAnalyses() {
  const res = await fetch(`${API_URL}/api/recent-analyses`)
  if (!res.ok) throw new Error('Failed to fetch analyses')
  return res.json()
}

export async function fetchSystemHealth() {
  const res = await fetch(`${API_URL}/api/system-health`)
  if (!res.ok) throw new Error('Failed to fetch health')
  return res.json()
}

export async function fetchJobs(limit = 10) {
  const res = await fetch(`${API_URL}/api/jobs?limit=${limit}`)
  if (!res.ok) throw new Error('Failed to fetch jobs')
  return res.json()
}

export async function startScrape(query: string, email?: string) {
  const res = await fetch(`${API_URL}/api/scrape`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      notification_email: email || undefined,
      depth: 10,
      lang: 'en',
      max_time: 300,
    }),
  })
  if (!res.ok) throw new Error('Failed to start scrape')
  return res.json()
}

export interface LogEntry {
  id: string
  timestamp: string | null
  level: string
  category: string
  action: string
  message: string
  details: Record<string, any>
  job_id: string | null
  scrape_job_id: string | null
  place_id: string | null
}

export interface LogsResponse {
  logs: LogEntry[]
  pagination: {
    page: number
    limit: number
    total: number
    total_pages: number
    has_next: boolean
    has_prev: boolean
  }
}

export async function fetchLogs(page = 1, limit = 10, category?: string, level?: string): Promise<LogsResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    limit: limit.toString(),
  })
  if (category) params.set('category', category)
  if (level) params.set('level', level)

  const res = await fetch(`${API_URL}/api/logs?${params}`)
  if (!res.ok) throw new Error('Failed to fetch logs')
  return res.json()
}
