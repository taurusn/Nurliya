'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AuthGuard } from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import { fetchPendingTaxonomies, PendingTaxonomy } from '@/lib/api'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  LogOut,
  FileSearch,
  CheckCircle,
  Clock,
  Package,
  FolderTree,
  ChevronRight,
  RefreshCw,
} from 'lucide-react'

function PendingList() {
  const { user, logout } = useAuth()
  const [taxonomies, setTaxonomies] = useState<PendingTaxonomy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<string | undefined>(undefined)

  const loadTaxonomies = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchPendingTaxonomies(filter)
      setTaxonomies(data.taxonomies)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTaxonomies()
  }, [filter])

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'draft':
        return <Badge variant="warning">Draft</Badge>
      case 'review':
        return <Badge variant="default">In Review</Badge>
      case 'active':
        return <Badge variant="success">Active</Badge>
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary to-blue-700 flex items-center justify-center">
              <span className="text-lg font-bold text-white">N</span>
            </div>
            <div>
              <h1 className="text-lg font-semibold text-foreground">Onboarding Portal</h1>
              <p className="text-xs text-muted">Taxonomy Review</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted">{user?.name}</span>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="w-4 h-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <Card>
            <CardContent className="pt-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-warning/20 flex items-center justify-center">
                  <Clock className="w-5 h-5 text-warning" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {taxonomies.filter((t) => t.status === 'draft' || t.status === 'review').length}
                  </p>
                  <p className="text-sm text-muted">Pending Review</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-success/20 flex items-center justify-center">
                  <CheckCircle className="w-5 h-5 text-success" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {taxonomies.filter((t) => t.status === 'active').length}
                  </p>
                  <p className="text-sm text-muted">Published</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
                  <FileSearch className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">{taxonomies.length}</p>
                  <p className="text-sm text-muted">Total Taxonomies</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filter & Refresh */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex gap-2">
            <Button
              variant={!filter ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilter(undefined)}
            >
              Pending
            </Button>
            <Button
              variant={filter === 'active' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilter('active')}
            >
              Published
            </Button>
          </div>
          <Button variant="outline" size="sm" onClick={loadTaxonomies} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 p-4 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive">
            {error}
          </div>
        )}

        {/* Taxonomy List */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
          </div>
        ) : taxonomies.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <FileSearch className="w-12 h-12 text-muted mx-auto mb-4" />
              <p className="text-muted">No taxonomies found</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {taxonomies.map((tax) => (
              <Link key={tax.id} href={`/${tax.id}`}>
                <Card className="hover:bg-card-hover transition-colors cursor-pointer">
                  <CardContent className="py-4">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="font-semibold text-foreground">{tax.place_name}</h3>
                          {getStatusBadge(tax.status)}
                        </div>
                        <div className="flex items-center gap-4 text-sm text-muted">
                          <span className="flex items-center gap-1">
                            <FolderTree className="w-4 h-4" />
                            {tax.approved_categories}/{tax.categories_count} categories
                          </span>
                          <span className="flex items-center gap-1">
                            <Package className="w-4 h-4" />
                            {tax.approved_products}/{tax.products_count} products
                          </span>
                          {tax.place_category && (
                            <Badge variant="outline">{tax.place_category}</Badge>
                          )}
                        </div>
                      </div>
                      <ChevronRight className="w-5 h-5 text-muted" />
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

export default function HomePage() {
  return (
    <AuthGuard>
      <PendingList />
    </AuthGuard>
  )
}
