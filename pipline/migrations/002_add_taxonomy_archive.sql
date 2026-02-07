-- Migration: Add taxonomy_archives table for preserving taxonomy history
-- Date: 2026-02-06

CREATE TABLE IF NOT EXISTS taxonomy_archives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_taxonomy_id UUID NOT NULL,
    place_id UUID NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    place_name VARCHAR(255),

    -- Reason for archival
    archive_reason VARCHAR(50) NOT NULL,  -- 'import_recluster', 'manual_delete', 'republish'
    archived_by UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Full snapshot of taxonomy state
    snapshot JSONB NOT NULL,  -- {taxonomy: {...}, categories: [...], products: [...]}

    -- Stats at time of archival
    categories_count INTEGER DEFAULT 0,
    products_count INTEGER DEFAULT 0,
    status_at_archive VARCHAR(20),  -- draft, review, active

    -- Link to new taxonomy (if replaced)
    replaced_by_taxonomy_id UUID,

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS ix_taxonomy_archives_place ON taxonomy_archives(place_id);
CREATE INDEX IF NOT EXISTS ix_taxonomy_archives_original ON taxonomy_archives(original_taxonomy_id);
CREATE INDEX IF NOT EXISTS ix_taxonomy_archives_created ON taxonomy_archives(created_at DESC);

-- Comment
COMMENT ON TABLE taxonomy_archives IS 'Archive of taxonomy snapshots before re-clustering/deletion for learning and audit';
