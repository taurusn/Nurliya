'use client'

import { useState } from 'react'
import { ChevronDown, MapPin, X } from 'lucide-react'
import { cn } from '@/lib/cn'
import { Place } from '@/lib/api'

interface PlaceSelectorProps {
  places: Place[]
  selectedPlace: Place | null
  onSelect: (place: Place | null) => void
}

export function PlaceSelector({ places, selectedPlace, onSelect }: PlaceSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors",
          "bg-card hover:bg-card-hover border-border",
          selectedPlace ? "text-foreground" : "text-muted"
        )}
      >
        <MapPin className="w-4 h-4" />
        <span className="text-sm max-w-[200px] truncate">
          {selectedPlace ? selectedPlace.name : "All Places"}
        </span>
        {selectedPlace ? (
          <X
            className="w-4 h-4 text-muted hover:text-foreground"
            onClick={(e) => {
              e.stopPropagation()
              onSelect(null)
            }}
          />
        ) : (
          <ChevronDown className={cn("w-4 h-4 transition-transform", isOpen && "rotate-180")} />
        )}
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute top-full mt-1 left-0 z-50 w-72 max-h-80 overflow-auto rounded-lg border border-border bg-card shadow-lg">
            <button
              onClick={() => {
                onSelect(null)
                setIsOpen(false)
              }}
              className={cn(
                "w-full px-3 py-2 text-left text-sm hover:bg-card-hover transition-colors",
                !selectedPlace && "bg-card-hover text-foreground font-medium"
              )}
            >
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4 text-muted" />
                <span>All Places</span>
              </div>
            </button>

            <div className="border-t border-border" />

            {places.map((place) => (
              <button
                key={place.id}
                onClick={() => {
                  onSelect(place)
                  setIsOpen(false)
                }}
                className={cn(
                  "w-full px-3 py-2 text-left text-sm hover:bg-card-hover transition-colors",
                  selectedPlace?.id === place.id && "bg-card-hover text-foreground font-medium"
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate">{place.name}</span>
                  {place.total_reviews && (
                    <span className="text-xs text-muted ml-2">
                      {place.total_reviews} reviews
                    </span>
                  )}
                </div>
              </button>
            ))}

            {places.length === 0 && (
              <div className="px-3 py-4 text-sm text-muted text-center">
                No places found
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
