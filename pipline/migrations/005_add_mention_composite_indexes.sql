-- Composite indexes for raw_mentions to speed up grouped mention queries.
-- Query patterns: place_id IN (...) AND discovered_category_id = X (draft)
--                 place_id IN (...) AND resolved_category_id = X (published)
-- Also covers orphan queries that filter on mention_type + NULL checks.

-- Draft taxonomy: category grouped mentions
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_mentions_place_disc_cat
ON raw_mentions (place_id, discovered_category_id);

-- Draft taxonomy: product grouped mentions
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_mentions_place_disc_prod
ON raw_mentions (place_id, discovered_product_id);

-- Published taxonomy: category grouped mentions
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_mentions_place_res_cat
ON raw_mentions (place_id, resolved_category_id);

-- Published taxonomy: product grouped mentions
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_mentions_place_res_prod
ON raw_mentions (place_id, resolved_product_id);

-- Orphan queries: place_id + mention_type + NULL checks
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_mentions_place_type
ON raw_mentions (place_id, mention_type);
