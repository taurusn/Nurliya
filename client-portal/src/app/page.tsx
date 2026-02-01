'use client'

import { useEffect, useState } from 'react'
import { AuthGuard } from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import { fetchOverview, fetchJobs, startScrape, OverviewData } from '@/lib/api'

function OverviewContent() {
  const { user, logout } = useAuth()
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [scraping, setScraping] = useState(false)

  const loadData = async () => {
    try {
      const [overviewData, jobsData] = await Promise.all([
        fetchOverview().catch(() => null),
        fetchJobs(5).catch(() => ({ jobs: [] })),
      ])
      if (overviewData) setOverview(overviewData)
      setJobs(jobsData.jobs || [])
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleStartScrape = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setScraping(true)
    try {
      await startScrape(query, user?.email)
      setQuery('')
      loadData()
    } catch (error) {
      console.error('Failed to start scrape:', error)
    } finally {
      setScraping(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  const metrics = overview?.metrics || {
    average_rating: null,
    positive_percentage: 0,
    reviews_count: 0,
    urgent_count: 0,
    pending_analyses: 0,
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Top Navigation */}
      <nav className="bg-zinc-900 border-b border-zinc-800 px-6 py-3 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center">
              <span className="text-sm font-bold text-white">N</span>
            </div>
            <span className="text-xl font-bold text-white">NURLIYA</span>
          </div>
          <div className="flex items-center gap-2 bg-zinc-800 px-3 py-1.5 rounded-lg">
            <span className="text-sm text-zinc-300">{overview?.places_count || 0} Places</span>
            <span className="text-zinc-500">▼</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center bg-zinc-800 px-3 py-1.5 rounded-lg">
            <span className="text-zinc-500 mr-2">🔍</span>
            <input type="text" placeholder="Search reviews..." className="bg-transparent text-sm outline-none w-40 text-zinc-300 placeholder-zinc-500" />
          </div>
          <span className="text-sm text-zinc-400">{user?.name}</span>
          <button onClick={logout} className="text-sm text-red-400 hover:text-red-300">Logout</button>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="bg-zinc-900 border-b border-zinc-800 px-6 py-6">
        <div className="max-w-7xl mx-auto">
          {/* Metrics Row */}
          <div className="grid grid-cols-5 gap-4 mb-6">
            <div className="text-center">
              <div className="text-3xl font-bold text-white">
                {metrics.average_rating?.toFixed(1) || '—'} <span className="text-yellow-500">★</span>
              </div>
              <div className="text-sm text-zinc-500">Rating</div>
              <div className="text-xs text-zinc-600">avg across places</div>
            </div>
            <div className="text-center">
              <div className={`text-3xl font-bold ${metrics.positive_percentage >= 70 ? 'text-emerald-500' : metrics.positive_percentage >= 50 ? 'text-amber-500' : 'text-red-500'}`}>
                {metrics.positive_percentage}%
              </div>
              <div className="text-sm text-zinc-500">Positive</div>
              <div className="text-xs text-zinc-600">sentiment</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-white">{metrics.reviews_count}</div>
              <div className="text-sm text-zinc-500">Reviews</div>
              <div className="text-xs text-zinc-600">total</div>
            </div>
            <div className="text-center">
              <div className={`text-3xl font-bold ${metrics.urgent_count > 0 ? 'text-red-500' : 'text-zinc-600'}`}>
                {metrics.urgent_count}
              </div>
              <div className="text-sm text-zinc-500">Urgent</div>
              <div className="text-xs text-red-500 font-medium">{metrics.urgent_count > 0 ? 'needs attention' : 'all good'}</div>
            </div>
            <div className="text-center">
              <div className={`text-3xl font-bold ${metrics.pending_analyses > 0 ? 'text-blue-500' : 'text-zinc-600'}`}>
                {metrics.pending_analyses}
              </div>
              <div className="text-sm text-zinc-500">Pending</div>
              <div className="text-xs text-blue-500 font-medium">analyses</div>
            </div>
          </div>

          {/* AI Summary Box */}
          <div className="bg-gradient-to-r from-blue-900/30 to-indigo-900/30 border border-blue-800/50 rounded-xl p-4">
            <div className="flex items-start gap-3">
              <div className="text-2xl">🤖</div>
              <div className="flex-1">
                <p className="text-zinc-300">
                  {metrics.reviews_count === 0 ? (
                    <>
                      <span className="font-semibold text-white">Getting started</span> — Start by creating a scrape job below to analyze reviews from Google Maps.
                    </>
                  ) : (
                    <>
                      <span className="font-semibold text-white">
                        {metrics.positive_percentage >= 70 ? 'Great performance' : metrics.positive_percentage >= 50 ? 'Room for improvement' : 'Needs attention'}
                      </span> — You have {metrics.reviews_count} reviews across {overview?.places_count || 0} places with {metrics.positive_percentage}% positive sentiment.
                      {metrics.urgent_count > 0 && (
                        <span className="text-red-400"> {metrics.urgent_count} urgent items need your attention.</span>
                      )}
                      {metrics.pending_analyses > 0 && (
                        <span className="text-amber-400"> {metrics.pending_analyses} reviews pending analysis.</span>
                      )}
                      {overview?.whats_hot?.[0] && (
                        <span className="text-emerald-400"> Top strength: {overview.whats_hot[0].item}.</span>
                      )}
                    </>
                  )}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* New Scrape Form */}
      <div className="bg-zinc-900/50 border-b border-zinc-800 px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <form onSubmit={handleStartScrape} className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search query (e.g., 'coffee shops in Riyadh')"
              className="flex-1 px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-zinc-500"
            />
            <button
              type="submit"
              disabled={scraping || !query.trim()}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg disabled:opacity-50"
            >
              {scraping ? 'Starting...' : 'Start Scrape'}
            </button>
          </form>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="space-y-6">
          {/* Charts Row */}
          <div className="grid grid-cols-2 gap-6">
            {/* Sentiment Trend */}
            <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
              <h3 className="font-semibold text-white mb-4">📈 Sentiment Trend (Last 7 Days)</h3>
              <div className="h-40 flex items-end justify-between gap-2 px-4">
                {(overview?.sentiment_trend || []).map((day, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center">
                    <span className={`text-xs font-medium mb-1 ${day.positive >= 70 ? 'text-emerald-500' : day.positive >= 50 ? 'text-amber-500' : 'text-red-500'}`}>
                      {day.count > 0 ? `${day.positive}%` : '—'}
                    </span>
                    <div
                      className={`w-full rounded-t-lg ${day.positive >= 70 ? 'bg-emerald-600' : day.positive >= 50 ? 'bg-amber-600' : 'bg-red-600'}`}
                      style={{ height: `${day.count > 0 ? Math.max(day.positive, 10) : 5}%` }}
                    />
                    <span className="text-xs text-zinc-500 mt-2">{day.day}</span>
                  </div>
                ))}
                {(!overview?.sentiment_trend || overview.sentiment_trend.length === 0) && (
                  <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
                    No data yet
                  </div>
                )}
              </div>
            </div>

            {/* Rating Distribution */}
            <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
              <h3 className="font-semibold text-white mb-4">⭐ Rating Distribution</h3>
              <div className="space-y-3">
                {[5, 4, 3, 2, 1].map((star) => {
                  const pct = overview?.rating_distribution?.[String(star)] || 0
                  return (
                    <div key={star} className="flex items-center gap-3">
                      <span className="text-sm w-16 text-yellow-500">
                        {'★'.repeat(star)}{'☆'.repeat(5 - star)}
                      </span>
                      <div className="flex-1 h-4 bg-zinc-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-yellow-500 rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-sm text-zinc-400 w-10">{pct}%</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Hot / Cold Row */}
          <div className="grid grid-cols-2 gap-6">
            {/* What's Hot */}
            <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
              <h3 className="font-semibold text-white mb-4">🔥 What's Hot</h3>
              <div className="space-y-3">
                {(overview?.whats_hot || []).length > 0 ? (
                  overview?.whats_hot.map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-emerald-900/20 border border-emerald-800/30 rounded-lg">
                      <span className="font-medium text-zinc-200">{item.item}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-400 font-bold">{item.score}</span>
                        <span className="text-emerald-500 text-sm">{item.mentions} mentions</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-zinc-500 text-sm p-3">
                    No positive topics found yet. Run analysis to see what customers love.
                  </div>
                )}
              </div>
            </div>

            {/* What's Not */}
            <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
              <h3 className="font-semibold text-white mb-4">❄️ What's Not</h3>
              <div className="space-y-3">
                {(overview?.whats_not || []).length > 0 ? (
                  overview?.whats_not.map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-red-900/20 border border-red-800/30 rounded-lg">
                      <span className="font-medium text-zinc-200">{item.item}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-red-400 font-bold">{item.score}</span>
                        <span className="text-red-500 text-sm">{item.mentions} mentions</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-zinc-500 text-sm p-3">
                    No negative topics found yet. Great news or more data needed!
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Alerts */}
          <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
            <h3 className="font-semibold text-white mb-4">🚨 Needs Attention</h3>
            <div className="space-y-2">
              {(overview?.alerts || []).length > 0 ? (
                overview?.alerts.map((alert, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-3 p-3 rounded-lg ${
                      alert.type === 'urgent' ? 'bg-red-900/20 border border-red-800/30' :
                      alert.type === 'warning' ? 'bg-amber-900/20 border border-amber-800/30' :
                      alert.type === 'processing' ? 'bg-blue-900/20 border border-blue-800/30' :
                      'bg-zinc-800/50 border border-zinc-700/30'
                    }`}
                  >
                    <span>{alert.icon}</span>
                    <span className="text-zinc-200">{alert.message}</span>
                  </div>
                ))
              ) : (
                <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-900/20 border border-emerald-800/30">
                  <span>✅</span>
                  <span className="text-zinc-200">All caught up! No urgent items.</span>
                </div>
              )}
            </div>
          </div>

          {/* Recent Jobs */}
          <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
            <h3 className="font-semibold text-white mb-4">📋 Recent Jobs</h3>
            {jobs.length === 0 ? (
              <p className="text-zinc-500 text-sm">No jobs yet. Start a scrape job to analyze reviews.</p>
            ) : (
              <div className="space-y-2">
                {jobs.map((job) => (
                  <div
                    key={job.id}
                    className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg"
                  >
                    <div>
                      <span className="text-sm font-medium text-white">{job.query}</span>
                      <span className={`ml-3 text-xs px-2 py-0.5 rounded ${
                        job.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' :
                        job.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                        'bg-blue-500/20 text-blue-400'
                      }`}>
                        {job.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-zinc-500">
                      <span>{job.places_found || 0} places</span>
                      <span>{job.reviews_total || 0} reviews</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Job Status Summary */}
          <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
            <h3 className="font-semibold text-white mb-4">📊 Job Status Overview</h3>
            <div className="grid grid-cols-5 gap-2 text-center">
              {['pending', 'scraping', 'processing', 'completed', 'failed'].map((status) => (
                <div key={status} className={`p-3 rounded-lg ${
                  status === 'completed' ? 'bg-emerald-900/20 border border-emerald-800/30' :
                  status === 'failed' ? 'bg-red-900/20 border border-red-800/30' :
                  status === 'pending' ? 'bg-zinc-800/50 border border-zinc-700/30' :
                  'bg-blue-900/20 border border-blue-800/30'
                }`}>
                  <div className={`text-lg font-bold ${
                    status === 'completed' ? 'text-emerald-400' :
                    status === 'failed' ? 'text-red-400' :
                    status === 'pending' ? 'text-zinc-400' :
                    'text-blue-400'
                  }`}>
                    {overview?.scrape_jobs?.[status] || 0}
                  </div>
                  <div className="text-xs text-zinc-500 capitalize">{status}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Overview() {
  return (
    <AuthGuard>
      <OverviewContent />
    </AuthGuard>
  )
}
