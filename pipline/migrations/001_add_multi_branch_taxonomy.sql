-- Migration: Add multi-branch support to place_taxonomies
-- FEATURE-001: Multi-Branch Shared Taxonomy
-- Date: 2026-02-04
--
-- This migration adds:
-- 1. place_ids: Array of UUIDs for all places sharing a taxonomy
-- 2. scrape_job_id: FK to scrape_jobs for linking to parent scrape
--
-- Run with: psql -U postgres -d nurliya -f 001_add_multi_branch_taxonomy.sql

-- Add new columns
ALTER TABLE place_taxonomies
ADD COLUMN IF NOT EXISTS place_ids UUID[];

ALTER TABLE place_taxonomies
ADD COLUMN IF NOT EXISTS scrape_job_id UUID REFERENCES scrape_jobs(id) ON DELETE SET NULL;

-- Create GIN index for efficient array queries on place_ids
CREATE INDEX IF NOT EXISTS ix_place_taxonomies_place_ids
ON place_taxonomies USING GIN (place_ids);

-- Create index on scrape_job_id for lookups
CREATE INDEX IF NOT EXISTS ix_place_taxonomies_scrape_job
ON place_taxonomies (scrape_job_id);

-- Backfill existing taxonomies: set place_ids = ARRAY[place_id]
-- This ensures backward compatibility - existing single-place taxonomies
-- will have their place_id also in place_ids array
UPDATE place_taxonomies
SET place_ids = ARRAY[place_id]
WHERE place_ids IS NULL;

-- Verification query (optional - run to check results)
-- SELECT id, place_id, place_ids, scrape_job_id FROM place_taxonomies LIMIT 5;

-- Rollback commands (if needed):
-- DROP INDEX IF EXISTS ix_place_taxonomies_place_ids;
-- DROP INDEX IF EXISTS ix_place_taxonomies_scrape_job;
-- ALTER TABLE place_taxonomies DROP COLUMN IF EXISTS place_ids;
-- ALTER TABLE place_taxonomies DROP COLUMN IF EXISTS scrape_job_id;
