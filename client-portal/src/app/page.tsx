'use client'

import { useEffect, useState } from 'react'
import { AuthGuard } from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import {
  fetchInsights,
  fetchPlaces,
  fetchSentimentTrend,
  fetchDateReviews,
  fetchReviewSearch,
  InsightsData,
  ZoomLevel,
  TrendDataPoint,
  Anomaly,
  DateReview,
  Place
} from '@/lib/api'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Star,
  TrendingUp,
  TrendingDown,
  MessageSquare,
  AlertTriangle,
  Clock,
  BarChart3,
  ThumbsUp,
  ThumbsDown,
  LogOut,
  MapPin,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Loader2,
  CheckCircle2,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowDown,
  Minus,
  Plus,
  Lightbulb,
  Calendar,
  ClipboardCheck,
  Package,
  Users,
  Heart,
} from 'lucide-react'

// Arabic day names
const DAY_AR: Record<string, string> = {
  Sunday: 'الأحد', Monday: 'الاثنين', Tuesday: 'الثلاثاء',
  Wednesday: 'الأربعاء', Thursday: 'الخميس', Friday: 'الجمعة', Saturday: 'السبت',
}

const ZOOM_LEVELS: { value: ZoomLevel; label: string }[] = [
  { value: 'day', label: 'يوم' },
  { value: 'week', label: 'أسبوع' },
  { value: 'month', label: 'شهر' },
  { value: 'year', label: 'سنة' },
]

function formatDateLabel(dateStr: string): string {
  if (!dateStr) return ''
  if (/^\d{4}$/.test(dateStr)) return dateStr
  if (/^\d{4}-\d{2}$/.test(dateStr)) {
    const [year, month] = dateStr.split('-')
    return new Date(parseInt(year), parseInt(month) - 1, 1).toLocaleDateString('ar-SA', { month: 'short', year: '2-digit' })
  }
  if (/^\d{4}-W\d{2}$/i.test(dateStr)) {
    const [year, week] = dateStr.toUpperCase().split('-W')
    return `W${parseInt(week)}`
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return new Date(dateStr + 'T00:00:00').toLocaleDateString('ar-SA', { month: 'short', day: 'numeric' })
  }
  return dateStr
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5" dir="ltr">
      {[1, 2, 3, 4, 5].map((s) => (
        <Star key={s} className={`w-2.5 h-2.5 ${s <= (rating || 0) ? 'text-yellow-500 fill-yellow-500' : 'text-muted/30'}`} />
      ))}
    </div>
  )
}

function TrendArrow({ trend }: { trend: string }) {
  if (trend === 'increasing') return <ArrowUp className="w-3 h-3 text-destructive" />
  if (trend === 'decreasing') return <ArrowDown className="w-3 h-3 text-success" />
  return <Minus className="w-3 h-3 text-muted" />
}

function SeverityDot({ severity }: { severity: string }) {
  const color = severity === 'high' ? 'bg-destructive' : severity === 'medium' ? 'bg-warning' : 'bg-success'
  return <span className={`w-1.5 h-1.5 rounded-full ${color} inline-block mt-1.5 flex-shrink-0`} />
}

// ===== Reusable Inline Drill-Down =====
function InlineDrillDown({
  title,
  placeId,
  baseParams,
  onClose,
}: {
  title: string
  placeId: string
  baseParams: Record<string, any>
  onClose: () => void
}) {
  const [reviews, setReviews] = useState<DateReview[]>([])
  const [loading, setLoading] = useState(true)
  const [sentimentFilter, setSentimentFilter] = useState<string | null>(null)

  const load = async (sentiment?: string | null) => {
    setLoading(true)
    try {
      const result = await fetchReviewSearch({
        place_id: placeId,
        ...baseParams,
        sentiment: sentiment || undefined,
        limit: 20,
      })
      setReviews(result.reviews)
    } catch { setReviews([]) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-foreground truncate">{title}</span>
        <button onClick={onClose} className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 flex-shrink-0">
          رجوع <ArrowLeft className="w-3 h-3" />
        </button>
      </div>
      <div className="flex items-center gap-0.5 bg-card-hover rounded p-0.5" dir="ltr">
        {[
          { value: null, label: 'الكل' },
          { value: 'positive', label: 'إيجابي' },
          { value: 'negative', label: 'سلبي' },
          { value: 'neutral', label: 'محايد' },
        ].map(tab => (
          <button
            key={tab.label}
            onClick={() => { setSentimentFilter(tab.value); load(tab.value) }}
            className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${
              sentimentFilter === tab.value ? 'bg-primary text-white' : 'text-muted hover:text-foreground'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="max-h-60 overflow-y-auto space-y-1">
        {loading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="w-4 h-4 text-muted animate-spin" />
          </div>
        ) : reviews.length > 0 ? reviews.map(review => (
          <div key={review.id} className="p-2 bg-card-hover rounded border border-border">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <Badge
                  variant={review.sentiment === 'positive' ? 'success' : review.sentiment === 'negative' ? 'destructive' : 'default'}
                  className="text-[9px] px-1 py-0"
                >
                  {review.sentiment === 'positive' ? 'إيجابي' : review.sentiment === 'negative' ? 'سلبي' : 'محايد'}
                </Badge>
                <span className="text-[10px] text-muted truncate max-w-[80px]">{review.author}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-muted" dir="ltr">{review.date}</span>
                <StarRating rating={review.rating} />
              </div>
            </div>
            {review.text ? (
              <p className="text-xs text-foreground leading-relaxed">{review.text}</p>
            ) : review.summary_ar || review.summary_en ? (
              <p className="text-xs text-foreground/70 leading-relaxed italic">{review.summary_ar || review.summary_en}</p>
            ) : (
              <p className="text-[10px] text-muted italic">لا يوجد نص</p>
            )}
          </div>
        )) : (
          <div className="flex items-center gap-1.5 justify-center py-3 text-xs text-muted">
            <CheckCircle2 className="w-3.5 h-3.5 text-success" />
            لا توجد تقييمات
          </div>
        )}
      </div>
    </div>
  )
}

// ===== SECTION: Weekly Plan (Side Panel) =====
function WeeklyPlanPanel({ data }: { data: InsightsData }) {
  const plan = data.weekly_plan
  if (!plan) return null

  return (
    <div className="sticky top-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2 px-1">
        <div className="w-7 h-7 rounded-lg bg-warning/15 flex items-center justify-center">
          <Lightbulb className="w-4 h-4 text-warning" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-foreground">الخطة الأسبوعية</h2>
          <p className="text-[10px] text-muted">خطة عمل مبنية على تحليل التقييمات</p>
        </div>
      </div>

      {/* Summary */}
      {(plan.summary_ar || plan.summary_en) && (
        <div className="p-3 bg-warning/5 border border-warning/15 rounded-xl">
          <p className="text-[11px] text-foreground/80 leading-relaxed">{plan.summary_ar || plan.summary_en}</p>
        </div>
      )}

      {/* Priorities */}
      {plan.priorities.length > 0 ? (
        <div className="space-y-2">
          {plan.priorities.map((p, i) => {
            const isUrgent = p.type === 'urgent'
            const isProblem = p.type === 'problem_product'
            return (
              <div key={i} className={`group relative p-3 rounded-xl border transition-colors ${
                isUrgent ? 'bg-destructive/5 border-destructive/20 hover:bg-destructive/10' :
                isProblem ? 'bg-warning/5 border-warning/20 hover:bg-warning/10' :
                'bg-card-hover/50 border-border hover:bg-card-hover'
              }`}>
                <div className="flex items-start gap-2.5">
                  <span className={`text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
                    isUrgent ? 'bg-destructive text-white' :
                    isProblem ? 'bg-warning text-white' :
                    'bg-primary/15 text-primary'
                  }`} dir="ltr">{p.priority}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-foreground">{p.title_ar || p.title_en}</div>
                    <div className="text-[11px] text-muted mt-1 leading-relaxed">{p.detail_ar || p.detail_en}</div>
                  </div>
                </div>
                {isUrgent && (
                  <div className="absolute top-2.5 left-2.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-destructive block animate-pulse" />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="flex items-center gap-2 p-3 bg-success/5 border border-success/20 rounded-xl text-xs">
          <CheckCircle2 className="w-4 h-4 text-success" />
          <span className="text-foreground">لا توجد مشاكل كبيرة هذا الأسبوع!</span>
        </div>
      )}
    </div>
  )
}

// ===== SECTION: Urgent Issues =====
function UrgentSection({ data }: { data: InsightsData }) {
  const [expanded, setExpanded] = useState(false)
  const [expandedItem, setExpandedItem] = useState<string | null>(null)
  const urgent = data.urgent_issues
  if (!urgent) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-destructive" /> عاجل</CardTitle>
          {urgent.total > 0 && <Badge variant="destructive" className="text-[10px] px-1.5 py-0" dir="ltr">{urgent.total}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {urgent.items.length > 0 ? (
          <div className="space-y-1.5">
            {(expanded ? urgent.items : urgent.items.slice(0, 4)).map((item, i) => (
              <div
                key={i}
                className="p-2 bg-destructive/5 border border-destructive/10 rounded-lg cursor-pointer hover:bg-destructive/10 transition-colors"
                onClick={() => setExpandedItem(expandedItem === item.review_id ? null : item.review_id)}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[10px] text-muted truncate max-w-[120px]">{item.author}</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted" dir="ltr">{item.review_date}</span>
                    <StarRating rating={item.rating} />
                  </div>
                </div>
                <p className="text-xs text-foreground line-clamp-2">{item.summary_ar || item.summary_en}</p>
                {(item.action_ar || item.action_en) && (
                  <p className="text-[10px] text-primary mt-0.5 line-clamp-1">{item.action_ar || item.action_en}</p>
                )}
                {expandedItem === item.review_id && item.text && (
                  <div className="mt-1.5 pt-1.5 border-t border-destructive/20">
                    <p className="text-[10px] text-muted leading-relaxed">{item.text}</p>
                  </div>
                )}
              </div>
            ))}
            {urgent.items.length > 4 && (
              <button onClick={() => setExpanded(!expanded)} className="text-[10px] text-primary hover:underline">
                {expanded ? 'عرض أقل' : `عرض الكل ${urgent.items.length}`}
              </button>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 p-2 bg-success/10 border border-success/20 rounded-lg text-xs">
            <CheckCircle2 className="w-3.5 h-3.5 text-success" />
            <span className="text-foreground">لا توجد مشاكل عاجلة!</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Action Items =====
function ActionsSection({ data }: { data: InsightsData }) {
  const [expanded, setExpanded] = useState(false)
  const [expandedItem, setExpandedItem] = useState<string | null>(null)
  const actions = data.action_checklist
  if (!actions) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2"><ClipboardCheck className="w-4 h-4 text-primary" /> إجراءات مطلوبة</CardTitle>
          {actions.total > 0 && <Badge variant="default" className="text-[10px] px-1.5 py-0" dir="ltr">{actions.total}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {actions.items.length > 0 ? (
          <div className="space-y-1.5">
            {(expanded ? actions.items : actions.items.slice(0, 4)).map((item, i) => (
              <div
                key={i}
                className={`p-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                  item.urgent ? 'bg-destructive/5 border-destructive/10 hover:bg-destructive/10' : 'bg-card-hover border-border hover:bg-card-hover/80'
                }`}
                onClick={() => setExpandedItem(expandedItem === item.review_id ? null : item.review_id)}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted truncate max-w-[100px]">{item.author}</span>
                    {item.urgent && <span className="text-[9px] px-1 py-0 bg-destructive/20 text-destructive rounded">عاجل</span>}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted" dir="ltr">{item.review_date}</span>
                    <StarRating rating={item.rating} />
                  </div>
                </div>
                {(item.action_ar || item.action_en) && <p className="text-foreground line-clamp-2">{item.action_ar || item.action_en}</p>}
                {expandedItem === item.review_id && item.text && (
                  <div className="mt-1.5 pt-1.5 border-t border-border">
                    <p className="text-[10px] text-muted leading-relaxed">{item.text}</p>
                  </div>
                )}
              </div>
            ))}
            {actions.items.length > 4 && (
              <button onClick={() => setExpanded(!expanded)} className="text-[10px] text-primary hover:underline">
                {expanded ? 'عرض أقل' : `عرض الكل ${actions.items.length}`}
              </button>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 p-2 bg-success/10 border border-success/20 rounded-lg text-xs">
            <CheckCircle2 className="w-3.5 h-3.5 text-success" />
            <span className="text-foreground">لا توجد إجراءات معلقة!</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== Helpers for date pagination =====
const DEFAULT_PAGE_SIZE = 10
const MIN_PAGE_SIZE = 3
const MAX_PAGE_SIZE = 30

function getDateRange(zoom: ZoomLevel, page: number, size: number): { start: string; end: string; label: string } {
  const today = new Date()
  if (zoom === 'day') {
    const end = new Date(today)
    end.setDate(end.getDate() - page * size)
    const start = new Date(end)
    start.setDate(start.getDate() - size + 1)
    return { start: fmt(start), end: fmt(end), label: `${fmtShort(start)} – ${fmtShort(end)}` }
  }
  if (zoom === 'week') {
    const end = new Date(today)
    end.setDate(end.getDate() - page * size * 7)
    const start = new Date(end)
    start.setDate(start.getDate() - size * 7 + 1)
    return { start: fmt(start), end: fmt(end), label: `${fmtShort(start)} – ${fmtShort(end)}` }
  }
  if (zoom === 'month') {
    const endMonth = new Date(today.getFullYear(), today.getMonth() - page * size + 1, 0)
    const startMonth = new Date(today.getFullYear(), today.getMonth() - page * size - size + 1, 1)
    return { start: fmt(startMonth), end: fmt(endMonth), label: `${fmtMonth(startMonth)} – ${fmtMonth(endMonth)}` }
  }
  // year
  const endYear = today.getFullYear() - page * size
  const startYear = endYear - size + 1
  return { start: `${startYear}-01-01`, end: `${endYear}-12-31`, label: `${startYear} – ${endYear}` }
}

function fmt(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function fmtShort(d: Date): string {
  return d.toLocaleDateString('ar-SA', { month: 'short', day: 'numeric' })
}
function fmtMonth(d: Date): string {
  return d.toLocaleDateString('ar-SA', { month: 'short', year: 'numeric' })
}

// ===== SECTION: Sentiment Trend =====
function SentimentTrendSection({ selectedPlace }: { selectedPlace: string }) {
  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>('month')
  const [page, setPage] = useState(0) // 0 = most recent
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [trendData, setTrendData] = useState<TrendDataPoint[]>([])
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendAnomalies, setTrendAnomalies] = useState<Anomaly[]>([])
  const [topicsInPeriod, setTopicsInPeriod] = useState<string[]>([])
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null)
  const [drillDownDate, setDrillDownDate] = useState<string | null>(null)
  const [drillDownReviews, setDrillDownReviews] = useState<DateReview[]>([])
  const [drillDownLoading, setDrillDownLoading] = useState(false)
  const [drillDownSentimentFilter, setDrillDownSentimentFilter] = useState<string | null>(null)

  const range = getDateRange(zoomLevel, page, pageSize)

  const loadTrend = async () => {
    setTrendLoading(true)
    try {
      const response = await fetchSentimentTrend({
        period: 'custom',
        zoom: zoomLevel,
        place_id: selectedPlace,
        topic: selectedTopic || undefined,
        start_date: range.start,
        end_date: range.end,
      })
      setTrendData(response.data)
      setTrendAnomalies(response.anomalies)
      setTopicsInPeriod(response.topics_in_period)
    } catch { setTrendData([]); setTrendAnomalies([]) }
    finally { setTrendLoading(false) }
  }

  const loadDrillDown = async (date: string, sentiment?: string | null) => {
    setDrillDownLoading(true)
    try {
      const response = await fetchDateReviews(date, { sentiment: sentiment || undefined, topic: selectedTopic || undefined, place_id: selectedPlace })
      setDrillDownReviews(response.reviews)
    } catch { setDrillDownReviews([]) }
    finally { setDrillDownLoading(false) }
  }

  useEffect(() => { loadTrend() }, [zoomLevel, page, pageSize, selectedTopic, selectedPlace])

  const handleZoomChange = (z: ZoomLevel) => { setZoomLevel(z); setPage(0) }
  const handleSizeChange = (delta: number) => {
    setPageSize(s => Math.min(MAX_PAGE_SIZE, Math.max(MIN_PAGE_SIZE, s + delta)))
    setPage(0)
  }
  const getAnomalyForDate = (date: string) => trendAnomalies.find(a => a.date === date)

  return (
    <Card>
      <CardHeader className="py-3 px-4 pb-1">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm flex items-center gap-2"><BarChart3 className="w-4 h-4 text-primary" /> اتجاه المشاعر</CardTitle>
          {!drillDownDate && (
            <div className="flex items-center bg-card-hover rounded p-0.5" dir="ltr">
              {ZOOM_LEVELS.map(z => (
                <button key={z.value} onClick={() => handleZoomChange(z.value)} className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${zoomLevel === z.value ? 'bg-primary text-white' : 'text-muted hover:text-foreground'}`}>{z.label}</button>
              ))}
            </div>
          )}
        </div>
        {/* Navigation bar */}
        {!drillDownDate && (
          <div className="flex items-center justify-between mt-2">
            <div className="flex items-center gap-0.5">
              <button onClick={() => setPage(p => p + 1)} className="p-1 rounded hover:bg-card-hover text-muted hover:text-foreground transition-colors" title="أقدم">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => handleSizeChange(-2)} disabled={pageSize <= MIN_PAGE_SIZE} className={`p-0.5 rounded hover:bg-card-hover transition-colors ${pageSize <= MIN_PAGE_SIZE ? 'text-muted/30 cursor-not-allowed' : 'text-muted hover:text-foreground'}`} title="تكبير (عناصر أقل)">
                <Minus className="w-3.5 h-3.5" />
              </button>
              <div className="text-center">
                <span className="text-xs text-foreground font-medium" dir="ltr">{range.label}</span>
                <div className="text-[9px] text-muted" dir="ltr">{pageSize} {zoomLevel === 'day' ? 'يوم' : zoomLevel === 'week' ? 'أسبوع' : zoomLevel === 'month' ? 'شهر' : 'سنة'}</div>
              </div>
              <button onClick={() => handleSizeChange(2)} disabled={pageSize >= MAX_PAGE_SIZE} className={`p-0.5 rounded hover:bg-card-hover transition-colors ${pageSize >= MAX_PAGE_SIZE ? 'text-muted/30 cursor-not-allowed' : 'text-muted hover:text-foreground'}`} title="تصغير (عناصر أكثر)">
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="flex items-center gap-0.5">
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} className={`p-1 rounded hover:bg-card-hover transition-colors ${page === 0 ? 'text-muted/30 cursor-not-allowed' : 'text-muted hover:text-foreground'}`} title="أحدث">
                <ChevronLeft className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
        {/* Topic chips */}
        {!drillDownDate && topicsInPeriod.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            <button onClick={() => setSelectedTopic(null)} className={`px-2 py-0.5 text-[10px] rounded-full transition-colors ${selectedTopic === null ? 'bg-primary text-white' : 'bg-card-hover text-muted hover:text-foreground border border-border'}`}>الكل</button>
            {topicsInPeriod.map(t => (
              <button key={t} onClick={() => setSelectedTopic(selectedTopic === t ? null : t)} className={`px-2 py-0.5 text-[10px] rounded-full capitalize transition-colors ${selectedTopic === t ? 'bg-primary text-white' : 'bg-card-hover text-muted hover:text-foreground border border-border'}`}>{t.replace('_', ' ')}</button>
            ))}
          </div>
        )}
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-2">
        {drillDownDate ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-foreground">{formatDateLabel(drillDownDate)}</span>
              <button onClick={() => { setDrillDownDate(null); setDrillDownReviews([]) }} className="flex items-center gap-1 text-xs text-primary hover:text-primary/80">رجوع <ArrowLeft className="w-3 h-3" /></button>
            </div>
            {(() => {
              const anomaly = getAnomalyForDate(drillDownDate)
              if (!anomaly) return null
              return (
                <div className={`p-2 rounded-lg border text-xs ${anomaly.type === 'drop' ? 'bg-destructive/10 border-destructive/20' : 'bg-success/10 border-success/20'}`}>
                  <div className="flex items-start gap-1.5">
                    <AlertTriangle className={`w-3 h-3 mt-0.5 ${anomaly.type === 'drop' ? 'text-destructive' : 'text-success'}`} />
                    <div>
                      <span className="font-medium text-foreground">تنبيه: </span>
                      <span className="text-muted">{anomaly.reason}</span>
                    </div>
                  </div>
                  {anomaly.llm_insight && (
                    <div className="mt-1.5 pt-1.5 border-t border-border text-[10px]">
                      <p className="text-muted">{anomaly.llm_insight.analysis_ar || anomaly.llm_insight.analysis}</p>
                      <p className="text-foreground mt-0.5">{anomaly.llm_insight.recommendation_ar || anomaly.llm_insight.recommendation}</p>
                    </div>
                  )}
                </div>
              )
            })()}
            <div className="flex items-center gap-0.5 bg-card-hover rounded p-0.5" dir="ltr">
              {[
                { value: null, label: 'الكل' },
                { value: 'positive', label: 'إيجابي' },
                { value: 'negative', label: 'سلبي' },
                { value: 'neutral', label: 'محايد' },
              ].map(tab => (
                <button key={tab.label} onClick={() => { setDrillDownSentimentFilter(tab.value); if (drillDownDate) loadDrillDown(drillDownDate, tab.value) }} className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${drillDownSentimentFilter === tab.value ? 'bg-primary text-white' : 'text-muted hover:text-foreground'}`}>{tab.label}</button>
              ))}
            </div>
            <div className="max-h-40 overflow-y-auto space-y-1">
              {drillDownLoading ? (
                <div className="flex items-center justify-center py-3"><Loader2 className="w-4 h-4 text-muted animate-spin" /></div>
              ) : drillDownReviews.filter(r => !drillDownSentimentFilter || r.sentiment === drillDownSentimentFilter).map(review => (
                <div key={review.id} className="p-1.5 bg-card-hover rounded border border-border">
                  <div className="flex items-center justify-between mb-0.5">
                    <Badge variant={review.sentiment === 'positive' ? 'success' : review.sentiment === 'negative' ? 'destructive' : 'default'} className="text-[9px] px-1 py-0">
                      {review.sentiment === 'positive' ? 'إيجابي' : review.sentiment === 'negative' ? 'سلبي' : 'محايد'}
                    </Badge>
                    <StarRating rating={review.rating} />
                  </div>
                  <p className="text-[10px] text-foreground line-clamp-2">{review.text}</p>
                </div>
              ))}
            </div>
          </div>
        ) : trendLoading ? (
          <div className="h-32 flex items-center justify-center"><Loader2 className="w-4 h-4 text-muted animate-spin" /></div>
        ) : trendData.length > 0 ? (
          (() => {
            const maxTotal = Math.max(...trendData.map(p => p.total), 1)
            return (
              <>
                <div className="h-32 flex items-end gap-1 overflow-visible" dir="ltr">
                  {trendData.map((point, i) => {
                    const barHeight = point.total > 0 ? Math.max((point.total / maxTotal) * 100, 8) : 4
                    const isAnomaly = point.is_anomaly
                    return (
                      <div key={point.date || i} className="flex-1 min-w-0 group cursor-pointer" onClick={() => { if (point.total > 0) { setDrillDownDate(point.date); setDrillDownSentimentFilter(null); loadDrillDown(point.date) } }}>
                        <div className="h-28 w-full relative">
                          <div className="absolute -top-1 left-1/2 -translate-x-1/2 -translate-y-full hidden group-hover:block z-20 pointer-events-none">
                            <div className="bg-card border border-border rounded px-1.5 py-1 text-[10px] shadow-lg whitespace-nowrap" dir="ltr">
                              <div className="font-medium text-foreground">{point.label || point.date}</div>
                              <div className="text-success">+{point.positive}</div>
                              <div className="text-destructive">-{point.negative}</div>
                              <div className="text-muted">{point.total} تقييم</div>
                            </div>
                          </div>
                          {isAnomaly && <div className={`absolute left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full z-10 ${point.anomaly_type === 'drop' ? 'bg-destructive' : 'bg-success'}`} style={{ bottom: `calc(${Math.min(barHeight, 94)}% + 4px)` }} />}
                          <div className={`absolute bottom-0 left-0 right-0 rounded-t-sm transition-colors ${point.positive_pct >= 70 ? 'bg-success hover:bg-success/80' : point.positive_pct >= 50 ? 'bg-warning hover:bg-warning/80' : point.total === 0 ? 'bg-muted/20' : 'bg-destructive hover:bg-destructive/80'} ${isAnomaly ? 'ring-1 ring-offset-1 ' + (point.anomaly_type === 'drop' ? 'ring-destructive/40' : 'ring-success/40') : ''}`} style={{ height: `${barHeight}%` }} />
                        </div>
                        <div className="h-4 flex items-center justify-center">
                          <span className="text-[8px] text-muted truncate">{point.label}</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
                <div className="flex items-center justify-center gap-3 mt-1 text-[10px] text-muted" dir="ltr">
                  <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded bg-success" /> &gt;70%</span>
                  <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded bg-warning" /> 50-70%</span>
                  <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded bg-destructive" /> &lt;50%</span>
                </div>
              </>
            )
          })()
        ) : (
          <div className="h-32 flex items-center justify-center text-muted text-xs">لا توجد بيانات لهذه الفترة</div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Day of Week =====
const DAY_TO_WEEKDAY: Record<string, number> = {
  Monday: 0, Tuesday: 1, Wednesday: 2, Thursday: 3,
  Friday: 4, Saturday: 5, Sunday: 6,
}

function DayOfWeekSection({ data, placeId }: { data: InsightsData; placeId: string }) {
  const tp = data.time_patterns
  const [drillDown, setDrillDown] = useState<{ title: string; params: Record<string, any> } | null>(null)
  if (!tp) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-sm flex items-center gap-2"><Calendar className="w-4 h-4 text-primary" /> حسب اليوم</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {drillDown ? (
          <InlineDrillDown title={drillDown.title} placeId={placeId} baseParams={drillDown.params} onClose={() => setDrillDown(null)} />
        ) : (
          <>
            <div className="space-y-1.5">
              {tp.day_of_week.map((d, i) => {
                const maxCount = Math.max(...tp.day_of_week.map(x => x.review_count), 1)
                const pct = (d.review_count / maxCount) * 100
                const dayAr = d.day_ar || DAY_AR[d.day] || d.day
                return (
                  <div
                    key={i}
                    className="flex items-center gap-2 cursor-pointer hover:bg-card-hover/50 rounded px-1 -mx-1 transition-colors"
                    onClick={() => setDrillDown({ title: dayAr, params: { day_of_week: DAY_TO_WEEKDAY[d.day] ?? i } })}
                  >
                    <span className={`text-[10px] w-12 font-medium ${d.day === tp.busiest_day ? 'text-primary' : d.day === tp.worst_day ? 'text-destructive' : 'text-foreground'}`}>{dayAr}</span>
                    <div className="flex-1 h-3 bg-card-hover rounded-full overflow-hidden" dir="ltr">
                      <div className={`h-full rounded-full ${d.negative_pct > 20 ? 'bg-destructive/60' : d.negative_pct > 10 ? 'bg-warning/60' : 'bg-success/60'}`} style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-[10px] text-muted w-6 text-left" dir="ltr">{d.review_count}</span>
                    <span className="text-[10px] w-7 text-left" dir="ltr">{d.avg_rating ? `${d.avg_rating}★` : '—'}</span>
                    <ChevronLeft className="w-3 h-3 text-muted/40" />
                  </div>
                )
              })}
            </div>
            <div className="mt-2 flex items-center gap-3 text-[10px] text-muted">
              {tp.busiest_day && <span>الأكثر: <span className="text-primary font-medium">{DAY_AR[tp.busiest_day] || tp.busiest_day}</span></span>}
              {tp.worst_day && <span>الأسوأ: <span className="text-destructive font-medium">{DAY_AR[tp.worst_day] || tp.worst_day}</span></span>}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Recurring Complaints =====
function RecurringComplaintsSection({ data, placeId }: { data: InsightsData; placeId: string }) {
  const complaints = data.recurring_complaints
  const [drillDown, setDrillDown] = useState<{ title: string; params: Record<string, any> } | null>(null)
  if (!complaints || complaints.items.length === 0) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-sm flex items-center gap-2"><TrendingDown className="w-4 h-4 text-destructive" /> شكاوى متكررة</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {drillDown ? (
          <InlineDrillDown title={drillDown.title} placeId={placeId} baseParams={drillDown.params} onClose={() => setDrillDown(null)} />
        ) : (
          <div className="space-y-1.5">
            {complaints.items.slice(0, 8).map((item, i) => {
              const maxCount = Math.max(...complaints.items.map(x => x.count), 1)
              return (
                <div
                  key={i}
                  className="flex items-center gap-2 cursor-pointer hover:bg-card-hover/50 rounded px-1 -mx-1 transition-colors"
                  onClick={() => setDrillDown({ title: item.topic_display, params: { topic: item.topic, sentiment: 'negative' } })}
                >
                  <span className="text-[10px] w-16 text-foreground font-medium capitalize truncate">{item.topic_display}</span>
                  <div className="flex-1 h-2.5 bg-card-hover rounded-full overflow-hidden" dir="ltr">
                    <div className="h-full bg-destructive/50 rounded-full" style={{ width: `${(item.count / maxCount) * 100}%` }} />
                  </div>
                  <span className="text-[10px] text-muted w-6 text-left" dir="ltr">{item.count}</span>
                  <TrendArrow trend={item.trend} />
                  <ChevronLeft className="w-3 h-3 text-muted/40" />
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Top Praised Products =====
function TopPraisedSection({ data, placeId }: { data: InsightsData; placeId: string }) {
  const praised = data.top_praised
  const [drillDown, setDrillDown] = useState<{ title: string; params: Record<string, any> } | null>(null)
  if (!praised || praised.items.length === 0) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-sm flex items-center gap-2"><ThumbsUp className="w-4 h-4 text-success" /> الأكثر إشادة</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {drillDown ? (
          <InlineDrillDown title={drillDown.title} placeId={placeId} baseParams={drillDown.params} onClose={() => setDrillDown(null)} />
        ) : (
          <div className="space-y-1">
            {praised.items.slice(0, 8).map((item, i) => (
              <div
                key={i}
                className="flex items-center gap-2 py-1 border-b border-border/50 last:border-0 cursor-pointer hover:bg-card-hover/50 rounded px-1 -mx-1 transition-colors"
                onClick={() => setDrillDown({ title: item.product_name, params: { product_id: item.product_id, sentiment: 'positive' } })}
              >
                <span className="text-xs text-foreground font-medium truncate flex-1 min-w-0">{item.product_name}</span>
                <span className="text-[10px] text-muted truncate max-w-[60px]">{item.category_name_ar || item.category_name}</span>
                <div className="w-12 h-1.5 bg-card-hover rounded-full overflow-hidden flex-shrink-0" dir="ltr">
                  <div className="h-full bg-success rounded-full" style={{ width: `${item.positive_pct}%` }} />
                </div>
                <span className="text-[10px] text-success font-medium w-8 text-left" dir="ltr">{item.positive_pct}%</span>
                <span className="text-[10px] text-muted w-4 text-left" dir="ltr">{item.total_mentions}</span>
                <ChevronLeft className="w-3 h-3 text-muted/40" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Problem Products =====
function ProblemProductsSection({ data, placeId }: { data: InsightsData; placeId: string }) {
  const problems = data.problem_products
  const [drillDown, setDrillDown] = useState<{ title: string; params: Record<string, any> } | null>(null)
  if (!problems || problems.items.length === 0) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-sm flex items-center gap-2"><ThumbsDown className="w-4 h-4 text-destructive" /> منتجات بمشاكل</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {drillDown ? (
          <InlineDrillDown title={drillDown.title} placeId={placeId} baseParams={drillDown.params} onClose={() => setDrillDown(null)} />
        ) : (
          <div className="space-y-1">
            {problems.items.slice(0, 8).map((item, i) => (
              <div
                key={i}
                className="flex items-center gap-2 py-1 border-b border-border/50 last:border-0 cursor-pointer hover:bg-card-hover/50 rounded px-1 -mx-1 transition-colors"
                onClick={() => setDrillDown({ title: item.product_name, params: { product_id: item.product_id, sentiment: 'negative' } })}
              >
                <span className="text-xs text-foreground font-medium truncate flex-1 min-w-0">{item.product_name}</span>
                <span className="text-[10px] text-muted truncate max-w-[60px]">{item.category_name_ar || item.category_name}</span>
                <div className="w-12 h-1.5 bg-card-hover rounded-full overflow-hidden flex-shrink-0" dir="ltr">
                  <div className="h-full bg-destructive rounded-full" style={{ width: `${item.negative_pct}%` }} />
                </div>
                <span className="text-[10px] text-destructive font-medium w-8 text-left" dir="ltr">{item.negative_pct}%</span>
                <span className="text-[10px] text-muted w-4 text-left" dir="ltr">{item.total_mentions}</span>
                <ChevronLeft className="w-3 h-3 text-muted/40" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Staff =====
function StaffSection({ data, placeId }: { data: InsightsData; placeId: string }) {
  const staff = data.praised_employees
  const [drillDown, setDrillDown] = useState<{ title: string; params: Record<string, any> } | null>(null)
  if (!staff || (staff.staff_positive_mentions === 0 && staff.staff_negative_mentions === 0)) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2"><Users className="w-4 h-4 text-primary" /> الموظفين</CardTitle>
          <span className="text-xs font-bold text-foreground" dir="ltr">{staff.staff_sentiment_ratio}% إيجابي</span>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {drillDown ? (
          <InlineDrillDown title={drillDown.title} placeId={placeId} baseParams={drillDown.params} onClose={() => setDrillDown(null)} />
        ) : (
          <>
            <div className="h-1.5 bg-card-hover rounded-full overflow-hidden mb-3" dir="ltr">
              <div className="h-full bg-success rounded-full" style={{ width: `${staff.staff_sentiment_ratio}%` }} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              {staff.positive_samples.length > 0 && (
                <div
                  className="cursor-pointer hover:bg-success/5 rounded p-1 -m-1 transition-colors"
                  onClick={() => setDrillDown({ title: 'إشادة بالموظفين', params: { topic: 'staff', sentiment: 'positive' } })}
                >
                  <div className="text-[10px] font-medium text-success mb-1 flex items-center gap-1">إشادة ({staff.staff_positive_mentions}) <ChevronLeft className="w-2.5 h-2.5 text-success/40" /></div>
                  {staff.positive_samples.slice(0, 2).map((s, i) => (
                    <p key={i} className="text-[10px] text-muted italic line-clamp-2 mb-0.5">"{s.text}"</p>
                  ))}
                </div>
              )}
              {staff.negative_samples.length > 0 && (
                <div
                  className="cursor-pointer hover:bg-destructive/5 rounded p-1 -m-1 transition-colors"
                  onClick={() => setDrillDown({ title: 'شكاوى الموظفين', params: { topic: 'staff', sentiment: 'negative' } })}
                >
                  <div className="text-[10px] font-medium text-destructive mb-1 flex items-center gap-1">شكاوى ({staff.staff_negative_mentions}) <ChevronLeft className="w-2.5 h-2.5 text-destructive/40" /></div>
                  {staff.negative_samples.slice(0, 2).map((s, i) => (
                    <p key={i} className="text-[10px] text-muted italic line-clamp-2 mb-0.5">"{s.text}"</p>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Customer Loyalty =====
function LoyaltySection({ data, placeId }: { data: InsightsData; placeId: string }) {
  const loyalty = data.loyalty_alerts
  const [showStable, setShowStable] = useState(false)
  const [drillDown, setDrillDown] = useState<{ title: string; params: Record<string, any> } | null>(null)
  if (!loyalty || loyalty.repeat_customers.length === 0) return null

  const declining = loyalty.repeat_customers.filter(c => c.rating_trend === 'declining')
  const improving = loyalty.repeat_customers.filter(c => c.rating_trend === 'improving')
  const stable = loyalty.repeat_customers.filter(c => c.rating_trend === 'stable')

  const CustomerCard = ({ c, i, variant }: { c: typeof declining[0]; i: number; variant: 'declining' | 'improving' | 'stable' }) => (
    <div
      key={i}
      className={`flex items-center gap-2 p-1.5 rounded text-[10px] cursor-pointer transition-colors ${
        variant === 'declining' ? 'bg-destructive/5 border border-destructive/10 hover:bg-destructive/10' :
        variant === 'improving' ? 'bg-success/5 border border-success/10 hover:bg-success/10' :
        'bg-card-hover border border-border hover:bg-card-hover/80'
      }`}
      onClick={() => setDrillDown({ title: c.author, params: { author: c.author } })}
    >
      <span className="font-medium text-foreground truncate max-w-[80px]">{c.author}</span>
      <div className="flex items-center gap-0.5 flex-1 min-w-0" dir="ltr">
        {c.ratings.map((r, j) => (
          <span key={j} className="flex items-center">
            {j > 0 && <span className="text-muted mx-0.5">→</span>}
            <span className={`font-medium ${r >= 4 ? 'text-success' : r >= 3 ? 'text-warning' : 'text-destructive'}`}>{r}★</span>
          </span>
        ))}
      </div>
      <span className="text-muted" dir="ltr">{c.review_count}x</span>
      <ChevronLeft className="w-3 h-3 text-muted/40" />
    </div>
  )

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2"><Heart className="w-4 h-4 text-primary" /> ولاء العملاء</CardTitle>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-muted">{loyalty.total_repeat_customers} عميل متكرر</span>
            {loyalty.declining_count > 0 && <Badge variant="destructive" className="text-[9px] px-1 py-0">{loyalty.declining_count} متراجع</Badge>}
            {loyalty.improving_count > 0 && <Badge variant="success" className="text-[9px] px-1 py-0">{loyalty.improving_count} محسّن</Badge>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {drillDown ? (
          <InlineDrillDown title={drillDown.title} placeId={placeId} baseParams={drillDown.params} onClose={() => setDrillDown(null)} />
        ) : (
          <div className="space-y-2">
            {declining.length > 0 && (
              <div>
                <div className="text-[10px] font-medium text-destructive mb-1">متراجعون</div>
                <div className="space-y-1">
                  {declining.map((c, i) => <CustomerCard key={i} c={c} i={i} variant="declining" />)}
                </div>
              </div>
            )}
            {improving.length > 0 && (
              <div>
                <div className="text-[10px] font-medium text-success mb-1">محسّنون</div>
                <div className="space-y-1">
                  {improving.map((c, i) => <CustomerCard key={i} c={c} i={i} variant="improving" />)}
                </div>
              </div>
            )}
            {stable.length > 0 && (
              <button onClick={() => setShowStable(!showStable)} className="flex items-center gap-1 text-[10px] text-muted hover:text-foreground">
                <span>مستقرون ({stable.length})</span>
                <ChevronDown className={`w-2.5 h-2.5 transition-transform ${showStable ? 'rotate-180' : ''}`} />
              </button>
            )}
            {showStable && stable.map((c, i) => <CustomerCard key={i} c={c} i={i} variant="stable" />)}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Opening Checklist =====
function ChecklistSection({ data, placeId }: { data: InsightsData; placeId: string }) {
  const checklist = data.opening_checklist
  const [drillDown, setDrillDown] = useState<{ title: string; params: Record<string, any> } | null>(null)
  if (!checklist || checklist.items.length === 0) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2"><ClipboardCheck className="w-4 h-4 text-warning" /> قائمة الافتتاح</CardTitle>
          {checklist.llm_generated && <span className="text-[9px] text-muted flex items-center gap-0.5"><Lightbulb className="w-2.5 h-2.5 text-warning" /> AI</span>}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {drillDown ? (
          <InlineDrillDown title={drillDown.title} placeId={placeId} baseParams={drillDown.params} onClose={() => setDrillDown(null)} />
        ) : (
          <div className="space-y-1">
            {checklist.items.map((item, i) => (
              <div
                key={i}
                className="flex items-start gap-2 py-1.5 border-b border-border/50 last:border-0 cursor-pointer hover:bg-card-hover/50 rounded px-1 -mx-1 transition-colors"
                onClick={() => {
                  if (item.review_ids?.length) {
                    setDrillDown({ title: item.check_item_ar || item.check_item_en, params: { ids: item.review_ids } })
                  } else {
                    setDrillDown({ title: item.check_item_ar || item.check_item_en, params: { topic: item.topic, sentiment: 'negative' } })
                  }
                }}
              >
                <SeverityDot severity={item.severity} />
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-foreground line-clamp-2">{item.check_item_ar || item.check_item_en}</div>
                  <div className="text-[10px] text-muted" dir="ltr">{item.complaint_count} شكوى ({item.recent_count} حديثة)</div>
                </div>
                <ChevronLeft className="w-3 h-3 text-muted/40 mt-1.5 flex-shrink-0" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== SECTION: Satisfaction Drops =====
function SatisfactionDropsSection({ data, placeId }: { data: InsightsData; placeId: string }) {
  const drops = data.satisfaction_drops
  const [drillDown, setDrillDown] = useState<{ title: string; params: Record<string, any> } | null>(null)
  if (!drops || drops.items.length === 0) return null

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-sm flex items-center gap-2"><TrendingDown className="w-4 h-4 text-destructive" /> انخفاض الرضا</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {drillDown ? (
          <InlineDrillDown title={drillDown.title} placeId={placeId} baseParams={drillDown.params} onClose={() => setDrillDown(null)} />
        ) : (
          <div className="space-y-1.5">
            {drops.items.slice(0, 5).map((drop, i) => (
              <div
                key={i}
                className="p-2 bg-destructive/5 border border-destructive/10 rounded-lg cursor-pointer hover:bg-destructive/10 transition-colors"
                onClick={() => {
                  if (drop.review_ids?.length) {
                    setDrillDown({ title: `انخفاض ${drop.date}`, params: { ids: drop.review_ids } })
                  }
                }}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <div className="flex items-center gap-1.5">
                    <TrendingDown className="w-3 h-3 text-destructive" />
                    <span className="text-xs font-medium text-foreground" dir="ltr">{drop.date}</span>
                    {drop.topic && <span className="text-[10px] text-muted">{drop.topic}</span>}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {drop.magnitude && <span className="text-[10px] font-medium text-destructive" dir="ltr">{drop.magnitude.toFixed(1)}%</span>}
                    {drop.review_ids?.length ? <ChevronLeft className="w-3 h-3 text-muted/40" /> : null}
                  </div>
                </div>
                {(drop.analysis_ar || drop.analysis) && <p className="text-[10px] text-muted line-clamp-2">{drop.analysis_ar || drop.analysis}</p>}
                {(drop.recommendation_ar || drop.recommendation) && <p className="text-[10px] text-foreground mt-0.5">{drop.recommendation_ar || drop.recommendation}</p>}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ===== MAIN PAGE =====
function InsightsContent() {
  const { user, logout } = useAuth()
  const [places, setPlaces] = useState<Place[]>([])
  const [selectedPlace, setSelectedPlace] = useState<string | null>(null)
  const [placesDropdownOpen, setPlacesDropdownOpen] = useState(false)
  const [insights, setInsights] = useState<InsightsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [timeFilter, setTimeFilter] = useState<string>('all') // 'all' | '2025' | '2024' | 'custom'

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchPlaces(100)
        const placesList = data.places || []
        setPlaces(placesList)
        const params = new URLSearchParams(window.location.search)
        const placeId = params.get('place_id')
        if (placeId) setSelectedPlace(placeId)
        else if (placesList.length > 0) setSelectedPlace(placesList[0].id)
      } catch (error) {
        console.error('Failed to load places:', error)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  useEffect(() => {
    if (!selectedPlace) return
    const loadInsights = async () => {
      setInsightsLoading(true)
      try {
        const opts: { start_date?: string; end_date?: string } = {}
        if (timeFilter !== 'all') {
          opts.start_date = `${timeFilter}-01-01`
          opts.end_date = `${timeFilter}-12-31`
        }
        const data = await fetchInsights(selectedPlace, opts)
        setInsights(data)
      } catch (error) {
        console.error('Failed to load insights:', error)
        setInsights(null)
      } finally {
        setInsightsLoading(false)
      }
    }
    loadInsights()
  }, [selectedPlace, timeFilter])

  const handlePlaceSelect = (placeId: string) => {
    setSelectedPlace(placeId)
    setPlacesDropdownOpen(false)
    const url = new URL(window.location.href)
    url.searchParams.set('place_id', placeId)
    window.history.replaceState({}, '', url.toString())
  }

  const selectedPlaceName = selectedPlace ? places.find(p => p.id === selectedPlace)?.name || 'المكان المحدد' : 'اختر مكان'

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-primary animate-spin" />
      </div>
    )
  }

  const summary = insights?.data_summary

  return (
    <div className="min-h-screen bg-background" dir="rtl">
      {/* Nav */}
      <nav className="bg-card border-b border-border px-4 py-2.5 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary to-blue-700 flex items-center justify-center">
                <span className="text-xs font-bold text-white">N</span>
              </div>
              <span className="text-base font-bold text-foreground hidden sm:inline">NURLIYA</span>
            </div>
            <div className="relative">
              <button onClick={() => setPlacesDropdownOpen(!placesDropdownOpen)} className="flex items-center gap-1.5 bg-card-hover px-2.5 py-1 rounded-lg border border-border hover:border-muted transition-colors">
                <MapPin className="w-3.5 h-3.5 text-muted" />
                <span className="text-xs text-foreground truncate max-w-[160px]">{selectedPlaceName}</span>
                <ChevronDown className={`w-3.5 h-3.5 text-muted transition-transform ${placesDropdownOpen ? 'rotate-180' : ''}`} />
              </button>
              {placesDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setPlacesDropdownOpen(false)} />
                  <div className="absolute top-full right-0 mt-1 w-64 max-h-60 overflow-y-auto bg-card border border-border rounded-lg shadow-lg z-50">
                    {places.map((place) => (
                      <button key={place.id} onClick={() => handlePlaceSelect(place.id)} className={`w-full text-right px-3 py-1.5 text-xs hover:bg-card-hover ${selectedPlace === place.id ? 'bg-primary/10 text-primary font-medium' : 'text-foreground'}`}>
                        <div className="truncate">{place.name}</div>
                        <div className="text-[10px] text-muted" dir="ltr">{place.review_count} تقييم</div>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted hidden sm:inline">{user?.name}</span>
            <Button variant="ghost" size="sm" onClick={logout} className="text-muted hover:text-destructive h-7 px-2">
              <LogOut className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </nav>

      {/* Metrics Bar */}
      {summary && summary.total_reviews != null && (
        <div className="bg-card border-b border-border px-4 py-2">
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-1.5">
                <MessageSquare className="w-3.5 h-3.5 text-primary" />
                <span className="text-sm font-bold text-foreground" dir="ltr">{(summary.total_reviews || 0).toLocaleString()}</span>
                <span className="text-[10px] text-muted">تقييم</span>
              </div>
              <div className="w-px h-4 bg-border" />
              <div className="flex items-center gap-1.5">
                <BarChart3 className="w-3.5 h-3.5 text-success" />
                <span className="text-sm font-bold text-foreground" dir="ltr">{(summary.analyzed_reviews || 0).toLocaleString()}</span>
                <span className="text-[10px] text-muted">محلل</span>
              </div>
              <div className="w-px h-4 bg-border" />
              <div className="flex items-center gap-1.5">
                <Package className="w-3.5 h-3.5 text-warning" />
                <span className="text-sm font-bold text-foreground" dir="ltr">{(summary.total_mentions || 0).toLocaleString()}</span>
                <span className="text-[10px] text-muted">إشارة</span>
              </div>
              {insights?.urgent_issues && insights.urgent_issues.total > 0 && (
                <>
                  <div className="w-px h-4 bg-border" />
                  <div className="flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-destructive" />
                    <span className="text-sm font-bold text-destructive" dir="ltr">{insights.urgent_issues.total}</span>
                    <span className="text-[10px] text-muted">عاجل</span>
                  </div>
                </>
              )}
              {insights?.action_checklist && insights.action_checklist.total > 0 && (
                <>
                  <div className="w-px h-4 bg-border" />
                  <div className="flex items-center gap-1.5">
                    <ClipboardCheck className="w-3.5 h-3.5 text-primary" />
                    <span className="text-sm font-bold text-primary" dir="ltr">{insights.action_checklist.total}</span>
                    <span className="text-[10px] text-muted">إجراء</span>
                  </div>
                </>
              )}
            </div>
            {/* Time filter */}
            <div className="flex items-center gap-1 bg-card-hover rounded-lg p-0.5">
              <Calendar className="w-3 h-3 text-muted mr-1" />
              {['all', '2026', '2025', '2024'].map(f => (
                <button key={f} onClick={() => setTimeFilter(f)} className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${timeFilter === f ? 'bg-primary text-white' : 'text-muted hover:text-foreground'}`}>
                  {f === 'all' ? 'الكل' : f}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 py-4">
        {!selectedPlace ? (
          <div className="text-center py-16">
            <MapPin className="w-10 h-10 text-muted mx-auto mb-3" />
            <p className="text-sm text-foreground">اختر مكان لعرض التحليلات</p>
          </div>
        ) : insightsLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 text-primary animate-spin" />
          </div>
        ) : insights ? (
          <>
            <div className="flex gap-4">
              {/* Main content */}
              <div className="flex-1 min-w-0 space-y-4">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <UrgentSection data={insights} />
                  <ActionsSection data={insights} />
                </div>

                <SentimentTrendSection selectedPlace={selectedPlace} />

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <DayOfWeekSection data={insights} placeId={selectedPlace} />
                  <RecurringComplaintsSection data={insights} placeId={selectedPlace} />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <TopPraisedSection data={insights} placeId={selectedPlace} />
                  <ProblemProductsSection data={insights} placeId={selectedPlace} />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <StaffSection data={insights} placeId={selectedPlace} />
                  <LoyaltySection data={insights} placeId={selectedPlace} />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <ChecklistSection data={insights} placeId={selectedPlace} />
                  <SatisfactionDropsSection data={insights} placeId={selectedPlace} />
                </div>
              </div>

              {/* Side panel - Weekly Plan */}
              <div className="hidden xl:block w-72 flex-shrink-0">
                <WeeklyPlanPanel data={insights} />
              </div>
            </div>

            {/* Mobile: Weekly Plan below content */}
            <div className="xl:hidden mt-4">
              <Card>
                <CardContent className="p-4">
                  <WeeklyPlanPanel data={insights} />
                </CardContent>
              </Card>
            </div>
          </>
        ) : (
          <div className="text-center py-16">
            <AlertTriangle className="w-10 h-10 text-muted mx-auto mb-3" />
            <p className="text-sm text-foreground">لا توجد تحليلات متاحة</p>
            <p className="text-xs text-muted mt-1">قد لا يحتوي هذا المكان على تقييمات محللة بعد</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function InsightsPage() {
  return (
    <AuthGuard>
      <InsightsContent />
    </AuthGuard>
  )
}
