-- Add Arabic fields to anomaly_insights table
ALTER TABLE anomaly_insights ADD COLUMN IF NOT EXISTS analysis_ar TEXT;
ALTER TABLE anomaly_insights ADD COLUMN IF NOT EXISTS recommendation_ar TEXT;
