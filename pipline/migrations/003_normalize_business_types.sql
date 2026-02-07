-- Migration 003: Normalize existing anchor business_type values
-- Maps raw Google Maps category strings to canonical keys
-- Idempotent: safe to run multiple times
-- Note: LOWER() is safe for Arabic strings — Arabic has no case distinction,
-- so LOWER('مقهى') = 'مقهى' regardless of PostgreSQL locale.

UPDATE category_anchors SET business_type = 'cafe'
WHERE LOWER(business_type) IN ('coffee shop', 'مقهى', 'كوفي شوب', 'كافيه', 'coffeehouse', 'coffee', 'café');

UPDATE category_anchors SET business_type = 'restaurant'
WHERE LOWER(business_type) IN ('restaurant', 'مطعم', 'fast food restaurant', 'مطعم وجبات سريعة');

UPDATE category_anchors SET business_type = 'bakery'
WHERE LOWER(business_type) IN ('bakery', 'مخبز', 'مخبزة');
