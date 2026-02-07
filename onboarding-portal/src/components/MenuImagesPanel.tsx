'use client'

import { useEffect, useState } from 'react'
import { fetchMenuImages, MenuImage } from '@/lib/api'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ImageIcon } from 'lucide-react'
import Lightbox from 'yet-another-react-lightbox'
import Zoom from 'yet-another-react-lightbox/plugins/zoom'
import Counter from 'yet-another-react-lightbox/plugins/counter'
import 'yet-another-react-lightbox/styles.css'
import 'yet-another-react-lightbox/plugins/counter.css'

interface MenuImagesPanelProps {
  taxonomyId: string
}

export function MenuImagesPanel({ taxonomyId }: MenuImagesPanelProps) {
  const [images, setImages] = useState<MenuImage[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(false)
  const [lightboxIndex, setLightboxIndex] = useState(-1)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const data = await fetchMenuImages(taxonomyId)
        setImages(data.images)
      } catch {
        // Silently fail — no images is fine
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [taxonomyId])

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            <ImageIcon className="w-4 h-4 inline mr-2" />
            Menu Images
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin w-5 h-5 border-2 border-primary border-t-transparent rounded-full" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (images.length === 0) return null

  const displayImages = expanded ? images : images.slice(0, 6)

  const slides = images.map((img) => ({ src: img.image_url }))

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            <ImageIcon className="w-4 h-4 inline mr-2" />
            Menu Images
            <span className="font-normal text-muted ml-2">({images.length})</span>
          </CardTitle>
          {images.length > 6 && (
            <Button size="sm" variant="ghost" onClick={() => setExpanded(!expanded)}>
              {expanded ? 'Show less' : `Show all ${images.length}`}
            </Button>
          )}
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {displayImages.map((img, idx) => (
              <button
                key={img.id}
                onClick={() => setLightboxIndex(idx)}
                className="relative aspect-square rounded-lg overflow-hidden border border-border hover:border-primary transition-colors group cursor-pointer"
              >
                <img
                  src={img.image_url}
                  alt={`Menu photo ${idx + 1}`}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                  loading="lazy"
                />
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Lightbox
        open={lightboxIndex >= 0}
        close={() => setLightboxIndex(-1)}
        index={lightboxIndex}
        slides={slides}
        plugins={[Zoom, Counter]}
        zoom={{
          maxZoomPixelRatio: 5,
          scrollToZoom: true,
        }}
        counter={{
          container: { style: { top: 0, bottom: 'unset' } },
        }}
        styles={{
          container: { backgroundColor: 'rgba(0, 0, 0, 0.92)' },
        }}
        animation={{ fade: 250, swipe: 300 }}
        carousel={{ finite: false }}
        controller={{ closeOnBackdropClick: true }}
      />
    </>
  )
}
