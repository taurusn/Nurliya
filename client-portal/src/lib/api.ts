const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.nurliya.com'

function getAuthHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export async function fetchStats() {
  const res = await fetch(`${API_URL}/api/stats`, { headers: getAuthHeaders() })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch stats')
  }
  return res.json()
}

export async function fetchJobs(limit = 20, offset = 0) {
  const res = await fetch(`${API_URL}/api/jobs?limit=${limit}&offset=${offset}`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch jobs')
  }
  return res.json()
}

export interface Place {
  id: string
  name: string
  category?: string
  address?: string
  rating?: number
  review_count: number
  analyzed_count: number
}

export async function fetchPlaces(limit = 100, offset = 0): Promise<{ places: Place[], total: number }> {
  const res = await fetch(`${API_URL}/api/places?limit=${limit}&offset=${offset}`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch places')
  }
  return res.json()
}

export async function fetchPlaceStats(placeId: string) {
  const res = await fetch(`${API_URL}/api/places/${placeId}/stats`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch place stats')
  }
  return res.json()
}

export async function startScrape(query: string, email?: string) {
  const res = await fetch(`${API_URL}/api/scrape`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      query,
      notification_email: email,
      depth: 10,
      lang: 'en',
      max_time: 300,
    }),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to start scrape')
  }
  return res.json()
}

export async function fetchJobProgress(jobId: string) {
  const res = await fetch(`${API_URL}/api/jobs/${jobId}`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch job progress')
  }
  return res.json()
}

export interface OverviewData {
  metrics: {
    average_rating: number | null
    positive_percentage: number
    reviews_count: number
    urgent_count: number
    pending_analyses: number
  }
  sentiment_trend: Array<{
    date: string
    day: string
    positive: number
    count: number
  }>
  rating_distribution: Record<string, number>
  top_positive_topics: Array<{ topic: string; count: number }>
  top_negative_topics: Array<{ topic: string; count: number }>
  whats_hot: Array<{ item: string; score: string; mentions: number }>
  whats_not: Array<{ item: string; score: string; mentions: number }>
  alerts: Array<{
    type: string
    icon: string
    message: string
    count: number
  }>
  places_count: number
  sentiment_counts: Record<string, number>
  scrape_jobs: Record<string, number>
}

export async function fetchOverview(placeId?: string): Promise<OverviewData> {
  const url = placeId ? `${API_URL}/api/overview?place_id=${placeId}` : `${API_URL}/api/overview`
  const res = await fetch(url, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch overview')
  }
  return res.json()
}

export type TrendPeriod = '7d' | '30d' | '90d' | '1y' | '2y' | '5y' | 'all' | 'custom'
export type ZoomLevel = 'day' | 'week' | 'month' | 'year'

export interface TrendDataPoint {
  date: string
  label: string
  positive: number
  negative: number
  neutral: number
  total: number
  positive_pct: number
  is_anomaly?: boolean
  anomaly_type?: 'spike' | 'drop'
  anomaly_reason?: string
}

export interface Anomaly {
  date: string
  type: 'spike' | 'drop'
  magnitude: number
  reason: string
  llm_insight?: {
    analysis: string
    recommendation: string
  }
  review_ids: string[]
}

export interface TrendResponse {
  data: TrendDataPoint[]
  anomalies: Anomaly[]
  topics_in_period: string[]
  baseline: {
    avg_positive_pct: number
    avg_daily_reviews: number
  }
}

export interface TrendFilters {
  period?: TrendPeriod
  zoom?: ZoomLevel
  start_date?: string
  end_date?: string
  topic?: string
  place_id?: string
}

export async function fetchSentimentTrend(filters: TrendFilters = {}): Promise<TrendResponse> {
  const params = new URLSearchParams()
  if (filters.period) params.append('period', filters.period)
  if (filters.zoom) params.append('zoom', filters.zoom)
  if (filters.start_date) params.append('start_date', filters.start_date)
  if (filters.end_date) params.append('end_date', filters.end_date)
  if (filters.topic) params.append('topic', filters.topic)
  if (filters.place_id) params.append('place_id', filters.place_id)

  const url = `${API_URL}/api/sentiment-trend?${params.toString()}`
  const res = await fetch(url, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch sentiment trend')
  }
  return res.json()
}

export interface DateReview {
  id: string
  text: string
  rating: number
  author: string
  date: string
  place_name: string
  sentiment: string
  score: number | null
  topics_positive: string[]
  topics_negative: string[]
  summary_en: string
  summary_ar: string
  suggested_reply_ar: string
  urgent: boolean
}

export interface DateReviewsResponse {
  reviews: DateReview[]
  total: number
  date: string
  filters: {
    topic: string | null
    sentiment: string | null
    place_id: string | null
  }
}

export async function fetchDateReviews(
  date: string,
  options: { topic?: string; sentiment?: string; place_id?: string } = {}
): Promise<DateReviewsResponse> {
  const params = new URLSearchParams()
  if (options.topic) params.append('topic', options.topic)
  if (options.sentiment) params.append('sentiment', options.sentiment)
  if (options.place_id) params.append('place_id', options.place_id)

  const queryString = params.toString()
  const url = `${API_URL}/api/sentiment-trend/${date}/reviews${queryString ? `?${queryString}` : ''}`
  const res = await fetch(url, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch date reviews')
  }
  return res.json()
}
