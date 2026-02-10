# Business Intelligence Insights — Data Requirements

Analysis of what's achievable from our sentiment analysis data (869 analyzed reviews, 1477 mentions, 99.5% date coverage).

## Requirements Status

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Action checklist | YES | 109 reviews with `needs_action`, `action_en/ar` fields from LLM |
| 2 | Shift analysis | NO | Google Maps reviews have date only (YYYY-M-D), no time-of-day |
| 3 | Problem products | YES | raw_mentions with negative sentiment joined to taxonomy products |
| 4 | Opening checklist | YES | Derived from recurring negative topics in recent reviews |
| 5 | Urgent issues | YES | 44 reviews flagged `urgent=true` by LLM |
| 6 | Time patterns | YES | Day-of-week + monthly trends (865/869 reviews have dates) |
| 7 | Recurring complaints | YES | `topics_negative` arrays aggregated across all analyses |
| 8 | Top praised items | YES | Positive mentions joined to taxonomy products |
| 9 | Satisfaction drops | YES | Monthly score trends + anomaly_insights table |
| 10 | Patterns | YES | Day-of-week + monthly + topic correlations |
| 11 | Weekly plan | YES | Aggregated from #1, #3, #5, #7 |
| 12 | Praised employees | PARTIAL | LLM summaries mention "staff"/"barista" but not named individuals |
| 13 | Loyalty alerts | YES | 20+ repeat customers with rating trends over time |

## Data Sources

- **review_analysis**: sentiment, score, topics_positive/negative, urgent, needs_action, action_en/ar, summary_en/ar, suggested_reply_ar
- **raw_mentions**: mention text, sentiment, discovered_product_id — links mentions to taxonomy products
- **reviews**: author, rating, review_date (YYYY-M-D), text
- **anomaly_insights**: pre-computed satisfaction drop detection
- **taxonomy_products / taxonomy_categories**: product/category hierarchy

## Key Constraints

- **No time-of-day**: Google Maps `review_date` is date-only, no hours/minutes. Shift analysis is impossible.
- **Employee names**: LLM extracts topic=`staff` but doesn't isolate individual names. Would need NER pass on review text.
- **12 topic types**: service, food, drinks, price, cleanliness, wait_time, staff, quality, atmosphere, location, parking, delivery.
- **Date coverage**: 99.5% of analyzed reviews have dates after scraper timestamp fix (was 25% before).

## Scraper Fix (2026-02-10)

The Go scraper's `parseReviews()` in `entry.go` was missing dates for ~75% of extended reviews. Root cause: timestamp extraction relied on `el[2][2][0][1][21][6][8]` (date array inside photo metadata) which only exists for reviews with photos.

Fix: Added fallback to `el[1][2]` — a Unix microsecond timestamp present on every review. Date coverage went from 25% to 100% for new scrapes.
