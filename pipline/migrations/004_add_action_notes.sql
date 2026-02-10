-- Add internal action note fields for compensation/follow-up suggestions
ALTER TABLE review_analysis ADD COLUMN IF NOT EXISTS needs_action BOOLEAN DEFAULT FALSE;
ALTER TABLE review_analysis ADD COLUMN IF NOT EXISTS action_ar TEXT;
ALTER TABLE review_analysis ADD COLUMN IF NOT EXISTS action_en TEXT;
