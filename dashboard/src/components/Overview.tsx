'use client'

import { Card } from '@/components/Card'

interface OverviewProps {
  stats?: {
    rating?: number
    ratingTrend?: number
    positivePercent?: number
    positiveTrend?: number
    reviewsThisWeek?: number
    alerts?: number
    actions?: number
  }
  sentimentTrend?: number[]
  ratingDistribution?: { stars: number; pct: number }[]
  hotItems?: { item: string; score: string; trend: string }[]
  coldItems?: { item: string; score: string; trend: string }[]
  alerts?: { icon: string; text: string; urgent: boolean }[]
  aiSummary?: string
}

export function Overview({
  stats = {
    rating: 4.3,
    ratingTrend: 0.1,
    positivePercent: 78,
    positiveTrend: 5,
    reviewsThisWeek: 23,
    alerts: 12,
    actions: 3,
  },
  sentimentTrend = [65, 72, 68, 75, 71, 78, 82],
  ratingDistribution = [
    { stars: 5, pct: 68 },
    { stars: 4, pct: 22 },
    { stars: 3, pct: 7 },
    { stars: 2, pct: 2 },
    { stars: 1, pct: 1 },
  ],
  hotItems = [
    { item: 'Spanish Latte', score: '94%', trend: '+12' },
    { item: 'Croissant', score: '89%', trend: '+3' },
    { item: 'Staff Friendliness', score: '87%', trend: '+5' },
  ],
  coldItems = [
    { item: 'Chicken Sandwich', score: '62%', trend: '-8' },
    { item: 'Wait Times', score: '-23%', trend: 'declining' },
    { item: 'Parking', score: '12', trend: 'complaints' },
  ],
  alerts = [
    { icon: '⚠️', text: 'Chicken Sandwich sentiment dropped 23% this week', urgent: true },
    { icon: '⚠️', text: '8 complaints about Friday lunch wait times', urgent: true },
    { icon: '💬', text: '14 reviews awaiting response', urgent: false },
    { icon: '📉', text: '3-star reviews increased by 40%', urgent: false },
  ],
  aiSummary = 'Great week — Spanish Latte mentioned 34 times with 94% positive sentiment. Watch out: Friday lunch service got 8 complaints. Your Chicken Sandwich is trending down — check portion size.',
}: OverviewProps) {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

  return (
    <div className="space-y-6">
      {/* Metrics Row */}
      <div className="grid grid-cols-5 gap-4">
        <div className="bg-card rounded-xl border border-border p-4 text-center">
          <div className="text-2xl font-bold text-foreground">
            {stats.rating} <span className="text-yellow-500">★</span>
          </div>
          <div className="text-xs text-muted">Rating</div>
          <div className="text-xs text-emerald-500 font-medium">↑ {stats.ratingTrend}</div>
        </div>
        <div className="bg-card rounded-xl border border-border p-4 text-center">
          <div className="text-2xl font-bold text-emerald-500">{stats.positivePercent}%</div>
          <div className="text-xs text-muted">Positive</div>
          <div className="text-xs text-emerald-500 font-medium">↑ {stats.positiveTrend}%</div>
        </div>
        <div className="bg-card rounded-xl border border-border p-4 text-center">
          <div className="text-2xl font-bold text-foreground">+{stats.reviewsThisWeek}</div>
          <div className="text-xs text-muted">Reviews</div>
          <div className="text-xs text-muted">this week</div>
        </div>
        <div className="bg-card rounded-xl border border-border p-4 text-center">
          <div className="text-2xl font-bold text-red-500">{stats.alerts}</div>
          <div className="text-xs text-muted">Alerts</div>
          <div className="text-xs text-red-500 font-medium">pending</div>
        </div>
        <div className="bg-card rounded-xl border border-border p-4 text-center">
          <div className="text-2xl font-bold text-blue-500">{stats.actions}</div>
          <div className="text-xs text-muted">Actions</div>
          <div className="text-xs text-blue-500 font-medium">suggested</div>
        </div>
      </div>

      {/* AI Summary */}
      <div className="bg-gradient-to-r from-blue-500/10 to-indigo-500/10 border border-blue-500/20 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <div className="text-xl">🤖</div>
          <div className="flex-1">
            <p className="text-sm text-foreground">{aiSummary}</p>
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-6">
        {/* Sentiment Trend */}
        <Card title="Sentiment Trend">
          <div className="h-40 flex items-end justify-between gap-2">
            {sentimentTrend.map((val, i) => (
              <div key={i} className="flex-1 flex flex-col items-center">
                <div
                  className="w-full bg-gradient-to-t from-blue-600 to-blue-400 rounded-t"
                  style={{ height: `${val}%` }}
                />
                <span className="text-xs text-muted mt-2">{days[i]}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Rating Distribution */}
        <Card title="Rating Distribution">
          <div className="space-y-3">
            {ratingDistribution.map((row) => (
              <div key={row.stars} className="flex items-center gap-3">
                <span className="text-xs w-16 text-yellow-500">
                  {'★'.repeat(row.stars)}
                  {'☆'.repeat(5 - row.stars)}
                </span>
                <div className="flex-1 h-3 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-yellow-500 rounded-full"
                    style={{ width: `${row.pct}%` }}
                  />
                </div>
                <span className="text-xs text-muted w-10">{row.pct}%</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Hot / Cold Row */}
      <div className="grid grid-cols-2 gap-6">
        {/* What's Hot */}
        <Card title="What's Hot">
          <div className="space-y-2">
            {hotItems.map((row, i) => (
              <div
                key={i}
                className="flex items-center justify-between p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg"
              >
                <span className="text-sm font-medium text-foreground">{row.item}</span>
                <div className="flex items-center gap-2">
                  <span className="text-emerald-500 font-bold text-sm">{row.score}</span>
                  <span className="text-emerald-400 text-xs">{row.trend}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* What's Not */}
        <Card title="What's Not">
          <div className="space-y-2">
            {coldItems.map((row, i) => (
              <div
                key={i}
                className="flex items-center justify-between p-3 bg-red-500/10 border border-red-500/20 rounded-lg"
              >
                <span className="text-sm font-medium text-foreground">{row.item}</span>
                <div className="flex items-center gap-2">
                  <span className="text-red-500 font-bold text-sm">{row.score}</span>
                  <span className="text-red-400 text-xs">{row.trend}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Alerts */}
      <Card title="Needs Attention">
        <div className="space-y-2">
          {alerts.map((alert, i) => (
            <div
              key={i}
              className={`flex items-center gap-3 p-3 rounded-lg ${
                alert.urgent
                  ? 'bg-red-500/10 border border-red-500/20'
                  : 'bg-amber-500/10 border border-amber-500/20'
              }`}
            >
              <span>{alert.icon}</span>
              <span className="text-sm text-foreground">{alert.text}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
