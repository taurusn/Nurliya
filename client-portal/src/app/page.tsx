'use client'

import { useEffect, useState } from 'react'
import { AuthGuard } from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import {
  fetchOverview,
  fetchJobs,
  startScrape,
  fetchSentimentTrend,
  fetchPlaces,
  fetchDateReviews,
  OverviewData,
  TrendPeriod,
  ZoomLevel,
  TrendDataPoint,
  TrendResponse,
  Anomaly,
  DateReview,
  Place
} from '@/lib/api'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Star,
  TrendingUp,
  MessageSquare,
  AlertTriangle,
  Clock,
  BarChart3,
  ThumbsUp,
  ThumbsDown,
  Bell,
  Briefcase,
  PieChart,
  Search,
  LogOut,
  MapPin,
  ChevronDown,
  Loader2,
  CheckCircle2,
  XCircle,
  Zap,
  Cog,
  ArrowLeft,
  Lightbulb,
  Filter,
  Calendar,
} from 'lucide-react'

const ZOOM_LEVELS: { value: ZoomLevel; label: string }[] = [
  { value: 'day', label: 'Days' },
  { value: 'week', label: 'Weeks' },
  { value: 'month', label: 'Months' },
  { value: 'year', label: 'Years' },
]

// Format date string based on its format (handles day, week, month, year)
function formatDateLabel(dateStr: string): string {
  if (!dateStr) return ''

  // Year format: 2025
  if (/^\d{4}$/.test(dateStr)) {
    return dateStr
  }

  // Month format: 2025-01
  if (/^\d{4}-\d{2}$/.test(dateStr)) {
    const [year, month] = dateStr.split('-')
    const date = new Date(parseInt(year), parseInt(month) - 1, 1)
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' })
  }

  // Week format: 2025-W01
  if (/^\d{4}-W\d{2}$/i.test(dateStr)) {
    const [year, week] = dateStr.toUpperCase().split('-W')
    return `Week ${parseInt(week)}, ${year}`
  }

  // Day format: 2025-01-15
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    const date = new Date(dateStr + 'T00:00:00')
    return date.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
  }

  return dateStr
}

function OverviewContent() {
  const { user, logout } = useAuth()
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [jobs, setJobs] = useState<any[]>([])
  const [places, setPlaces] = useState<Place[]>([])
  const [selectedPlace, setSelectedPlace] = useState<string | null>(null)
  const [placesDropdownOpen, setPlacesDropdownOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [scraping, setScraping] = useState(false)
  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>('day')
  const [trendPeriod, setTrendPeriod] = useState<TrendPeriod>('30d')
  const [trendData, setTrendData] = useState<TrendDataPoint[]>([])
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendAnomalies, setTrendAnomalies] = useState<Anomaly[]>([])
  const [topicsInPeriod, setTopicsInPeriod] = useState<string[]>([])
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null)
  const [trendBaseline, setTrendBaseline] = useState<{ avg_positive_pct: number; avg_daily_reviews: number } | null>(null)

  // Drill-down state
  const [drillDownDate, setDrillDownDate] = useState<string | null>(null)
  const [drillDownReviews, setDrillDownReviews] = useState<DateReview[]>([])
  const [drillDownLoading, setDrillDownLoading] = useState(false)
  const [drillDownSentimentFilter, setDrillDownSentimentFilter] = useState<string | null>(null)
  const [topicDropdownOpen, setTopicDropdownOpen] = useState(false)

  // Custom date range
  const [customStartDate, setCustomStartDate] = useState<string>('')
  const [customEndDate, setCustomEndDate] = useState<string>('')

  const loadPlaces = async () => {
    try {
      const data = await fetchPlaces(100)
      setPlaces(data.places || [])
    } catch (error) {
      console.error('Failed to load places:', error)
    }
  }

  const loadData = async (placeId?: string | null) => {
    try {
      const [overviewData, jobsData] = await Promise.all([
        fetchOverview(placeId || undefined).catch(() => null),
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

  const loadTrend = async (period: TrendPeriod, zoom: ZoomLevel, placeId?: string | null, topic?: string | null) => {
    setTrendLoading(true)
    try {
      const response = await fetchSentimentTrend({
        period,
        zoom,
        place_id: placeId || undefined,
        topic: topic || undefined,
        start_date: period === 'custom' ? customStartDate : undefined,
        end_date: period === 'custom' ? customEndDate : undefined,
      })
      setTrendData(response.data)
      setTrendAnomalies(response.anomalies)
      setTopicsInPeriod(response.topics_in_period)
      setTrendBaseline(response.baseline)
    } catch (error) {
      console.error('Failed to load trend:', error)
      setTrendData([])
      setTrendAnomalies([])
    } finally {
      setTrendLoading(false)
    }
  }

  const loadDrillDownReviews = async (date: string, sentimentFilter?: string | null) => {
    setDrillDownLoading(true)
    try {
      const response = await fetchDateReviews(date, {
        sentiment: sentimentFilter || undefined,
        topic: selectedTopic || undefined,
        place_id: selectedPlace || undefined,
      })
      setDrillDownReviews(response.reviews)
    } catch (error) {
      console.error('Failed to load reviews:', error)
      setDrillDownReviews([])
    } finally {
      setDrillDownLoading(false)
    }
  }

  const handleBarClick = (point: TrendDataPoint) => {
    if (point.total === 0) return
    setDrillDownDate(point.date)
    setDrillDownSentimentFilter(null)
    loadDrillDownReviews(point.date)
  }

  const handleBackToChart = () => {
    setDrillDownDate(null)
    setDrillDownReviews([])
    setDrillDownSentimentFilter(null)
  }

  const handleSentimentFilterChange = (sentiment: string | null) => {
    setDrillDownSentimentFilter(sentiment)
    if (drillDownDate) {
      loadDrillDownReviews(drillDownDate, sentiment)
    }
  }

  const getAnomalyForDate = (date: string): Anomaly | undefined => {
    return trendAnomalies.find(a => a.date === date)
  }

  useEffect(() => {
    loadPlaces()
    loadData(selectedPlace)
    loadTrend(trendPeriod, zoomLevel, selectedPlace)
    const interval = setInterval(() => {
      loadData(selectedPlace)
      loadPlaces()
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    loadTrend(trendPeriod, zoomLevel, selectedPlace, selectedTopic)
  }, [trendPeriod, zoomLevel, selectedTopic])

  // When place selection changes, reload all data
  useEffect(() => {
    loadData(selectedPlace)
    loadTrend(trendPeriod, zoomLevel, selectedPlace, selectedTopic)
    // Reset drill-down when place changes
    setDrillDownDate(null)
    setDrillDownReviews([])
  }, [selectedPlace])

  const handlePlaceSelect = (placeId: string | null) => {
    setSelectedPlace(placeId)
    setPlacesDropdownOpen(false)
  }

  const selectedPlaceName = selectedPlace
    ? places.find(p => p.id === selectedPlace)?.name || 'Selected Place'
    : 'All Places'

  const handleStartScrape = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setScraping(true)
    try {
      await startScrape(query, user?.email)
      setQuery('')
      loadData(selectedPlace)
      loadPlaces() // Reload places to show the new place
    } catch (error) {
      console.error('Failed to start scrape:', error)
    } finally {
      setScraping(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
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
    <div className="min-h-screen bg-background">
      {/* Top Navigation */}
      <nav className="bg-card border-b border-border px-4 sm:px-6 py-3 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2 sm:gap-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-blue-700 flex items-center justify-center">
                <span className="text-sm font-bold text-white">N</span>
              </div>
              <span className="text-lg sm:text-xl font-bold text-foreground hidden sm:inline">NURLIYA</span>
            </div>
            <div className="relative">
              <button
                onClick={() => setPlacesDropdownOpen(!placesDropdownOpen)}
                className="flex items-center gap-2 bg-card-hover px-3 py-1.5 rounded-lg border border-border hover:border-muted transition-colors"
              >
                <MapPin className="w-4 h-4 text-muted" />
                <span className="text-sm text-foreground hidden sm:inline truncate max-w-[120px]">{selectedPlaceName}</span>
                <span className="text-sm text-foreground sm:hidden">{places.length}</span>
                <ChevronDown className={`w-4 h-4 text-muted transition-transform ${placesDropdownOpen ? 'rotate-180' : ''}`} />
              </button>
              {placesDropdownOpen && (
                <>
                  {/* Backdrop */}
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setPlacesDropdownOpen(false)}
                  />
                  {/* Dropdown */}
                  <div className="absolute top-full left-0 mt-1 w-64 max-h-80 overflow-y-auto bg-card border border-border rounded-lg shadow-lg z-50">
                    <button
                      onClick={() => handlePlaceSelect(null)}
                      className={`w-full text-left px-3 py-2 text-sm hover:bg-card-hover transition-colors ${
                        selectedPlace === null ? 'bg-primary/10 text-primary font-medium' : 'text-foreground'
                      }`}
                    >
                      All Places ({places.length})
                    </button>
                    <div className="border-t border-border" />
                    {places.length === 0 ? (
                      <div className="px-3 py-2 text-sm text-muted">No places yet</div>
                    ) : (
                      places.map((place) => (
                        <button
                          key={place.id}
                          onClick={() => handlePlaceSelect(place.id)}
                          className={`w-full text-left px-3 py-2 text-sm hover:bg-card-hover transition-colors ${
                            selectedPlace === place.id ? 'bg-primary/10 text-primary font-medium' : 'text-foreground'
                          }`}
                        >
                          <div className="truncate">{place.name}</div>
                          <div className="text-xs text-muted">
                            {place.review_count} reviews | {place.analyzed_count} analyzed
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            <div className="hidden md:flex items-center bg-card-hover border border-border px-3 py-1.5 rounded-lg">
              <Search className="w-4 h-4 text-muted mr-2" />
              <input
                type="text"
                placeholder="Search reviews..."
                className="bg-transparent text-sm outline-none w-40 text-foreground placeholder-muted"
              />
            </div>
            <span className="text-sm text-muted hidden sm:inline">{user?.name}</span>
            <Button variant="ghost" size="sm" onClick={logout} className="text-muted hover:text-destructive">
              <LogOut className="w-4 h-4" />
              <span className="ml-2 hidden sm:inline">Logout</span>
            </Button>
          </div>
        </div>
      </nav>

      {/* Metrics Bar - Compact */}
      <div className="bg-card border-b border-border px-4 sm:px-6 py-3">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-wrap items-center gap-3 sm:gap-6">
            {/* Metrics - Inline */}
            <div className="flex items-center gap-2">
              <Star className="w-4 h-4 text-yellow-500" />
              <span className="text-lg font-bold text-foreground">{metrics.average_rating?.toFixed(1) || '—'}</span>
              <span className="text-xs text-muted hidden sm:inline">rating</span>
            </div>
            <div className="w-px h-6 bg-border hidden sm:block" />
            <div className="flex items-center gap-2">
              <TrendingUp className={`w-4 h-4 ${metrics.positive_percentage >= 70 ? 'text-success' : metrics.positive_percentage >= 50 ? 'text-warning' : 'text-destructive'}`} />
              <span className={`text-lg font-bold ${metrics.positive_percentage >= 70 ? 'text-success' : metrics.positive_percentage >= 50 ? 'text-warning' : 'text-destructive'}`}>{metrics.positive_percentage}%</span>
              <span className="text-xs text-muted hidden sm:inline">positive</span>
            </div>
            <div className="w-px h-6 bg-border hidden sm:block" />
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-primary" />
              <span className="text-lg font-bold text-foreground">{metrics.reviews_count.toLocaleString()}</span>
              <span className="text-xs text-muted hidden sm:inline">reviews</span>
            </div>
            {metrics.urgent_count > 0 && (
              <>
                <div className="w-px h-6 bg-border hidden sm:block" />
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-destructive" />
                  <span className="text-lg font-bold text-destructive">{metrics.urgent_count}</span>
                  <span className="text-xs text-muted hidden sm:inline">urgent</span>
                </div>
              </>
            )}
            {metrics.pending_analyses > 0 && (
              <>
                <div className="w-px h-6 bg-border hidden sm:block" />
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-warning" />
                  <span className="text-lg font-bold text-warning">{metrics.pending_analyses}</span>
                  <span className="text-xs text-muted hidden sm:inline">pending</span>
                </div>
              </>
            )}

          </div>
        </div>
      </div>

      {/* New Scrape Form */}
      <div className="bg-card/50 border-b border-border px-4 sm:px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <form onSubmit={handleStartScrape} className="flex flex-col sm:flex-row gap-3">
            <Input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search or paste Google Maps URL"
              className="flex-1"
            />
            <Button type="submit" disabled={scraping || !query.trim()} className="w-full sm:w-auto">
              {scraping ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4 mr-2" />
                  Start Scrape
                </>
              )}
            </Button>
          </form>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <div className="space-y-6">
          {/* Charts Row - Responsive */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Sentiment Trend */}
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <CardTitle>
                    <BarChart3 className="w-5 h-5 text-primary" />
                    Sentiment Trend
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {/* Topic Filter */}
                    {topicsInPeriod.length > 0 && !drillDownDate && (
                      <div className="relative">
                        <button
                          onClick={() => setTopicDropdownOpen(!topicDropdownOpen)}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-card-hover rounded-lg border border-border hover:border-muted transition-colors"
                        >
                          <Filter className="w-3 h-3 text-muted" />
                          <span className="text-foreground">{selectedTopic || 'All Topics'}</span>
                          <ChevronDown className={`w-3 h-3 text-muted transition-transform ${topicDropdownOpen ? 'rotate-180' : ''}`} />
                        </button>
                        {topicDropdownOpen && (
                          <>
                            <div className="fixed inset-0 z-40" onClick={() => setTopicDropdownOpen(false)} />
                            <div className="absolute top-full right-0 mt-1 w-40 bg-card border border-border rounded-lg shadow-lg z-50 max-h-48 overflow-y-auto">
                              <button
                                onClick={() => { setSelectedTopic(null); setTopicDropdownOpen(false) }}
                                className={`w-full text-left px-3 py-2 text-xs hover:bg-card-hover transition-colors ${
                                  selectedTopic === null ? 'bg-primary/10 text-primary font-medium' : 'text-foreground'
                                }`}
                              >
                                All Topics
                              </button>
                              {topicsInPeriod.map((t) => (
                                <button
                                  key={t}
                                  onClick={() => { setSelectedTopic(t); setTopicDropdownOpen(false) }}
                                  className={`w-full text-left px-3 py-2 text-xs hover:bg-card-hover transition-colors capitalize ${
                                    selectedTopic === t ? 'bg-primary/10 text-primary font-medium' : 'text-foreground'
                                  }`}
                                >
                                  {t.replace('_', ' ')}
                                </button>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    )}
                    {/* Zoom Level Selector */}
                    {!drillDownDate && (
                      <div className="flex items-center gap-2">
                        {/* Period quick select */}
                        <select
                          value={trendPeriod}
                          onChange={(e) => setTrendPeriod(e.target.value as TrendPeriod)}
                          className="text-xs bg-card-hover border border-border rounded-lg px-2 py-1 text-foreground"
                        >
                          <option value="7d">7 Days</option>
                          <option value="30d">30 Days</option>
                          <option value="90d">90 Days</option>
                          <option value="1y">1 Year</option>
                          <option value="2y">2 Years</option>
                          <option value="5y">5 Years</option>
                          <option value="all">All Time</option>
                        </select>
                        {/* Zoom level buttons */}
                        <div className="flex items-center gap-1 bg-card-hover rounded-lg p-1">
                          {ZOOM_LEVELS.map((z) => (
                            <button
                              key={z.value}
                              onClick={() => setZoomLevel(z.value)}
                              className={`px-2 py-1 text-xs font-medium rounded transition-colors ${
                                zoomLevel === z.value
                                  ? 'bg-primary text-white'
                                  : 'text-muted hover:text-foreground'
                              }`}
                            >
                              {z.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {drillDownDate ? (
                  /* Drill-Down View */
                  <div className="space-y-3">
                    {/* Header */}
                    <div className="flex items-center justify-between">
                      <button
                        onClick={handleBackToChart}
                        className="flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors"
                      >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Chart
                      </button>
                      <span className="text-sm font-medium text-foreground">
                        {formatDateLabel(drillDownDate)}
                      </span>
                    </div>

                    {/* Anomaly Info */}
                    {(() => {
                      const anomaly = getAnomalyForDate(drillDownDate)
                      if (!anomaly) return null
                      return (
                        <div className={`p-3 rounded-lg border ${
                          anomaly.type === 'drop' ? 'bg-destructive/10 border-destructive/20' : 'bg-success/10 border-success/20'
                        }`}>
                          <div className="flex items-start gap-2">
                            <AlertTriangle className={`w-4 h-4 mt-0.5 ${anomaly.type === 'drop' ? 'text-destructive' : 'text-success'}`} />
                            <div className="flex-1">
                              <div className="text-sm font-medium text-foreground">Anomaly Detected</div>
                              <div className="text-xs text-muted mt-0.5">{anomaly.reason}</div>
                            </div>
                          </div>
                          {anomaly.llm_insight && (
                            <div className="mt-3 pt-3 border-t border-border">
                              <div className="flex items-center gap-1 text-xs font-medium text-foreground mb-1">
                                <Lightbulb className="w-3 h-3 text-warning" />
                                AI Insight
                              </div>
                              <p className="text-xs text-muted">{anomaly.llm_insight.analysis}</p>
                              <div className="mt-2 flex items-start gap-1">
                                <span className="text-primary text-xs">→</span>
                                <p className="text-xs text-foreground">{anomaly.llm_insight.recommendation}</p>
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })()}

                    {/* Sentiment Tabs */}
                    <div className="flex items-center gap-1 bg-card-hover rounded-lg p-1">
                      {[
                        { value: null, label: 'All', count: drillDownReviews.length },
                        { value: 'positive', label: 'Positive', count: drillDownReviews.filter(r => r.sentiment === 'positive').length },
                        { value: 'negative', label: 'Negative', count: drillDownReviews.filter(r => r.sentiment === 'negative').length },
                        { value: 'neutral', label: 'Neutral', count: drillDownReviews.filter(r => r.sentiment === 'neutral').length },
                      ].map((tab) => (
                        <button
                          key={tab.label}
                          onClick={() => handleSentimentFilterChange(tab.value)}
                          className={`px-2 py-1 text-xs font-medium rounded transition-colors ${
                            drillDownSentimentFilter === tab.value
                              ? 'bg-primary text-white'
                              : 'text-muted hover:text-foreground'
                          }`}
                        >
                          {tab.label}: {tab.count}
                        </button>
                      ))}
                    </div>

                    {/* Reviews List */}
                    <div className="max-h-48 overflow-y-auto space-y-2">
                      {drillDownLoading ? (
                        <div className="flex items-center justify-center py-4">
                          <Loader2 className="w-5 h-5 text-muted animate-spin" />
                        </div>
                      ) : drillDownReviews.length > 0 ? (
                        drillDownReviews
                          .filter(r => !drillDownSentimentFilter || r.sentiment === drillDownSentimentFilter)
                          .map((review) => (
                          <div key={review.id} className="p-2 bg-card-hover rounded-lg border border-border">
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-1">
                                {[1,2,3,4,5].map((s) => (
                                  <Star key={s} className={`w-3 h-3 ${s <= (review.rating || 0) ? 'text-yellow-500 fill-yellow-500' : 'text-muted'}`} />
                                ))}
                              </div>
                              <Badge variant={review.sentiment === 'positive' ? 'success' : review.sentiment === 'negative' ? 'destructive' : 'default'}>
                                {review.sentiment}
                              </Badge>
                            </div>
                            <p className="text-xs text-foreground line-clamp-2">{review.text}</p>
                            {(review.topics_positive.length > 0 || review.topics_negative.length > 0) && (
                              <div className="flex flex-wrap gap-1 mt-1">
                                {review.topics_positive.map((t) => (
                                  <span key={t} className="text-[10px] px-1.5 py-0.5 bg-success/10 text-success rounded capitalize">{t.replace('_', ' ')}</span>
                                ))}
                                {review.topics_negative.map((t) => (
                                  <span key={t} className="text-[10px] px-1.5 py-0.5 bg-destructive/10 text-destructive rounded capitalize">{t.replace('_', ' ')}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))
                      ) : (
                        <div className="text-center py-4 text-sm text-muted">No reviews for this date</div>
                      )}
                    </div>
                  </div>
                ) : trendLoading ? (
                  <div className="h-40 flex items-center justify-center">
                    <Loader2 className="w-5 h-5 text-muted animate-spin" />
                  </div>
                ) : trendData.length > 0 ? (
                  (() => {
                    const maxTotal = Math.max(...trendData.map(p => p.total), 1)
                    const labelInterval = Math.max(1, Math.ceil(trendData.length / 12))

                    return (
                      <div className="h-40 flex items-end gap-px overflow-visible">
                        {trendData.map((point, i) => {
                          const barHeight = point.total > 0 ? Math.max((point.total / maxTotal) * 100, 8) : 4
                          const isAnomaly = point.is_anomaly
                          const showLabel = trendData.length <= 14 || i % labelInterval === 0

                          return (
                            <div
                              key={point.date || i}
                              className="flex-1 min-w-0 group cursor-pointer"
                              onClick={() => handleBarClick(point)}
                            >
                              {/* Bar area - h-36 = 144px, leaves 16px for labels */}
                              <div className="h-36 w-full relative">
                                {/* Tooltip */}
                                <div className="absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full hidden group-hover:block z-20 pointer-events-none">
                                  <div className="bg-card border border-border rounded-lg px-2 py-1.5 text-xs shadow-lg whitespace-nowrap">
                                    <div className="font-medium text-foreground">{point.label || point.date}</div>
                                    <div className="text-success">+{point.positive} positive</div>
                                    <div className="text-destructive">-{point.negative} negative</div>
                                    <div className="text-muted">{point.total} total</div>
                                    {isAnomaly && point.anomaly_reason && (
                                      <div className={`mt-1 pt-1 border-t border-border text-[11px] ${point.anomaly_type === 'drop' ? 'text-destructive' : 'text-success'}`}>
                                        {point.anomaly_reason}
                                      </div>
                                    )}
                                    {point.total > 0 && <div className="text-primary text-[10px] mt-1">Click to view</div>}
                                  </div>
                                </div>

                                {/* Anomaly dot - positioned just above bar */}
                                {isAnomaly && (
                                  <div
                                    className={`absolute left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full z-10 ${
                                      point.anomaly_type === 'drop' ? 'bg-destructive' : 'bg-success'
                                    }`}
                                    style={{ bottom: `calc(${Math.min(barHeight, 94)}% + 6px)` }}
                                  />
                                )}

                                {/* Bar */}
                                <div
                                  className={`absolute bottom-0 left-0 right-0 rounded-t transition-colors ${
                                    point.positive_pct >= 70 ? 'bg-success hover:bg-success/80' :
                                    point.positive_pct >= 50 ? 'bg-warning hover:bg-warning/80' :
                                    point.total === 0 ? 'bg-muted/30' : 'bg-destructive hover:bg-destructive/80'
                                  } ${isAnomaly ? 'ring-1 ring-offset-1 ' + (point.anomaly_type === 'drop' ? 'ring-destructive/40' : 'ring-success/40') : ''}`}
                                  style={{ height: `${barHeight}%` }}
                                />
                              </div>

                              {/* Label - fixed 16px height */}
                              <div className="h-4 flex items-center justify-center">
                                {showLabel && (
                                  <span className="text-[10px] text-muted truncate max-w-full px-0.5">{point.label}</span>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )
                  })()
                ) : (
                  <div className="h-40 flex items-center justify-center text-muted text-sm">
                    No data for this period
                  </div>
                )}
                {/* Legend - only show when not in drill-down */}
                {!drillDownDate && (
                  <div className="flex items-center justify-center gap-4 mt-3 text-xs text-muted">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-success" /> &gt;70% positive</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-warning" /> 50-70%</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-destructive" /> &lt;50%</span>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Rating Distribution */}
            <Card>
              <CardHeader>
                <CardTitle>
                  <Star className="w-5 h-5 text-yellow-500" />
                  Rating Distribution
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[5, 4, 3, 2, 1].map((star) => {
                    const pct = overview?.rating_distribution?.[String(star)] || 0
                    return (
                      <div key={star} className="flex items-center gap-3">
                        <span className="text-sm w-8 text-foreground font-medium">{star}<Star className="w-3 h-3 text-yellow-500 inline ml-0.5" /></span>
                        <div className="flex-1 h-3 bg-card-hover rounded-full overflow-hidden">
                          <div
                            className="h-full bg-yellow-500 rounded-full transition-all duration-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-sm text-muted w-12 text-right">{pct}%</span>
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Hot / Cold Row - Responsive */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* What's Hot */}
            <Card>
              <CardHeader>
                <CardTitle>
                  <ThumbsUp className="w-5 h-5 text-success" />
                  What's Hot
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {(overview?.whats_hot || []).length > 0 ? (
                    overview?.whats_hot.map((item, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-success/10 border border-success/20 rounded-lg">
                        <span className="font-medium text-foreground text-sm sm:text-base truncate mr-2">{item.item}</span>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <Badge variant="success">{item.score}</Badge>
                          <span className="text-success text-xs sm:text-sm">{item.mentions} mentions</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-muted text-sm p-3 text-center">
                      No positive topics found yet. Run analysis to see what customers love.
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* What's Not */}
            <Card>
              <CardHeader>
                <CardTitle>
                  <ThumbsDown className="w-5 h-5 text-destructive" />
                  What's Not
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {(overview?.whats_not || []).length > 0 ? (
                    overview?.whats_not.map((item, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
                        <span className="font-medium text-foreground text-sm sm:text-base truncate mr-2">{item.item}</span>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <Badge variant="destructive">{item.score}</Badge>
                          <span className="text-destructive text-xs sm:text-sm">{item.mentions} mentions</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-muted text-sm p-3 text-center">
                      No negative topics found yet. Great news or more data needed!
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Alerts */}
          <Card>
            <CardHeader>
              <CardTitle>
                <Bell className="w-5 h-5 text-warning" />
                Needs Attention
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(overview?.alerts || []).length > 0 ? (
                  overview?.alerts.map((alert, i) => (
                    <div
                      key={i}
                      className={`flex items-center gap-3 p-3 rounded-lg ${
                        alert.type === 'urgent' ? 'bg-destructive/10 border border-destructive/20' :
                        alert.type === 'warning' ? 'bg-warning/10 border border-warning/20' :
                        alert.type === 'processing' ? 'bg-primary/10 border border-primary/20' :
                        'bg-card-hover border border-border'
                      }`}
                    >
                      {alert.type === 'urgent' ? <AlertTriangle className="w-4 h-4 text-destructive flex-shrink-0" /> :
                       alert.type === 'warning' ? <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0" /> :
                       alert.type === 'processing' ? <Clock className="w-4 h-4 text-primary flex-shrink-0" /> :
                       <Bell className="w-4 h-4 text-muted flex-shrink-0" />}
                      <span className="text-foreground text-sm">{alert.message}</span>
                    </div>
                  ))
                ) : (
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-success/10 border border-success/20">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    <span className="text-foreground text-sm">All caught up! No urgent items.</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Recent Jobs */}
          <Card>
            <CardHeader>
              <CardTitle>
                <Briefcase className="w-5 h-5 text-primary" />
                Recent Jobs
              </CardTitle>
            </CardHeader>
            <CardContent>
              {jobs.length === 0 ? (
                <p className="text-muted text-sm text-center py-4">No jobs yet. Start a scrape job to analyze reviews.</p>
              ) : (
                <div className="space-y-2">
                  {jobs.map((job) => (
                    <div
                      key={job.id}
                      className="flex flex-col sm:flex-row sm:items-center justify-between p-3 bg-card-hover rounded-lg gap-2"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm font-medium text-foreground truncate">{job.query}</span>
                        <Badge variant={
                          job.status === 'completed' ? 'success' :
                          job.status === 'failed' ? 'destructive' :
                          'default'
                        }>
                          {job.status}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-muted">
                        <span className="flex items-center gap-1">
                          <MapPin className="w-3 h-3" />
                          {job.places_found || 0}
                        </span>
                        <span className="flex items-center gap-1">
                          <MessageSquare className="w-3 h-3" />
                          {job.reviews_total || 0}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Job Status Summary */}
          <Card>
            <CardHeader>
              <CardTitle>
                <PieChart className="w-5 h-5 text-primary" />
                Job Status Overview
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                {[
                  { status: 'pending', icon: Clock, color: 'text-muted', bg: 'bg-card-hover border-border' },
                  { status: 'scraping', icon: Loader2, color: 'text-primary', bg: 'bg-primary/10 border-primary/20' },
                  { status: 'processing', icon: Cog, color: 'text-primary', bg: 'bg-primary/10 border-primary/20' },
                  { status: 'completed', icon: CheckCircle2, color: 'text-success', bg: 'bg-success/10 border-success/20' },
                  { status: 'failed', icon: XCircle, color: 'text-destructive', bg: 'bg-destructive/10 border-destructive/20' },
                ].map(({ status, icon: Icon, color, bg }) => (
                  <div key={status} className={`p-3 rounded-lg border text-center ${bg}`}>
                    <Icon className={`w-4 h-4 mx-auto mb-1 ${color} ${status === 'scraping' ? 'animate-spin' : ''}`} />
                    <div className={`text-lg font-bold ${color}`}>
                      {overview?.scrape_jobs?.[status] || 0}
                    </div>
                    <div className="text-xs text-muted capitalize">{status}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
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
