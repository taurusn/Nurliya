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
    analysis_ar?: string
    recommendation: string
    recommendation_ar?: string
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

// --- Insights ---

export interface InsightsData {
  place_id: string
  place_name: string
  generated_at: string
  data_summary: {
    total_reviews: number
    analyzed_reviews: number
    total_mentions: number
    date_range: { from: string | null; to: string | null }
  }
  action_checklist?: {
    total: number
    recent: number
    items: Array<{
      review_id: string
      author: string
      rating: number
      review_date: string
      text?: string
      action_en: string
      action_ar: string
      summary_en: string
      urgent: boolean
      sentiment: string
      score: number | null
    }>
  }
  problem_products?: {
    items: Array<{
      product_id: string
      product_name: string
      category_name: string | null
      category_name_ar: string | null
      negative_mentions: number
      total_mentions: number
      negative_pct: number
      avg_sentiment: number | null
      sample_complaints: Array<{ text: string; review_date: string | null }>
    }>
  }
  opening_checklist?: {
    items: Array<{
      topic: string
      check_item_en: string
      check_item_ar: string
      complaint_count: number
      recent_count: number
      severity: 'high' | 'medium' | 'low'
      review_ids?: string[]
    }>
    llm_generated: boolean
  }
  urgent_issues?: {
    total: number
    recent: number
    items: Array<{
      review_id: string
      author: string
      rating: number
      review_date: string
      text?: string
      summary_en: string
      summary_ar: string
      action_en: string
      action_ar: string
      topics_negative: string[]
    }>
  }
  time_patterns?: {
    day_of_week: Array<{
      day: string
      day_ar: string
      avg_rating: number | null
      review_count: number
      negative_pct: number
    }>
    monthly_trend: Array<{
      month: string
      label: string
      avg_rating: number | null
      review_count: number
      negative_pct: number
    }>
    busiest_day: string | null
    worst_day: string | null
    best_month: string | null
    worst_month: string | null
  }
  recurring_complaints?: {
    items: Array<{
      topic: string
      topic_display: string
      count: number
      recent_count: number
      trend: 'increasing' | 'decreasing' | 'stable'
      pct_of_negative: number
      sample_reviews: Array<{ text: string; date: string }>
    }>
  }
  top_praised?: {
    items: Array<{
      product_id: string
      product_name: string
      category_name: string | null
      category_name_ar: string | null
      positive_mentions: number
      total_mentions: number
      positive_pct: number
      avg_sentiment: number | null
      sample_praises: Array<{ text: string; review_date: string | null }>
    }>
  }
  satisfaction_drops?: {
    items: Array<{
      id: string
      date: string
      topic: string | null
      anomaly_type: string
      magnitude: number | null
      analysis: string | null
      analysis_ar?: string | null
      recommendation: string | null
      recommendation_ar?: string | null
      review_count: number
      review_ids?: string[]
    }>
  }
  patterns?: {
    day_topic_correlations: Array<{
      day: string
      topic: string
      negative_count: number
      avg_per_day: number
      multiplier: number
    }>
    monthly_topic_shifts: Array<{
      topic: string
      direction: 'worsening' | 'improving'
      recent_negative_pct: number
      previous_negative_pct: number
      change: number
    }>
  }
  weekly_plan?: {
    summary: {
      urgent_to_resolve: number
      actions_pending: number
      top_complaint: string | null
      problem_products_count: number
    }
    summary_en: string
    summary_ar: string
    priorities: Array<{
      priority: number
      type: string
      title_en: string
      title_ar: string
      detail_en: string
      detail_ar?: string
    }>
    llm_generated: boolean
  }
  praised_employees?: {
    staff_positive_mentions: number
    staff_negative_mentions: number
    staff_sentiment_ratio: number
    positive_samples: Array<{ text: string; date: string }>
    negative_samples: Array<{ text: string; date: string }>
    note: string
  }
  loyalty_alerts?: {
    repeat_customers: Array<{
      author: string
      review_count: number
      first_review: string
      latest_review: string
      avg_rating: number | null
      rating_trend: 'declining' | 'improving' | 'stable'
      ratings: number[]
      latest_sentiment: string | null
      alert: string | null
    }>
    total_repeat_customers: number
    declining_count: number
    improving_count: number
  }
}

export async function fetchInsights(placeId: string, options?: { sections?: string[], start_date?: string, end_date?: string }): Promise<InsightsData> {
  const params = new URLSearchParams()
  params.append('place_id', placeId)
  if (options?.sections) params.append('sections', options.sections.join(','))
  if (options?.start_date) params.append('start_date', options.start_date)
  if (options?.end_date) params.append('end_date', options.end_date)

  const res = await fetch(`${API_URL}/api/insights?${params.toString()}`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch insights')
  }
  return res.json()
}

// --- Review Search (drill-down) ---

export interface ReviewSearchParams {
  place_id: string
  ids?: string[]
  product_id?: string
  topic?: string
  sentiment?: string
  author?: string
  day_of_week?: number
  limit?: number
  offset?: number
}

export interface ReviewSearchResult {
  reviews: DateReview[]
  total: number
}

export async function fetchReviewSearch(params: ReviewSearchParams): Promise<ReviewSearchResult> {
  const qs = new URLSearchParams()
  qs.append('place_id', params.place_id)
  if (params.ids?.length) qs.append('ids', params.ids.join(','))
  if (params.product_id) qs.append('product_id', params.product_id)
  if (params.topic) qs.append('topic', params.topic)
  if (params.sentiment) qs.append('sentiment', params.sentiment)
  if (params.author) qs.append('author', params.author)
  if (params.day_of_week !== undefined) qs.append('day_of_week', String(params.day_of_week))
  if (params.limit) qs.append('limit', String(params.limit))
  if (params.offset) qs.append('offset', String(params.offset))

  const res = await fetch(`${API_URL}/api/reviews/search?${qs.toString()}`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to search reviews')
  }
  const data = await res.json()
  // Map ReviewWithAnalysis (nested analysis) → DateReview (flat) format
  return {
    reviews: (data.reviews || []).map((r: any) => ({
      id: r.id,
      text: r.text || '',
      rating: r.rating,
      author: r.author || '',
      date: r.review_date || r.date || '',
      place_name: r.place_name || '',
      sentiment: r.analysis?.sentiment || r.sentiment || 'neutral',
      score: r.analysis?.score ?? r.score ?? null,
      topics_positive: r.analysis?.topics_positive || r.topics_positive || [],
      topics_negative: r.analysis?.topics_negative || r.topics_negative || [],
      summary_en: r.analysis?.summary_en || r.summary_en || '',
      summary_ar: r.analysis?.summary_ar || r.summary_ar || '',
      suggested_reply_ar: r.analysis?.suggested_reply_ar || r.suggested_reply_ar || '',
      urgent: r.analysis?.urgent || r.urgent || false,
    })),
    total: data.total,
  }
}

// --- Date Reviews ---

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
