# Nurliya System Architecture

## Product Overview

**Nurliya** is an AI-powered sentiment analysis platform designed for Saudi Arabian businesses to understand and respond to Google Maps reviews at scale.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NURLIYA PLATFORM                                │
│                                                                             │
│    "AI-Powered Review Intelligence for Saudi Arabian Businesses"           │
│                                                                             │
│    Features:                                                                │
│    ✓ Scrape Google Maps reviews (120+ places/min, 300+ reviews/place)     │
│    ✓ AI sentiment analysis (Llama 3.1 8B)                                  │
│    ✓ Saudi dialect-aware Arabic processing                                  │
│    ✓ Auto-generated professional replies                                    │
│    ✓ Email reports with actionable insights                                │
│    ✓ REST API for integration                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. High-Level System Architecture

```
                                    ┌──────────────────┐
                                    │    End Users     │
                                    │  (API Clients)   │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │ Cloudflare Tunnel│
                                    │   (Optional)     │
                                    └────────┬─────────┘
                                             │
┌────────────────────────────────────────────┼────────────────────────────────────────────┐
│                                            │                                             │
│                              DOCKER COMPOSE NETWORK                                      │
│                                            │                                             │
│    ┌───────────────────────────────────────┼───────────────────────────────────────┐   │
│    │                                       │                                        │   │
│    │                            ┌──────────▼──────────┐                            │   │
│    │                            │      API Layer      │                            │   │
│    │                            │    (FastAPI:8000)   │                            │   │
│    │                            │                     │                            │   │
│    │                            │  • REST Endpoints   │                            │   │
│    │                            │  • Job Management   │                            │   │
│    │                            │  • Background Tasks │                            │   │
│    │                            └──────────┬──────────┘                            │   │
│    │                                       │                                        │   │
│    │              ┌────────────────────────┼────────────────────────┐              │   │
│    │              │                        │                        │              │   │
│    │              ▼                        ▼                        ▼              │   │
│    │    ┌─────────────────┐    ┌─────────────────────┐    ┌──────────────────┐   │   │
│    │    │  Go Scraper     │    │    PostgreSQL       │    │    RabbitMQ      │   │   │
│    │    │   :8080         │    │     :5432           │    │     :5672        │   │   │
│    │    │                 │    │                     │    │                  │   │   │
│    │    │ • Google Maps   │    │  • places           │    │ • review_analysis│   │   │
│    │    │ • 33+ fields    │    │  • reviews          │    │ • dlq            │   │   │
│    │    │ • CSV output    │    │  • jobs             │    │                  │   │   │
│    │    └─────────────────┘    │  • review_analysis  │    └────────┬─────────┘   │   │
│    │                           │  • scrape_jobs      │             │              │   │
│    │                           └─────────────────────┘             │              │   │
│    │                                                               │              │   │
│    │                                                    ┌──────────▼──────────┐  │   │
│    │                                                    │   Worker Pool       │  │   │
│    │                                                    │   (2+ Replicas)     │  │   │
│    │                                                    │                     │  │   │
│    │                                                    │  • Queue Consumer   │  │   │
│    │                                                    │  • LLM Orchestrator │  │   │
│    │                                                    │  • Email Trigger    │  │   │
│    │                                                    └──────────┬──────────┘  │   │
│    │                                                               │              │   │
│    └───────────────────────────────────────────────────────────────┼──────────────┘   │
│                                                                    │                   │
└────────────────────────────────────────────────────────────────────┼───────────────────┘
                                                                     │
                                                          ┌──────────▼──────────┐
                                                          │    vLLM Server      │
                                                          │   (Host Machine)    │
                                                          │                     │
                                                          │  • Llama 3.1 8B     │
                                                          │  • RTX 4090 GPU     │
                                                          │  • OpenAI API       │
                                                          └─────────────────────┘
```

---

## 2. Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                NURLIYA COMPONENTS                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           PRESENTATION LAYER                                 │   │
│  │                                                                              │   │
│  │   ┌─────────────────────────────────────────────────────────────────────┐  │   │
│  │   │                        api.py (FastAPI)                              │  │   │
│  │   │                                                                      │  │   │
│  │   │   Endpoints:                                                         │  │   │
│  │   │   ├── GET  /health              → Health check                      │  │   │
│  │   │   ├── POST /api/scrape          → Start scrape job                  │  │   │
│  │   │   ├── GET  /api/jobs            → List all jobs                     │  │   │
│  │   │   ├── GET  /api/jobs/{id}       → Job status/progress               │  │   │
│  │   │   ├── GET  /api/places          → List scraped places               │  │   │
│  │   │   ├── GET  /api/places/{id}     → Place details                     │  │   │
│  │   │   ├── GET  /api/places/{id}/reviews → Reviews + AI analysis         │  │   │
│  │   │   └── GET  /api/places/{id}/stats   → Sentiment statistics          │  │   │
│  │   │                                                                      │  │   │
│  │   └─────────────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                           │
│                                         ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         ORCHESTRATION LAYER                                  │   │
│  │                                                                              │   │
│  │   ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐  │   │
│  │   │  orchestrator.py   │    │  scraper_client.py │    │  producer.py    │  │   │
│  │   │                    │    │                    │    │                 │  │   │
│  │   │ • Pipeline control │    │ • HTTP client      │    │ • CSV → DB      │  │   │
│  │   │ • Job lifecycle    │    │ • Job polling      │    │ • DB → Queue    │  │   │
│  │   │ • Error handling   │    │ • CSV download     │    │ • Job creation  │  │   │
│  │   └────────────────────┘    └────────────────────┘    └─────────────────┘  │   │
│  │                                                                              │   │
│  │   ┌────────────────────────────────────────────────────────────────────┐   │   │
│  │   │                        csv_parser.py                                │   │   │
│  │   │                                                                     │   │   │
│  │   │   • Parse scraper CSV output                                       │   │   │
│  │   │   • Normalize place data (33+ fields)                              │   │   │
│  │   │   • Extract reviews (regular + extended)                           │   │   │
│  │   │   • Handle JSON fields, NaN values                                 │   │   │
│  │   └────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                           │
│                                         ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          PROCESSING LAYER                                    │   │
│  │                                                                              │   │
│  │   ┌──────────────────────────────────────────────────────────────────────┐ │   │
│  │   │                         worker.py                                     │ │   │
│  │   │                                                                       │ │   │
│  │   │   ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │ │   │
│  │   │   │   Consume   │───▶│   Analyze   │───▶│   Save + Notify         │ │ │   │
│  │   │   │   Message   │    │   w/ LLM    │    │   • Store analysis      │ │ │   │
│  │   │   │             │    │             │    │   • Update progress     │ │ │   │
│  │   │   └─────────────┘    └─────────────┘    │   • Trigger email       │ │ │   │
│  │   │                                         └─────────────────────────┘ │ │   │
│  │   └──────────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                              │   │
│  │   ┌────────────────────┐    ┌────────────────────────────────────────────┐ │   │
│  │   │   llm_client.py    │    │              email_service.py              │ │   │
│  │   │                    │    │                                            │ │   │
│  │   │ • vLLM interface   │    │ • HTML report generation (Jinja2)         │ │   │
│  │   │ • System prompts   │    │ • Sentiment visualization                 │ │   │
│  │   │ • JSON parsing     │    │ • Per-place insights                      │ │   │
│  │   │ • Retry logic      │    │ • SMTP delivery (async)                   │ │   │
│  │   │                    │    │ • RTL Arabic support                      │ │   │
│  │   └────────────────────┘    └────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                           │
│                                         ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                            DATA LAYER                                        │   │
│  │                                                                              │   │
│  │   ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐  │   │
│  │   │    database.py     │    │    rabbitmq.py     │    │   config.py     │  │   │
│  │   │                    │    │                    │    │                 │  │   │
│  │   │ • SQLAlchemy ORM   │    │ • Queue setup      │    │ • Env vars      │  │   │
│  │   │ • 5 table models   │    │ • DLQ routing      │    │ • Defaults      │  │   │
│  │   │ • Session mgmt     │    │ • Message publish  │    │ • Validation    │  │   │
│  │   └────────────────────┘    └────────────────────┘    └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              COMPLETE DATA FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘

     USER REQUEST                    SCRAPING PHASE                    PROCESSING PHASE
  ═══════════════                 ═══════════════════              ═════════════════════

  ┌─────────────┐
  │ POST        │
  │ /api/scrape │
  │             │
  │ {           │
  │  query:     │
  │  "cafes in  │
  │   Riyadh"   │
  │ }           │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
  │   Create    │────────▶│   Call Go   │────────▶│   Poll      │
  │ ScrapeJob   │         │  Scraper    │         │  Status     │
  │  (pending)  │         │   API       │         │             │
  └─────────────┘         └─────────────┘         └──────┬──────┘
                                                         │
                                                         │ status=ok
                                                         ▼
                          ┌─────────────┐         ┌─────────────┐
                          │  Download   │◀────────│   Parse     │
                          │    CSV      │         │  Results    │
                          │   File      │         │             │
                          └──────┬──────┘         └─────────────┘
                                 │
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                         CSV PARSING                               │
  │                                                                   │
  │   ┌─────────────────────────────────────────────────────────┐   │
  │   │  CSV Row (per place)                                     │   │
  │   │  ├── title, place_id, category, address, rating         │   │
  │   │  ├── user_reviews: [...] (up to ~5 reviews)             │   │
  │   │  └── user_reviews_extended: [...] (up to ~300 reviews)  │   │
  │   └─────────────────────────────────────────────────────────┘   │
  │                              │                                    │
  │                              ▼                                    │
  │   ┌─────────────────────────────────────────────────────────┐   │
  │   │  Normalize & Merge                                       │   │
  │   │  ├── Deduplicate reviews                                 │   │
  │   │  ├── Clean NaN/null values                               │   │
  │   │  └── Parse JSON fields                                   │   │
  │   └─────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                      DATABASE STORAGE                             │
  │                                                                   │
  │   ┌───────────────┐     ┌───────────────┐     ┌──────────────┐  │
  │   │    places     │     │    reviews    │     │     jobs     │  │
  │   │               │     │               │     │              │  │
  │   │ id            │◀────│ place_id (FK) │     │ place_id(FK) │  │
  │   │ name          │     │ job_id (FK)   │────▶│ id           │  │
  │   │ place_id (UK) │     │ author        │     │ status       │  │
  │   │ category      │     │ rating        │     │ total_reviews│  │
  │   │ rating        │     │ text          │     │ processed    │  │
  │   │ address       │     │ review_date   │     └──────────────┘  │
  │   │ metadata_     │     │ images        │                       │
  │   └───────────────┘     └───────────────┘                       │
  └──────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                      MESSAGE QUEUE                                │
  │                                                                   │
  │   ┌─────────────────────────────────────────────────────────┐   │
  │   │                    RabbitMQ                              │   │
  │   │                                                          │   │
  │   │   review_analysis queue:                                 │   │
  │   │   ┌───────────┐ ┌───────────┐ ┌───────────┐            │   │
  │   │   │{review_id}│ │{review_id}│ │{review_id}│  ...       │   │
  │   │   │{job_id}   │ │{job_id}   │ │{job_id}   │            │   │
  │   │   └───────────┘ └───────────┘ └───────────┘            │   │
  │   │                                                          │   │
  │   │   review_analysis_dlq (dead letter):                     │   │
  │   │   └── Failed messages after 3 retries                    │   │
  │   └─────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Workers consume
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                      AI ANALYSIS                                  │
  │                                                                   │
  │   ┌─────────────────────────────────────────────────────────┐   │
  │   │  Worker Process (x2 replicas)                            │   │
  │   │                                                          │   │
  │   │   1. Fetch review from DB                                │   │
  │   │   2. Call LLM (Llama 3.1 8B)                            │   │
  │   │   3. Parse JSON response                                 │   │
  │   │   4. Save to review_analysis                             │   │
  │   │   5. Update job progress                                 │   │
  │   └─────────────────────────────────────────────────────────┘   │
  │                              │                                    │
  │                              ▼                                    │
  │   ┌─────────────────────────────────────────────────────────┐   │
  │   │  LLM Output                                              │   │
  │   │                                                          │   │
  │   │  {                                                       │   │
  │   │    "sentiment": "positive",                              │   │
  │   │    "score": 0.92,                                        │   │
  │   │    "topics_positive": ["service", "food"],               │   │
  │   │    "topics_negative": [],                                │   │
  │   │    "language": "ar",                                     │   │
  │   │    "urgent": false,                                      │   │
  │   │    "summary_ar": "العميل راضي عن الخدمة والطعام",         │   │
  │   │    "summary_en": "Customer satisfied with service/food", │   │
  │   │    "suggested_reply_ar": "شكراً لك على تقييمك الجميل..."  │   │
  │   │  }                                                       │   │
  │   └─────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────┘
                                 │
                                 │ All reviews processed
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                      EMAIL NOTIFICATION                           │
  │                                                                   │
  │   ┌─────────────────────────────────────────────────────────┐   │
  │   │  Check: All jobs for ScrapeJob completed?                │   │
  │   │         └── Yes → Acquire advisory lock                  │   │
  │   │                   └── Generate HTML report               │   │
  │   │                       └── Send via SMTP                  │   │
  │   └─────────────────────────────────────────────────────────┘   │
  │                                                                   │
  │   ┌─────────────────────────────────────────────────────────┐   │
  │   │  Email Report Contents:                                  │   │
  │   │  ├── Overall sentiment distribution (pie chart)          │   │
  │   │  ├── Per-place breakdown                                 │   │
  │   │  │   ├── Positive topics                                 │   │
  │   │  │   ├── Negative topics                                 │   │
  │   │  │   └── Sample summaries                                │   │
  │   │  ├── Urgent issues list                                  │   │
  │   │  └── Recommended actions                                 │   │
  │   └─────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────┘
```

---

## 4. Database Schema (ERD)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           DATABASE SCHEMA (PostgreSQL)                               │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────┐
│              scrape_jobs                │
├────────────────────────────────────────┤
│ id              UUID        PK         │
│ query           VARCHAR(500)           │
│ status          VARCHAR(50)            │
│ scraper_job_id  VARCHAR(100)           │
│ pipeline_job_ids ARRAY(UUID)           │
│ places_found    INTEGER                │
│ reviews_total   INTEGER                │
│ reviews_processed INTEGER              │
│ error_message   TEXT                   │
│ notification_email VARCHAR(255)        │
│ email_sent_at   TIMESTAMP              │
│ created_at      TIMESTAMP              │
│ completed_at    TIMESTAMP              │
├────────────────────────────────────────┤
│ Status: pending → scraping →           │
│         processing → completed/failed  │
└───────────────────┬────────────────────┘
                    │
                    │ 1:N (pipeline_job_ids)
                    ▼
┌────────────────────────────────────────┐         ┌────────────────────────────────────────┐
│               places                    │         │                jobs                    │
├────────────────────────────────────────┤         ├────────────────────────────────────────┤
│ id              UUID        PK         │◀───┐    │ id              UUID        PK         │
│ name            VARCHAR(255)           │    │    │ place_id        UUID        FK ───────┐│
│ place_id        VARCHAR(255) UNIQUE    │    └────│ status          VARCHAR(50)           ││
│ category        VARCHAR(100)           │         │ total_reviews   INTEGER               ││
│ address         TEXT                   │         │ processed_reviews INTEGER             ││
│ rating          DECIMAL(2,1)           │         │ error_message   TEXT                  ││
│ review_count    INTEGER                │         │ created_at      TIMESTAMP             ││
│ reviews_per_rating JSONB               │         │ completed_at    TIMESTAMP             ││
│ metadata_       JSONB                  │         ├────────────────────────────────────────┤│
│ created_at      TIMESTAMP              │         │ Status: pending → queued →            ││
├────────────────────────────────────────┤         │         processing → completed/failed ││
│ metadata_ = {                          │         └────────────────────────────────────────┘│
│   link, website, phone,                │                                                   │
│   latitude, longitude,                 │                                                   │
│   complete_address, open_hours         │                                                   │
│ }                                      │                                                   │
└───────────────────┬────────────────────┘                                                   │
                    │                                                                        │
                    │ 1:N                                                                    │
                    ▼                                                                        │
┌────────────────────────────────────────┐                                                   │
│              reviews                    │                                                   │
├────────────────────────────────────────┤                                                   │
│ id              UUID        PK         │                                                   │
│ place_id        UUID        FK ────────┼───────────────────────────────────────────────────┘
│ job_id          UUID        FK ────────┼────────┐
│ author          VARCHAR(255)           │        │
│ rating          INTEGER (1-5)          │        │
│ text            TEXT                   │        │
│ review_date     VARCHAR(50)            │        │
│ profile_picture TEXT                   │        │
│ images          JSONB                  │        │
│ created_at      TIMESTAMP              │        │
└───────────────────┬────────────────────┘        │
                    │                              │
                    │ 1:1                          │
                    ▼                              │
┌────────────────────────────────────────┐        │
│          review_analysis               │        │
├────────────────────────────────────────┤        │
│ id              UUID        PK         │        │
│ review_id       UUID        FK UNIQUE ─┼────────┘
│ sentiment       VARCHAR(20)            │
│ score           DECIMAL(3,2) (0.0-1.0) │
│ topics_positive ARRAY(TEXT)            │
│ topics_negative ARRAY(TEXT)            │
│ language        VARCHAR(20)            │
│ urgent          BOOLEAN                │
│ summary_ar      TEXT                   │
│ summary_en      TEXT                   │
│ suggested_reply_ar TEXT                │
│ raw_response    JSONB                  │
│ analyzed_at     TIMESTAMP              │
├────────────────────────────────────────┤
│ sentiment: positive | neutral | negative│
│ topics: service, food, drinks, price,  │
│         cleanliness, wait_time, staff, │
│         quality, atmosphere, location, │
│         parking, delivery              │
│ language: ar | en | arabizi            │
└────────────────────────────────────────┘
```

---

## 5. Message Queue Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            RABBITMQ ARCHITECTURE                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                    PUBLISHER
                                 (orchestrator.py)
                                        │
                                        │ publish
                                        ▼
    ┌───────────────────────────────────────────────────────────────────────────┐
    │                         DEFAULT EXCHANGE                                   │
    │                          (direct routing)                                  │
    └───────────────────────────────────┬───────────────────────────────────────┘
                                        │
                                        │ routing_key: "review_analysis"
                                        ▼
    ┌───────────────────────────────────────────────────────────────────────────┐
    │                                                                            │
    │   ┌────────────────────────────────────────────────────────────────────┐  │
    │   │                    review_analysis queue                            │  │
    │   │                        (DURABLE)                                    │  │
    │   │                                                                     │  │
    │   │   Properties:                                                       │  │
    │   │   ├── x-dead-letter-exchange: "dlx"                                │  │
    │   │   ├── x-dead-letter-routing-key: "review_analysis_dlq"             │  │
    │   │   └── prefetch_count: 1                                            │  │
    │   │                                                                     │  │
    │   │   Message Format:                                                   │  │
    │   │   ┌─────────────────────────────────────────────┐                  │  │
    │   │   │ {                                           │                  │  │
    │   │   │   "review_id": "uuid-string",               │                  │  │
    │   │   │   "job_id": "uuid-string"                   │                  │  │
    │   │   │ }                                           │                  │  │
    │   │   │ delivery_mode: 2 (persistent)               │                  │  │
    │   │   └─────────────────────────────────────────────┘                  │  │
    │   └────────────────────────────────────────────────────────────────────┘  │
    │                                        │                                   │
    │                                        │ consume (basic_consume)           │
    │                                        ▼                                   │
    │   ┌────────────────────────────────────────────────────────────────────┐  │
    │   │                    WORKER POOL (2+ replicas)                        │  │
    │   │                                                                     │  │
    │   │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │  │
    │   │   │   Worker 1   │  │   Worker 2   │  │   Worker N   │            │  │
    │   │   │              │  │              │  │              │            │  │
    │   │   │ prefetch=1   │  │ prefetch=1   │  │ prefetch=1   │            │  │
    │   │   │ 2s delay     │  │ 2s delay     │  │ 2s delay     │            │  │
    │   │   └──────┬───────┘  └──────┬───────┘  └──────────────┘            │  │
    │   │          │                 │                                       │  │
    │   │          │    ┌────────────┘                                       │  │
    │   │          │    │                                                    │  │
    │   │          ▼    ▼                                                    │  │
    │   │   ┌─────────────────────────────────────────────────────────────┐ │  │
    │   │   │                    PROCESSING                                │ │  │
    │   │   │                                                              │ │  │
    │   │   │   Success:                                                   │ │  │
    │   │   │   └── basic_ack(delivery_tag) → Message removed             │ │  │
    │   │   │                                                              │ │  │
    │   │   │   Failure (retries < 3):                                     │ │  │
    │   │   │   └── basic_nack(requeue=True) → Back to queue              │ │  │
    │   │   │                                                              │ │  │
    │   │   │   Failure (retries >= 3):                                    │ │  │
    │   │   │   └── basic_nack(requeue=False) → Dead letter               │ │  │
    │   │   └─────────────────────────────────────────────────────────────┘ │  │
    │   └────────────────────────────────────────────────────────────────────┘  │
    │                                        │                                   │
    │                                        │ rejected (x-death)                │
    │                                        ▼                                   │
    │   ┌────────────────────────────────────────────────────────────────────┐  │
    │   │                           dlx EXCHANGE                              │  │
    │   │                          (dead letter)                              │  │
    │   └────────────────────────────────────┬───────────────────────────────┘  │
    │                                        │                                   │
    │                                        │ routing_key: "review_analysis_dlq"│
    │                                        ▼                                   │
    │   ┌────────────────────────────────────────────────────────────────────┐  │
    │   │                  review_analysis_dlq queue                          │  │
    │   │                      (DURABLE)                                      │  │
    │   │                                                                     │  │
    │   │   Contains:                                                         │  │
    │   │   ├── Messages that failed 3+ times                                │  │
    │   │   ├── LLM parsing errors                                           │  │
    │   │   └── Database save failures                                       │  │
    │   │                                                                     │  │
    │   │   Action: Manual inspection / retry                                │  │
    │   └────────────────────────────────────────────────────────────────────┘  │
    │                                                                            │
    └────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. LLM Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           LLM INTEGRATION (llm_client.py)                            │
└─────────────────────────────────────────────────────────────────────────────────────┘

    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                              WORKER                                            │
    │                                                                                │
    │   Input:                                                                       │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  Review {                                                                ││
    │   │    text: "الطعام ممتاز والخدمة سريعة بس الأسعار غالية شوي",              ││
    │   │    rating: 4                                                             ││
    │   │  }                                                                       ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────┬───────────────────────────────────────┘
                                            │
                                            │ POST /v1/chat/completions
                                            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                          vLLM SERVER (Host Machine)                            │
    │                                                                                │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  Model: meta-llama/Llama-3.1-8B-Instruct                                ││
    │   │  GPU: NVIDIA RTX 4090 (24GB VRAM)                                       ││
    │   │  Parameters:                                                             ││
    │   │    ├── max_model_len: 32000                                             ││
    │   │    ├── gpu_memory_utilization: 0.9                                      ││
    │   │    ├── temperature: 0.1 (deterministic)                                 ││
    │   │    └── max_tokens: 1000                                                 ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    │                                                                                │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  SYSTEM PROMPT                                                           ││
    │   │                                                                          ││
    │   │  You are a Saudi-focused review analysis expert.                         ││
    │   │                                                                          ││
    │   │  Capabilities:                                                           ││
    │   │  ├── Understand Saudi dialects (نجدي، حجازي)                            ││
    │   │  ├── Understand formal Arabic (فصحى)                                    ││
    │   │  ├── Understand Arabizi (3arabizi)                                      ││
    │   │  ├── Detect sentiment with confidence score                              ││
    │   │  └── Generate professional Saudi-friendly replies                        ││
    │   │                                                                          ││
    │   │  Output Format: JSON only, no markdown                                   ││
    │   │                                                                          ││
    │   │  Topics (pick from):                                                     ││
    │   │  service, food, drinks, price, cleanliness, wait_time,                  ││
    │   │  staff, quality, atmosphere, location, parking, delivery                 ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    │                                                                                │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  URGENCY DETECTION                                                       ││
    │   │                                                                          ││
    │   │  Mark urgent=true when:                                                  ││
    │   │  ├── Negative sentiment + score > 0.8 (high confidence negative)        ││
    │   │  ├── Health/safety issues mentioned                                      ││
    │   │  └── Escalation threats (سأشتكي، سأبلغ الجهات)                          ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────┬───────────────────────────────────────┘
                                            │
                                            │ JSON Response
                                            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                              OUTPUT                                            │
    │                                                                                │
    │   {                                                                            │
    │     "sentiment": "positive",                                                   │
    │     "score": 0.78,                                                             │
    │     "topics_positive": ["food", "service"],                                    │
    │     "topics_negative": ["price"],                                              │
    │     "language": "ar",                                                          │
    │     "urgent": false,                                                           │
    │     "summary_ar": "عميل راضي عن الطعام والخدمة مع ملاحظة على الأسعار",        │
    │     "summary_en": "Customer satisfied with food and service, notes high prices"│
    │     "suggested_reply_ar": "شكراً لزيارتكم الكريمة! نسعد بإعجابكم بطعامنا      │
    │       وخدمتنا، ونعمل دائماً على تقديم أفضل قيمة لعملائنا. نتمنى رؤيتكم قريباً!"│
    │   }                                                                            │
    └───────────────────────────────────────────────────────────────────────────────┘

    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                          RETRY LOGIC                                           │
    │                                                                                │
    │   Rate Limit (429):                                                            │
    │   ├── Attempt 1: Wait 30s                                                     │
    │   ├── Attempt 2: Wait 60s                                                     │
    │   └── Attempt 3: Wait 90s → Fail to DLQ                                       │
    │                                                                                │
    │   JSON Parse Error:                                                            │
    │   └── Immediate fail → DLQ                                                    │
    │                                                                                │
    │   Connection Error:                                                            │
    │   └── basic_nack(requeue=True) → Retry via queue                              │
    └───────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION DEPLOYMENT                                        │
│                       Tensordock VM (206.168.83.147)                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                   ┌────────────────┐
                                   │   INTERNET     │
                                   └────────┬───────┘
                                            │
                                   ┌────────▼───────┐
                                   │   Cloudflare   │
                                   │    Tunnel      │
                                   │  (Optional)    │
                                   └────────┬───────┘
                                            │
    ════════════════════════════════════════╪════════════════════════════════════════
                                            │
    ┌───────────────────────────────────────┼───────────────────────────────────────┐
    │                         HOST MACHINE  │                                       │
    │                                       │                                       │
    │   ┌───────────────────────────────────▼───────────────────────────────────┐  │
    │   │                        DOCKER NETWORK                                  │  │
    │   │                        (nurliya_default)                               │  │
    │   │                                                                        │  │
    │   │   ┌──────────────────────────────────────────────────────────────┐   │  │
    │   │   │                    INFRASTRUCTURE                             │   │  │
    │   │   │                                                               │   │  │
    │   │   │   ┌─────────────┐   ┌─────────────┐   ┌─────────────────┐   │   │  │
    │   │   │   │  postgres   │   │  rabbitmq   │   │    scraper      │   │   │  │
    │   │   │   │   :5432     │   │   :5672     │   │    :8080        │   │   │  │
    │   │   │   │             │   │   :15672    │   │                 │   │   │  │
    │   │   │   │ ┌─────────┐ │   │             │   │ ┌─────────────┐ │   │   │  │
    │   │   │   │ │ Volume  │ │   │ ┌─────────┐ │   │ │ Go binary   │ │   │   │  │
    │   │   │   │ │postgres │ │   │ │ Volume  │ │   │ │ -web mode   │ │   │   │  │
    │   │   │   │ │ _data   │ │   │ │rabbitmq │ │   │ │ Chromium    │ │   │   │  │
    │   │   │   │ └─────────┘ │   │ │ _data   │ │   │ └─────────────┘ │   │   │  │
    │   │   │   └─────────────┘   │ └─────────┘ │   └─────────────────┘   │   │  │
    │   │   │                     └─────────────┘                          │   │  │
    │   │   └──────────────────────────────────────────────────────────────┘   │  │
    │   │                                                                        │  │
    │   │   ┌──────────────────────────────────────────────────────────────┐   │  │
    │   │   │                     APPLICATION                               │   │  │
    │   │   │                                                               │   │  │
    │   │   │   ┌─────────────────────────────────────────────────────┐   │   │  │
    │   │   │   │                      api                             │   │   │  │
    │   │   │   │                     :8000                            │   │   │  │
    │   │   │   │                                                      │   │   │  │
    │   │   │   │   ┌──────────────────────────────────────────────┐  │   │   │  │
    │   │   │   │   │  FastAPI + Uvicorn                           │  │   │   │  │
    │   │   │   │   │  • REST endpoints                            │  │   │   │  │
    │   │   │   │   │  • Background orchestration                  │  │   │   │  │
    │   │   │   │   │  • Health checks                             │  │   │   │  │
    │   │   │   │   └──────────────────────────────────────────────┘  │   │   │  │
    │   │   │   │                                                      │   │   │  │
    │   │   │   │   Healthcheck: curl localhost:8000/health           │   │   │  │
    │   │   │   │   Depends on: postgres, rabbitmq, scraper            │   │   │  │
    │   │   │   └─────────────────────────────────────────────────────┘   │   │  │
    │   │   │                                                               │   │  │
    │   │   │   ┌─────────────────────────────────────────────────────┐   │   │  │
    │   │   │   │               worker (2 replicas)                    │   │   │  │
    │   │   │   │                                                      │   │   │  │
    │   │   │   │   ┌──────────────┐      ┌──────────────┐            │   │   │  │
    │   │   │   │   │   Worker 1   │      │   Worker 2   │            │   │   │  │
    │   │   │   │   │              │      │              │            │   │   │  │
    │   │   │   │   │ • Consume    │      │ • Consume    │            │   │   │  │
    │   │   │   │   │ • Analyze    │      │ • Analyze    │            │   │   │  │
    │   │   │   │   │ • Email      │      │ • Email      │            │   │   │  │
    │   │   │   │   └──────────────┘      └──────────────┘            │   │   │  │
    │   │   │   │                                                      │   │   │  │
    │   │   │   │   Depends on: postgres, rabbitmq, api                │   │   │  │
    │   │   │   │   Scale: make scale-workers WORKERS=N                │   │   │  │
    │   │   │   └─────────────────────────────────────────────────────┘   │   │  │
    │   │   │                                                               │   │  │
    │   │   │   ┌─────────────────────────────────────────────────────┐   │   │  │
    │   │   │   │                    Volumes                            │   │   │  │
    │   │   │   │                                                      │   │   │  │
    │   │   │   │   results:/app/results    ← CSV downloads            │   │   │  │
    │   │   │   │   postgres_data           ← Database persistence     │   │   │  │
    │   │   │   │   rabbitmq_data           ← Queue persistence        │   │   │  │
    │   │   │   └─────────────────────────────────────────────────────┘   │   │  │
    │   │   └──────────────────────────────────────────────────────────────┘   │  │
    │   └──────────────────────────────────────────────────────────────────────┘  │
    │                                        │                                     │
    │                                        │ host.docker.internal:8080           │
    │                                        ▼                                     │
    │   ┌──────────────────────────────────────────────────────────────────────┐  │
    │   │                         vLLM SERVER                                   │  │
    │   │                      (Host Process, not Docker)                       │  │
    │   │                                                                       │  │
    │   │   ┌─────────────────────────────────────────────────────────────┐   │  │
    │   │   │  vllm serve meta-llama/Llama-3.1-8B-Instruct \              │   │  │
    │   │   │       --port 8080 \                                         │   │  │
    │   │   │       --max-model-len 32000 \                               │   │  │
    │   │   │       --gpu-memory-utilization 0.9                          │   │  │
    │   │   └─────────────────────────────────────────────────────────────┘   │  │
    │   │                                                                       │  │
    │   │   ┌─────────────────────────────────────────────────────────────┐   │  │
    │   │   │  Hardware:                                                   │   │  │
    │   │   │  ├── GPU: NVIDIA RTX 4090 (24GB VRAM)                       │   │  │
    │   │   │  ├── CPU: High-performance server CPU                        │   │  │
    │   │   │  └── RAM: 32GB+ system memory                               │   │  │
    │   │   └─────────────────────────────────────────────────────────────┘   │  │
    │   └──────────────────────────────────────────────────────────────────────┘  │
    │                                                                              │
    └──────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. API Request/Response Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              API ENDPOINTS                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  POST /api/scrape                                                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   Request:                              Response:                                    │
│   ┌─────────────────────────────┐      ┌─────────────────────────────────────────┐ │
│   │ {                           │      │ {                                       │ │
│   │   "query": "cafes Riyadh",  │ ───▶ │   "job_id": "uuid",                     │ │
│   │   "depth": 20,              │      │   "status": "started"                   │ │
│   │   "lang": "ar",             │      │ }                                       │ │
│   │   "max_time": 300,          │      └─────────────────────────────────────────┘ │
│   │   "extra_reviews": true,    │                                                   │
│   │   "notification_email":     │                                                   │
│   │     "owner@cafe.sa"         │                                                   │
│   │ }                           │                                                   │
│   └─────────────────────────────┘                                                   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  GET /api/jobs/{job_id}                                                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   Response (in progress):               Response (completed):                        │
│   ┌─────────────────────────────┐      ┌─────────────────────────────────────────┐ │
│   │ {                           │      │ {                                       │ │
│   │   "id": "uuid",             │      │   "id": "uuid",                         │ │
│   │   "query": "cafes Riyadh",  │      │   "query": "cafes Riyadh",              │ │
│   │   "status": "processing",   │      │   "status": "completed",                │ │
│   │   "places_found": 15,       │      │   "places_found": 15,                   │ │
│   │   "reviews_total": 450,     │      │   "reviews_total": 450,                 │ │
│   │   "reviews_processed": 123  │      │   "reviews_processed": 450,             │ │
│   │ }                           │      │   "completed_at": "2024-..."            │ │
│   └─────────────────────────────┘      │ }                                       │ │
│                                         └─────────────────────────────────────────┘ │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  GET /api/places/{place_id}/reviews                                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   Response:                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │ {                                                                           │  │
│   │   "place": {                                                                │  │
│   │     "id": "uuid",                                                           │  │
│   │     "name": "Specialty Coffee",                                             │  │
│   │     "rating": 4.5                                                           │  │
│   │   },                                                                        │  │
│   │   "reviews": [                                                              │  │
│   │     {                                                                       │  │
│   │       "id": "uuid",                                                         │  │
│   │       "author": "Ahmed",                                                    │  │
│   │       "rating": 5,                                                          │  │
│   │       "text": "قهوة ممتازة!",                                               │  │
│   │       "analysis": {                                                         │  │
│   │         "sentiment": "positive",                                            │  │
│   │         "score": 0.95,                                                      │  │
│   │         "topics_positive": ["drinks", "quality"],                           │  │
│   │         "topics_negative": [],                                              │  │
│   │         "summary_ar": "عميل سعيد بجودة القهوة",                             │  │
│   │         "suggested_reply_ar": "شكراً لك! نسعد بإعجابك بقهوتنا"              │  │
│   │       }                                                                     │  │
│   │     },                                                                      │  │
│   │     ...                                                                     │  │
│   │   ]                                                                         │  │
│   │ }                                                                           │  │
│   └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  GET /api/places/{place_id}/stats                                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   Response:                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │ {                                                                           │  │
│   │   "place_id": "uuid",                                                       │  │
│   │   "total_reviews": 45,                                                      │  │
│   │   "analyzed_reviews": 45,                                                   │  │
│   │   "sentiment_distribution": {                                               │  │
│   │     "positive": 32,                                                         │  │
│   │     "neutral": 8,                                                           │  │
│   │     "negative": 5                                                           │  │
│   │   },                                                                        │  │
│   │   "sentiment_percentages": {                                                │  │
│   │     "positive": 71.1,                                                       │  │
│   │     "neutral": 17.8,                                                        │  │
│   │     "negative": 11.1                                                        │  │
│   │   },                                                                        │  │
│   │   "top_positive_topics": [                                                  │  │
│   │     {"topic": "service", "count": 28},                                      │  │
│   │     {"topic": "food", "count": 22}                                          │  │
│   │   ],                                                                        │  │
│   │   "top_negative_topics": [                                                  │  │
│   │     {"topic": "wait_time", "count": 4},                                     │  │
│   │     {"topic": "price", "count": 3}                                          │  │
│   │   ],                                                                        │  │
│   │   "urgent_count": 2,                                                        │  │
│   │   "average_confidence": 0.87                                                │  │
│   │ }                                                                           │  │
│   └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Email Report Structure

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            EMAIL REPORT TEMPLATE                                     │
│                          (email_report.html - Jinja2)                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                      │
│   ╔═══════════════════════════════════════════════════════════════════════════════╗│
│   ║                         NURLIYA ANALYSIS REPORT                                ║│
│   ║                                                                                ║│
│   ║   Query: "cafes in Riyadh"                                                     ║│
│   ║   Date: 2024-01-15                                                             ║│
│   ║   Places Analyzed: 15                                                          ║│
│   ║   Total Reviews: 450                                                           ║│
│   ╚═══════════════════════════════════════════════════════════════════════════════╝│
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────────┐│
│   │  OVERALL SENTIMENT                                                            ││
│   │                                                                               ││
│   │  Positive  ████████████████████████████████░░░░░░░░░░  71% (320)             ││
│   │  Neutral   ███████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  18% (81)              ││
│   │  Negative  █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  11% (49)              ││
│   │                                                                               ││
│   └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────────┐│
│   │  ⚠️  URGENT ISSUES (3)                                                        ││
│   │                                                                               ││
│   │  • Specialty Coffee - "تسمم غذائي بعد زيارتي" (health concern)               ││
│   │  • Cafe Latte - "سأبلغ الجهات المختصة" (escalation threat)                   ││
│   │  • Bean House - "انتظرت ساعة للطلب" (severe service issue)                   ││
│   │                                                                               ││
│   └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────────┐│
│   │  PER-PLACE BREAKDOWN                                                          ││
│   │                                                                               ││
│   │  ┌─────────────────────────────────────────────────────────────────────────┐ ││
│   │  │  📍 Specialty Coffee (★ 4.5)                                            │ ││
│   │  │  Reviews: 45 | Positive: 38 | Negative: 3                               │ ││
│   │  │                                                                         │ ││
│   │  │  ✅ Strengths: service (28), drinks (22), atmosphere (15)               │ ││
│   │  │  ❌ Weaknesses: price (3), wait_time (2)                                │ ││
│   │  │                                                                         │ ││
│   │  │  Sample Positive: "خدمة ممتازة وقهوة لذيذة"                             │ ││
│   │  │  Sample Negative: "الأسعار مرتفعة مقارنة بالمنافسين"                    │ ││
│   │  └─────────────────────────────────────────────────────────────────────────┘ ││
│   │                                                                               ││
│   │  ┌─────────────────────────────────────────────────────────────────────────┐ ││
│   │  │  📍 Cafe Latte (★ 4.2)                                                  │ ││
│   │  │  Reviews: 32 | Positive: 25 | Negative: 4                               │ ││
│   │  │  ...                                                                    │ ││
│   │  └─────────────────────────────────────────────────────────────────────────┘ ││
│   │                                                                               ││
│   └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────────┐│
│   │  📋 RECOMMENDED ACTIONS                                                       ││
│   │                                                                               ││
│   │  1. Address urgent health concern at Specialty Coffee immediately            ││
│   │  2. Respond to escalation threat at Cafe Latte within 24 hours              ││
│   │  3. Review pricing strategy - mentioned in 15% of negative reviews          ││
│   │  4. Improve wait times during peak hours (12pm-2pm)                         ││
│   │  5. Leverage positive service feedback in marketing                         ││
│   │                                                                               ││
│   └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────────┐│
│   │                                                                               ││
│   │  🤖 Generated by Nurliya AI                                                   ││
│   │  Powered by Llama 3.1 8B                                                     ││
│   │                                                                               ││
│   └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. System Capabilities & Limits

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           PERFORMANCE CHARACTERISTICS                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────┬────────────────────────────────────────────────┐
│           COMPONENT                │              THROUGHPUT                         │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  Google Maps Scraper               │  ~120 places/minute                            │
│  Extended Reviews                  │  Up to 300+ reviews/place                      │
│  LLM Analysis (per worker)         │  ~30 reviews/minute (2s delay)                 │
│  Email Generation                  │  ~10 reports/minute                            │
│  RabbitMQ                          │  ~10,000 messages/second (theoretical)         │
│  PostgreSQL                        │  ~5,000 inserts/second                         │
└────────────────────────────────────┴────────────────────────────────────────────────┘

┌────────────────────────────────────┬────────────────────────────────────────────────┐
│           SCALING                  │              STRATEGY                           │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  Workers                           │  Horizontal: 2 → N replicas                    │
│                                    │  Command: make scale-workers WORKERS=8         │
│  Database                          │  Connection pooling (SQLAlchemy)               │
│  vLLM                              │  Single GPU, optimize batch size               │
│  Scraper                           │  Rate-limited by Google (single instance)      │
└────────────────────────────────────┴────────────────────────────────────────────────┘

┌────────────────────────────────────┬────────────────────────────────────────────────┐
│           ERROR HANDLING           │              MECHANISM                          │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  Scraper Failures                  │  Status tracked, error_message stored          │
│  LLM Rate Limits                   │  Exponential backoff (30s, 60s, 90s)           │
│  LLM Parse Errors                  │  Immediate DLQ routing                         │
│  Database Failures                 │  Transaction rollback                          │
│  Message Processing                │  3 retries → Dead Letter Queue                 │
│  Worker Crashes                    │  Docker restart policy: on-failure             │
│  Duplicate Emails                  │  PostgreSQL advisory locks                     │
└────────────────────────────────────┴────────────────────────────────────────────────┘
```

---

## 11. File Structure

```
/home/user/nurliya/
│
├── .env                              # Local development credentials
├── .env.production                   # Production credentials
├── .env.production.example           # Template for production
├── docker-compose.yml                # Service orchestration (116 lines)
├── Makefile                          # Common operations
├── ARCHITECTURE.md                   # This document
│
├── pipline/                          # Python application
│   ├── Dockerfile                    # Container definition (23 lines)
│   ├── requirements.txt              # Python dependencies (12 packages)
│   │
│   ├── api.py                        # FastAPI REST server (408 lines)
│   ├── orchestrator.py               # Pipeline orchestration (250 lines)
│   ├── worker.py                     # Queue consumer (268 lines)
│   │
│   ├── scraper_client.py             # Go scraper HTTP client (179 lines)
│   ├── csv_parser.py                 # CSV parsing & normalization (137 lines)
│   ├── producer.py                   # CLI CSV processor (102 lines)
│   │
│   ├── llm_client.py                 # vLLM interface (118 lines)
│   ├── email_service.py              # Report generation (313 lines)
│   │
│   ├── database.py                   # SQLAlchemy models (115 lines)
│   ├── rabbitmq.py                   # Queue setup (68 lines)
│   ├── config.py                     # Secrets & config with GCP Secret Manager support (115 lines)
│   │
│   └── templates/
│       └── email_report.html         # Jinja2 email template (451 lines)
│
└── google-maps-scraper/              # Go scraper project
    ├── Dockerfile                    # Scraper container
    ├── main.go                       # Entry point
    ├── gmaps/                        # Core scraping logic
    │   ├── place.go                  # Place data extraction
    │   ├── reviews.go                # Review extraction
    │   └── entry.go                  # Entry point handling
    └── web/                          # Web API mode
        └── web.go                    # HTTP server
```

---

## 12. Quick Start Commands

```bash
# Development
make up-build              # Start all services with fresh build
make logs                  # Stream all logs
make health                # Check API health

# Scaling
make scale-workers WORKERS=4   # Scale worker replicas

# Testing
make test-scrape           # Send test scrape request

# Debugging
make logs-api              # API logs only
make logs-worker           # Worker logs only
docker exec -it nurliya-postgres-1 psql -U nurliya  # DB shell
```

---

*Document generated for Nurliya v1.0*
*Last updated: January 2026*
