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

export async function fetchPlaces(limit = 20, offset = 0) {
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

export async function fetchOverview(): Promise<OverviewData> {
  const res = await fetch(`${API_URL}/api/overview`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized')
    throw new Error('Failed to fetch overview')
  }
  return res.json()
}
