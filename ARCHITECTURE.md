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
│    ✓ AI sentiment analysis (Gemini 2.0 Flash)                              │
│    ✓ Saudi dialect-aware Arabic processing                                  │
│    ✓ Auto-generated professional replies                                    │
│    ✓ Email reports with actionable insights                                │
│    ✓ Anomaly detection with LLM-powered insights                           │
│    ✓ Real-time WebSocket updates                                           │
│    ✓ JWT authentication & multi-user support                               │
│    ✓ Client portal & admin dashboard                                       │
│    ✓ REST API for integration                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. High-Level System Architecture

```
                                    ┌──────────────────┐
                                    │    End Users     │
                                    │  (Web/API)       │
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
│    │   ┌─────────────────┐      ┌──────────▼──────────┐      ┌─────────────────┐  │   │
│    │   │ Client Portal   │      │      API Layer      │      │    Dashboard    │  │   │
│    │   │   (Next.js)     │      │    (FastAPI:8000)   │      │   (Next.js)     │  │   │
│    │   │    :3002        │      │                     │      │    :3000        │  │   │
│    │   │                 │      │  • REST Endpoints   │      │                 │  │   │
│    │   │ • User Auth     │◀────▶│  • JWT Auth         │◀────▶│ • Real-time     │  │   │
│    │   │ • Overview      │      │  • WebSocket        │      │ • Monitoring    │  │   │
│    │   │ • Analytics     │      │  • Background Tasks │      │ • Logs          │  │   │
│    │   └─────────────────┘      └──────────┬──────────┘      └─────────────────┘  │   │
│    │                                       │                                        │   │
│    │              ┌────────────────────────┼────────────────────────┐              │   │
│    │              │                        │                        │              │   │
│    │              ▼                        ▼                        ▼              │   │
│    │    ┌─────────────────┐    ┌─────────────────────┐    ┌──────────────────┐   │   │
│    │    │  Go Scraper     │    │    PostgreSQL       │    │    RabbitMQ      │   │   │
│    │    │   :8080         │    │     :5432           │    │     :5672        │   │   │
│    │    │                 │    │                     │    │                  │   │   │
│    │    │ • Google Maps   │    │  • users            │    │ • review_analysis│   │   │
│    │    │ • 33+ fields    │    │  • places           │    │ • dlq            │   │   │
│    │    │ • CSV output    │    │  • reviews          │    │                  │   │   │
│    │    └─────────────────┘    │  • jobs             │    └────────┬─────────┘   │   │
│    │                           │  • scrape_jobs      │             │              │   │
│    │                           │  • review_analysis  │             │              │   │
│    │    ┌─────────────────┐    │  • anomaly_insights │             │              │   │
│    │    │    pgAdmin      │    │  • activity_logs    │             │              │   │
│    │    │     :5050       │───▶└─────────────────────┘             │              │   │
│    │    └─────────────────┘                                        │              │   │
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
                                                          │   Gemini API        │
                                                          │   (Google Cloud)    │
                                                          │                     │
                                                          │  • Gemini 2.0 Flash │
                                                          │  • OpenAI-compat    │
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
│  │   ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐  │   │
│  │   │  client-portal/    │    │    dashboard/      │    │    api.py       │  │   │
│  │   │  (Next.js)         │    │    (Next.js)       │    │   (FastAPI)     │  │   │
│  │   │                    │    │                    │    │                 │  │   │
│  │   │ • User login/reg   │    │ • System monitor   │    │ • REST API      │  │   │
│  │   │ • Overview metrics │    │ • Real-time stats  │    │ • WebSocket     │  │   │
│  │   │ • Sentiment trends │    │ • Activity logs    │    │ • Auth deps     │  │   │
│  │   │ • Anomaly insights │    │ • Queue status     │    │                 │  │   │
│  │   └────────────────────┘    └────────────────────┘    └─────────────────┘  │   │
│  │                                                                              │   │
│  │   API Endpoints:                                                             │   │
│  │   ├── GET  /health                    → Health check                        │   │
│  │   ├── POST /api/auth/register         → User registration                   │   │
│  │   ├── POST /api/auth/login            → User login                          │   │
│  │   ├── GET  /api/auth/me               → Current user profile                │   │
│  │   ├── POST /api/scrape                → Start scrape job (auth required)    │   │
│  │   ├── GET  /api/jobs                  → List user's jobs (auth required)    │   │
│  │   ├── GET  /api/jobs/{id}             → Job status/progress                 │   │
│  │   ├── GET  /api/places                → List scraped places                 │   │
│  │   ├── GET  /api/places/{id}           → Place details                       │   │
│  │   ├── GET  /api/places/{id}/reviews   → Reviews + AI analysis               │   │
│  │   ├── GET  /api/places/{id}/stats     → Sentiment statistics                │   │
│  │   ├── GET  /api/overview              → Client portal overview (auth)       │   │
│  │   ├── GET  /api/sentiment-trend       → Sentiment trends + anomalies (auth) │   │
│  │   ├── GET  /api/sentiment-trend/{date}/reviews → Reviews for date (auth)    │   │
│  │   ├── GET  /api/stats                 → System-wide statistics              │   │
│  │   ├── GET  /api/queue-status          → RabbitMQ queue status               │   │
│  │   ├── GET  /api/recent-analyses       → Recent review analyses              │   │
│  │   ├── GET  /api/system-health         → All component health                │   │
│  │   ├── GET  /api/logs                  → Paginated activity logs             │   │
│  │   └── WS   /ws                        → Real-time WebSocket updates         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                           │
│                                         ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         ORCHESTRATION LAYER                                  │   │
│  │                                                                              │   │
│  │   ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐  │   │
│  │   │  orchestrator.py   │    │  scraper_client.py │    │    auth.py      │  │   │
│  │   │                    │    │                    │    │                 │  │   │
│  │   │ • Pipeline control │    │ • HTTP client      │    │ • JWT tokens    │  │   │
│  │   │ • Job lifecycle    │    │ • Job polling      │    │ • User auth     │  │   │
│  │   │ • Error handling   │    │ • CSV download     │    │ • Password hash │  │   │
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
│  │   │                                         │   • Log activity        │ │ │   │
│  │   │                                         └─────────────────────────┘ │ │   │
│  │   └──────────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                              │   │
│  │   ┌────────────────────┐    ┌────────────────────────────────────────────┐ │   │
│  │   │   llm_client.py    │    │              email_service.py              │ │   │
│  │   │                    │    │                                            │ │   │
│  │   │ • OpenAI-compat    │    │ • HTML report generation (Jinja2)         │ │   │
│  │   │ • Gemini API       │    │ • Sentiment visualization                 │ │   │
│  │   │ • System prompts   │    │ • Per-place insights                      │ │   │
│  │   │ • JSON parsing     │    │ • SMTP delivery (async)                   │ │   │
│  │   │ • Anomaly insights │    │ • RTL Arabic support                      │ │   │
│  │   └────────────────────┘    └────────────────────────────────────────────┘ │   │
│  │                                                                              │   │
│  │   ┌────────────────────┐    ┌────────────────────────────────────────────┐ │   │
│  │   │ activity_logger.py │    │           logging_config.py                │ │   │
│  │   │                    │    │                                            │ │   │
│  │   │ • Database logging │    │ • Structured logging                      │ │   │
│  │   │ • Event tracking   │    │ • Service identification                  │ │   │
│  │   │ • Activity feed    │    │ • JSON formatting                         │ │   │
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
│  │   │ • 7 table models   │    │ • DLQ routing      │    │ • GCP Secrets   │  │   │
│  │   │ • Session mgmt     │    │ • Message publish  │    │ • Defaults      │  │   │
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
  │             │
  │ + JWT Token │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
  │  Validate   │────────▶│   Create    │────────▶│   Call Go   │
  │  JWT Auth   │         │ ScrapeJob   │         │  Scraper    │
  │             │         │ (+ user_id) │         │   API       │
  └─────────────┘         └─────────────┘         └──────┬──────┘
                                                         │
                                                         │ Poll status
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
  │   │   2. Call Gemini API (OpenAI-compatible)                │   │
  │   │   3. Parse JSON response                                 │   │
  │   │   4. Save to review_analysis                             │   │
  │   │   5. Update job progress                                 │   │
  │   │   6. Log activity                                        │   │
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
  │   │                           └── Log activity               │   │
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

## 4. Scraper & Pipeline Deep Dive

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    SCRAPER + PIPELINE FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

  USER REQUEST                          ORCHESTRATOR                           GO SCRAPER
 ══════════════                        ══════════════                         ═══════════════

 ┌─────────────────┐
 │ POST /api/scrape│
 │ {               │
 │  query: "cafes  │
 │    in Riyadh",  │
 │  depth: 20,     │
 │  lang: "ar"     │
 │ }               │
 └────────┬────────┘
          │
          ▼
 ┌─────────────────┐        ┌─────────────────┐        ┌─────────────────────────────────┐
 │  create_scrape  │───────▶│ ScrapeJob       │        │        GO SCRAPER               │
 │     _job()      │        │ (status:pending)│        │       (Docker :8080)            │
 │                 │        └─────────────────┘        │                                 │
 │ • user_id       │                                   │  ┌───────────────────────────┐ │
 │ • query         │                                   │  │ Chromium Headless Browser │ │
 │ • notif. email  │                                   │  │ • Scroll Google Maps      │ │
 └────────┬────────┘                                   │  │ • Extract 33+ fields      │ │
          │                                            │  │ • Up to 300 reviews/place │ │
          │ Background Task                            │  └───────────────────────────┘ │
          ▼                                            │                                 │
 ┌─────────────────────────────────────────────────────┼─────────────────────────────────┤
 │                   run_scrape_pipeline()             │                                 │
 │                                                     │                                 │
 │  ┌─────────────────────────────────────────────────┐│                                │
 │  │ STEP 1: Create Scraper Job                      ││                                │
 │  │                                                 ││                                │
 │  │  ScraperClient.create_job()                     ││  POST /api/v1/jobs             │
 │  │  ┌─────────────────────────────┐               ││  ┌───────────────────────────┐ │
 │  │  │ {                           │───────────────┼┼─▶│ Go scraper creates job    │ │
 │  │  │   name: "cafes in Riyadh",  │               ││  │ Returns: { id: "abc123" } │ │
 │  │  │   keywords: [...],          │               ││  └───────────────────────────┘ │
 │  │  │   depth: 20,                │               ││                                │
 │  │  │   lang: "ar",               │               ││                                │
 │  │  │   extra_reviews: true,      │               ││                                │
 │  │  │   max_time: 300             │               ││                                │
 │  │  │ }                           │               ││                                │
 │  │  └─────────────────────────────┘               ││                                │
 │  │                                                 ││                                │
 │  │  ScrapeJob.status = "scraping"                 ││                                │
 │  └─────────────────────────────────────────────────┘│                                │
 │                       │                             │                                 │
 │                       ▼                             │                                 │
 │  ┌─────────────────────────────────────────────────┐│                                │
 │  │ STEP 2: Poll Until Completion                   ││                                │
 │  │                                                 ││                                │
 │  │  while status != "ok":                          ││  GET /api/v1/jobs/{id}         │
 │  │    GET scraper status ─────────────────────────┼┼─▶ { Status: "working" }        │
 │  │    sleep(5 seconds)                            ││                                │
 │  │                                                 ││  Status values:                │
 │  │  Timeout: max_time + 60s buffer                ││  • pending → working → ok      │
 │  │                                                 ││  • failed                      │
 │  └─────────────────────────────────────────────────┘│                                │
 │                       │                             │                                 │
 │                       ▼                             │                                 │
 │  ┌─────────────────────────────────────────────────┐│                                │
 │  │ STEP 3: Download CSV                            ││                                │
 │  │                                                 ││  GET /api/v1/jobs/{id}/download│
 │  │  ScraperClient.download_csv() ─────────────────┼┼─▶ Returns: CSV file bytes      │
 │  │                                                 ││                                │
 │  │  Saved to: /app/results/{scrape_job_id}.csv    ││                                │
 │  └─────────────────────────────────────────────────┘│                                │
 │                       │                             └─────────────────────────────────┘
 │                       │
 │                       ▼
 │  ┌───────────────────────────────────────────────────────────────────────────────────┐
 │  │ STEP 4: Parse CSV (csv_parser.py)                                                 │
 │  │                                                                                   │
 │  │  CSV Structure (per row = 1 place):                                              │
 │  │  ┌─────────────────────────────────────────────────────────────────────────────┐│
 │  │  │ title | place_id | category | address | rating | latitude | longitude | ... ││
 │  │  │───────────────────────────────────────────────────────────────────────────────││
 │  │  │ user_reviews: [{"author":"...", "rating":5, "text":"...", ...}, ...]        ││
 │  │  │ user_reviews_extended: [up to ~300 reviews with full details]               ││
 │  │  └─────────────────────────────────────────────────────────────────────────────┘│
 │  │                                                                                   │
 │  │  parse_csv() does:                                                               │
 │  │  1. Read CSV with pandas                                                         │
 │  │  2. For each row (place):                                                        │
 │  │     • Extract place metadata (33+ fields)                                        │
 │  │     • Parse user_reviews JSON                                                    │
 │  │     • Parse user_reviews_extended JSON                                           │
 │  │     • Merge & deduplicate reviews                                                │
 │  │     • Handle NaN/null values                                                     │
 │  │  3. Return list of place dicts with reviews                                      │
 │  └───────────────────────────────────────────────────────────────────────────────────┘
 │                       │
 │                       ▼
 │  ┌───────────────────────────────────────────────────────────────────────────────────┐
 │  │ STEP 5: Save to Database & Queue Reviews (run_producer_sync)                      │
 │  │                                                                                   │
 │  │  For each place:                                                                  │
 │  │  ┌─────────────────────────────────────────────────────────────────────────────┐│
 │  │  │                                                                              ││
 │  │  │  save_place_and_reviews()                                                    ││
 │  │  │  ├── Upsert Place record (dedupe by place_id)                               ││
 │  │  │  └── Insert Review records (dedupe by place+author+date)                    ││
 │  │  │                                                                              ││
 │  │  │  create_job()                                                                ││
 │  │  │  └── Job record (status: pending, total_reviews: N)                         ││
 │  │  │                                                                              ││
 │  │  │  For each review:                                                            ││
 │  │  │  ├── Update review.job_id                                                   ││
 │  │  │  └── publish_message() → RabbitMQ                                           ││
 │  │  │      { "review_id": "uuid", "job_id": "uuid" }                              ││
 │  │  │                                                                              ││
 │  │  │  update_job_status(job_id, "queued")                                        ││
 │  │  └─────────────────────────────────────────────────────────────────────────────┘│
 │  │                                                                                   │
 │  │  ScrapeJob.status = "processing"                                                 │
 │  │  ScrapeJob.pipeline_job_ids = [job1.id, job2.id, ...]                           │
 │  └───────────────────────────────────────────────────────────────────────────────────┘
 │                       │
 │                       ▼
 │  ┌───────────────────────────────────────────────────────────────────────────────────┐
 │  │ STEP 6: Update Final Status                                                       │
 │  │                                                                                   │
 │  │  ScrapeJob.status = "completed"                                                  │
 │  │  ScrapeJob.places_found = N                                                      │
 │  │  ScrapeJob.reviews_total = M                                                     │
 │  │  ScrapeJob.completed_at = now()                                                  │
 │  │                                                                                   │
 │  │  log_scrape_completed() → ActivityLog                                            │
 │  └───────────────────────────────────────────────────────────────────────────────────┘
 │                                                                                       │
 └───────────────────────────────────────────────────────────────────────────────────────┘


        WORKER PROCESSING                               DATABASE UPDATES
       ═══════════════════                             ══════════════════

 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                              WORKER (worker.py)                                         │
 │                              (2+ Replicas)                                              │
 │                                                                                         │
 │   ┌────────────────────────────────────────────────────────────────────────────────┐  │
 │   │                    MESSAGE CONSUMPTION                                          │  │
 │   │                                                                                 │  │
 │   │   RabbitMQ Queue: "review_analysis"                                            │  │
 │   │   ┌─────────────────┐                                                          │  │
 │   │   │ {"review_id":   │                                                          │  │
 │   │   │  "uuid",        │◀─── basic_consume (prefetch=1)                           │  │
 │   │   │  "job_id":      │                                                          │  │
 │   │   │  "uuid"}        │                                                          │  │
 │   │   └────────┬────────┘                                                          │  │
 │   │            │                                                                    │  │
 │   └────────────┼────────────────────────────────────────────────────────────────────┘  │
 │                │                                                                        │
 │                ▼                                                                        │
 │   ┌────────────────────────────────────────────────────────────────────────────────┐  │
 │   │                    process_message()                                            │  │
 │   │                                                                                 │  │
 │   │   1. Fetch review from PostgreSQL                                              │  │
 │   │      ┌──────────────────────────────────────────────────────────────────────┐ │  │
 │   │      │ SELECT * FROM reviews WHERE id = {review_id}                         │ │  │
 │   │      │ → review_text, review_rating, place_name                             │ │  │
 │   │      └──────────────────────────────────────────────────────────────────────┘ │  │
 │   │                                                                                 │  │
 │   │   2. Skip if empty text                                                        │  │
 │   │      → basic_ack, update_job_progress                                          │  │
 │   │                                                                                 │  │
 │   │   3. Call LLM with retry (max 3 attempts)                                      │  │
 │   │      ┌──────────────────────────────────────────────────────────────────────┐ │  │
 │   │      │ analyze_review(review_text, rating)                                  │ │  │
 │   │      │                                                                      │ │  │
 │   │      │ → Gemini API (POST /v1/chat/completions)                            │ │  │
 │   │      │                                                                      │ │  │
 │   │      │ Retry on 429 (rate limit):                                          │ │  │
 │   │      │   Attempt 1: wait 30s                                               │ │  │
 │   │      │   Attempt 2: wait 60s                                               │ │  │
 │   │      │   Attempt 3: wait 90s → fail to DLQ                                 │ │  │
 │   │      └──────────────────────────────────────────────────────────────────────┘ │  │
 │   │                                                                                 │  │
 │   │   4. Save analysis to database                                                 │  │
 │   │      ┌──────────────────────────────────────────────────────────────────────┐ │  │
 │   │      │ INSERT INTO review_analysis (                                        │ │  │
 │   │      │   review_id, sentiment, score, topics_positive, topics_negative,    │ │  │
 │   │      │   language, urgent, summary_ar, summary_en, suggested_reply_ar      │ │  │
 │   │      │ )                                                                    │ │  │
 │   │      └──────────────────────────────────────────────────────────────────────┘ │  │
 │   │                                                                                 │  │
 │   │   5. Update job progress                                                       │  │
 │   │      ┌──────────────────────────────────────────────────────────────────────┐ │  │
 │   │      │ UPDATE jobs SET processed_reviews = processed_reviews + 1            │ │  │
 │   │      │                                                                      │ │  │
 │   │      │ IF processed_reviews >= total_reviews:                               │ │  │
 │   │      │   SET status = "completed", completed_at = NOW()                     │ │  │
 │   │      │   → detect_and_queue_anomalies()                                     │ │  │
 │   │      │   → check_and_send_scrape_job_report()                               │ │  │
 │   │      └──────────────────────────────────────────────────────────────────────┘ │  │
 │   │                                                                                 │  │
 │   │   6. Acknowledge message                                                       │  │
 │   │      → basic_ack(delivery_tag)                                                 │  │
 │   │                                                                                 │  │
 │   │   7. Rate limit delay: sleep(2 seconds)                                        │  │
 │   │                                                                                 │  │
 │   └────────────────────────────────────────────────────────────────────────────────┘  │
 │                                                                                        │
 └────────────────────────────────────────────────────────────────────────────────────────┘


       JOB COMPLETION                                  EMAIL NOTIFICATION
      ════════════════                                ══════════════════════

 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                     COMPLETION CHECKS (when job.processed = job.total)                  │
 │                                                                                         │
 │   ┌────────────────────────────────────────────────────────────────────────────────┐  │
 │   │                detect_and_queue_anomalies(job_id)                               │  │
 │   │                                                                                 │  │
 │   │   1. Get all reviews + analyses for place                                       │  │
 │   │   2. Aggregate by day → positive percentage                                     │  │
 │   │   3. Calculate mean & standard deviation                                        │  │
 │   │   4. Find anomalies where |z-score| > 2                                        │  │
 │   │   5. For each anomaly:                                                          │  │
 │   │      → Queue to "anomaly_insights" for LLM analysis                            │  │
 │   │      → Worker processes: generate_anomaly_insight()                            │  │
 │   │      → Save to anomaly_insights table                                          │  │
 │   └────────────────────────────────────────────────────────────────────────────────┘  │
 │                                                                                         │
 │   ┌────────────────────────────────────────────────────────────────────────────────┐  │
 │   │                check_and_send_scrape_job_report(job_id)                         │  │
 │   │                                                                                 │  │
 │   │   1. Find parent ScrapeJob                                                      │  │
 │   │   2. Check if notification_email configured                                     │  │
 │   │   3. Acquire PostgreSQL advisory lock (prevent duplicates)                     │  │
 │   │   4. Check if ALL pipeline jobs completed                                       │  │
 │   │   5. Mark email_sent_at = NOW() (inside lock)                                  │  │
 │   │   6. Release lock                                                               │  │
 │   │   7. gather_scrape_job_stats() → report data                                   │  │
 │   │   8. send_completion_report()                                                   │  │
 │   │      ┌────────────────────────────────────────────────────────────────────┐   │  │
 │   │      │ HTML Email Report:                                                  │   │  │
 │   │      │ • Query summary                                                     │   │  │
 │   │      │ • Places & reviews count                                            │   │  │
 │   │      │ • Overall sentiment distribution                                    │   │  │
 │   │      │ • Per-place breakdown (strengths/weaknesses)                        │   │  │
 │   │      │ • Urgent issues list                                                │   │  │
 │   │      │ • Recommended actions                                               │   │  │
 │   │      └────────────────────────────────────────────────────────────────────┘   │  │
 │   └────────────────────────────────────────────────────────────────────────────────┘  │
 │                                                                                         │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Component Summary

| Component | File | Responsibility |
|-----------|------|----------------|
| **ScraperClient** | `scraper_client.py` | HTTP client for Go scraper API (create job, poll status, download CSV) |
| **Orchestrator** | `orchestrator.py` | Pipeline coordination: scraper → CSV → DB → queue |
| **CSV Parser** | `csv_parser.py` | Parse Google Maps CSV, extract 33+ fields, merge reviews |
| **Producer** | `producer.py` | Create Job records, queue reviews to RabbitMQ |
| **Worker** | `worker.py` | Consume queue, call LLM, save analysis, trigger email |
| **Go Scraper** | `google-maps-scraper/` | Chromium-based Google Maps extraction |

### Data Flow Timeline

```
T+0s    POST /api/scrape               → ScrapeJob created (pending)
T+1s    ScraperClient.create_job()     → Go scraper starts (scraping)
T+30s   Polling...                     → Status: working
T+120s  Scraper completes              → Status: ok
T+121s  Download CSV                   → {scrape_job_id}.csv saved
T+122s  Parse CSV                      → Extract places + reviews
T+125s  Save to DB + Queue             → ScrapeJob (processing)
        └── For each place:
            ├── Place record saved
            ├── Reviews saved
            ├── Job record created
            └── Reviews queued to RabbitMQ

T+130s  Workers consume messages
        └── For each review:
            ├── Fetch from DB
            ├── Call Gemini API (~2s)
            ├── Save ReviewAnalysis
            └── Update Job progress

T+300s  All reviews processed          → Jobs completed
        ├── Anomaly detection runs
        └── Email report sent (if configured)

T+301s  ScrapeJob status = "completed"
```

---

## 5. Database Schema (ERD)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           DATABASE SCHEMA (PostgreSQL)                               │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────┐
│                users                   │
├────────────────────────────────────────┤
│ id              UUID        PK         │
│ email           VARCHAR(255) UNIQUE    │
│ password_hash   VARCHAR(255)           │
│ name            VARCHAR(255)           │
│ is_active       BOOLEAN     DEFAULT T  │
│ created_at      TIMESTAMP              │
│ updated_at      TIMESTAMP              │
├────────────────────────────────────────┤
│ • Passwords hashed with bcrypt         │
│ • Email indexed for fast lookups       │
└───────────────────┬────────────────────┘
                    │
                    │ 1:N
                    ▼
┌────────────────────────────────────────┐
│              scrape_jobs               │
├────────────────────────────────────────┤
│ id              UUID        PK         │
│ user_id         UUID        FK ────────┼──▶ users.id
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
│               places                   │         │                jobs                    │
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
│              reviews                   │                                                   │
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
├────────────────────────────────────────┤        │
│ Index: ix_reviews_duplicate_check      │        │
│        (place_id, author, review_date) │        │
└───────────────────┬────────────────────┘        │
                    │                              │
                    │ 1:1                          │
                    ▼                              │
┌────────────────────────────────────────┐        │
│          review_analysis              │        │
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

┌────────────────────────────────────────┐
│          anomaly_insights             │
├────────────────────────────────────────┤
│ id              UUID        PK         │
│ place_id        UUID        FK ───────▶│ places.id
│ date            VARCHAR(20)            │  (YYYY-MM-DD)
│ topic           VARCHAR(50)  NULLABLE  │
│ anomaly_type    VARCHAR(20)            │  ('spike' | 'drop')
│ magnitude       DECIMAL(5,2)           │  (% change)
│ reason          TEXT                   │
│ analysis        TEXT                   │  (LLM-generated)
│ recommendation  TEXT                   │  (LLM-generated)
│ review_ids      ARRAY(UUID)            │
│ created_at      TIMESTAMP              │
├────────────────────────────────────────┤
│ Index: ix_anomaly_insights_lookup      │
│        (place_id, date, topic)         │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│           activity_logs               │
├────────────────────────────────────────┤
│ id              UUID        PK         │
│ timestamp       TIMESTAMP   INDEX      │
│ level           VARCHAR(20)            │  (info|warning|error|success)
│ category        VARCHAR(50) INDEX      │  (job|analysis|email|scraper|worker|system)
│ action          VARCHAR(100)           │
│ message         TEXT                   │
│ details         JSONB                  │
│ job_id          UUID        FK NULLABLE│
│ scrape_job_id   UUID        FK NULLABLE│
│ place_id        UUID        FK NULLABLE│
└────────────────────────────────────────┘
```

---

## 6. Authentication Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           JWT AUTHENTICATION FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                              REGISTRATION                                        │
    │                                                                                  │
    │   POST /api/auth/register                                                        │
    │   ┌─────────────────────────────┐      ┌─────────────────────────────────────┐ │
    │   │ {                           │      │ 1. Validate email uniqueness         │ │
    │   │   "email": "user@email.com",│ ───▶ │ 2. Hash password (bcrypt)           │ │
    │   │   "password": "secret",     │      │ 3. Create user record               │ │
    │   │   "name": "Ahmed"           │      │ 4. Generate JWT token               │ │
    │   │ }                           │      │ 5. Return token + user              │ │
    │   └─────────────────────────────┘      └─────────────────────────────────────┘ │
    └─────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                                  LOGIN                                           │
    │                                                                                  │
    │   POST /api/auth/login                                                           │
    │   ┌─────────────────────────────┐      ┌─────────────────────────────────────┐ │
    │   │ {                           │      │ 1. Find user by email               │ │
    │   │   "email": "user@email.com",│ ───▶ │ 2. Verify password (bcrypt)         │ │
    │   │   "password": "secret"      │      │ 3. Generate JWT token               │ │
    │   │ }                           │      │ 4. Return token + user              │ │
    │   └─────────────────────────────┘      └─────────────────────────────────────┘ │
    └─────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                            JWT TOKEN STRUCTURE                                   │
    │                                                                                  │
    │   ┌─────────────────────────────────────────────────────────────────────────┐  │
    │   │  Header: { alg: "HS256", typ: "JWT" }                                   │  │
    │   │  Payload: {                                                              │  │
    │   │    "user_id": "uuid-string",                                            │  │
    │   │    "email": "user@email.com",                                           │  │
    │   │    "exp": <timestamp + 7 days>                                          │  │
    │   │  }                                                                       │  │
    │   │  Signature: HMAC-SHA256(header + payload, JWT_SECRET)                   │  │
    │   └─────────────────────────────────────────────────────────────────────────┘  │
    │                                                                                  │
    │   Configuration:                                                                 │
    │   • Algorithm: HS256                                                            │
    │   • Expiration: 7 days                                                          │
    │   • Secret: JWT_SECRET env var                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                         PROTECTED ENDPOINT ACCESS                                │
    │                                                                                  │
    │   Request:                                                                       │
    │   ┌─────────────────────────────────────────────────────────────────────────┐  │
    │   │  GET /api/overview                                                       │  │
    │   │  Authorization: Bearer <jwt_token>                                       │  │
    │   └─────────────────────────────────────────────────────────────────────────┘  │
    │                                        │                                         │
    │                                        ▼                                         │
    │   ┌─────────────────────────────────────────────────────────────────────────┐  │
    │   │  get_current_user() Dependency                                           │  │
    │   │  1. Extract token from Authorization header                              │  │
    │   │  2. Decode and validate JWT                                              │  │
    │   │  3. Check expiration                                                     │  │
    │   │  4. Load user from database                                              │  │
    │   │  5. Verify user is active                                                │  │
    │   │  6. Return User object to endpoint                                       │  │
    │   └─────────────────────────────────────────────────────────────────────────┘  │
    │                                                                                  │
    │   Protected Endpoints (require auth):                                           │
    │   • POST /api/scrape                                                            │
    │   • GET  /api/jobs                                                              │
    │   • GET  /api/overview                                                          │
    │   • GET  /api/sentiment-trend                                                   │
    │   • GET  /api/sentiment-trend/{date}/reviews                                    │
    └─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Message Queue Architecture

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

## 8. LLM Integration Architecture

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
                                            │ (OpenAI-compatible API)
                                            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                          GEMINI API (Google Cloud)                            │
    │                                                                                │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  Model: gemini-2.0-flash                                                ││
    │   │  Endpoint: https://generativelanguage.googleapis.com/v1beta/openai/     ││
    │   │  Parameters:                                                             ││
    │   │    ├── temperature: 0.1 (deterministic)                                 ││
    │   │    └── max_tokens: 1000                                                 ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    │                                                                                │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  SYSTEM PROMPT                                                           ││
    │   │                                                                          ││
    │   │  You are a review analysis assistant for Saudi businesses.               ││
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
    │   │  ├── Negative sentiment + score > 0.7 (high confidence negative)        ││
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
    │                          ANOMALY INSIGHT GENERATION                           │
    │                                                                                │
    │   When anomalies detected (2σ deviation in sentiment):                        │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  generate_anomaly_insight() → LLM analyzes:                              ││
    │   │  • Date and anomaly type (spike/drop)                                    ││
    │   │  • Topic changes vs baseline                                             ││
    │   │  • Review summaries from period                                          ││
    │   │                                                                          ││
    │   │  Output:                                                                 ││
    │   │  {                                                                       ││
    │   │    "analysis": "Detailed explanation of anomaly cause",                  ││
    │   │    "recommendation": "Specific actionable step"                          ││
    │   │  }                                                                       ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Anomaly Detection System

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          ANOMALY DETECTION (2σ Statistical)                          │
└─────────────────────────────────────────────────────────────────────────────────────┘

    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                         SENTIMENT TREND CALCULATION                            │
    │                                                                                │
    │   GET /api/sentiment-trend?period=30d&zoom=day                                │
    │                                                                                │
    │   1. Aggregate reviews by time bucket (day/week/month/year)                   │
    │   2. Calculate positive percentage per bucket                                  │
    │   3. Compute mean and standard deviation                                       │
    │                                                                                │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  Date       | Reviews | Positive | Pct  | Z-Score | Anomaly?            ││
    │   │  -----------|---------|----------|------|---------|------------------   ││
    │   │  2025-01-01 |    15   |    12    | 80%  |   0.5   | No                  ││
    │   │  2025-01-02 |    18   |    14    | 78%  |   0.3   | No                  ││
    │   │  2025-01-03 |    22   |     8    | 36%  |  -2.4   | YES (drop)          ││
    │   │  2025-01-04 |    12   |    11    | 92%  |   2.1   | YES (spike)         ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────────────────────────────────────────────┘

    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                           ANOMALY PROCESSING                                   │
    │                                                                                │
    │   When |z-score| > 2:                                                         │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  1. Mark point as anomaly (spike if z > 2, drop if z < -2)              ││
    │   │  2. Calculate magnitude (% difference from mean)                         ││
    │   │  3. Analyze topic distribution for that period                           ││
    │   │  4. Generate statistical reason                                          ││
    │   │  5. Check for cached LLM insight in anomaly_insights table               ││
    │   │  6. If not cached, queue for background LLM analysis                     ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    │                                                                                │
    │   Response:                                                                    │
    │   {                                                                            │
    │     "data": [...sentiment trend points...],                                    │
    │     "anomalies": [                                                             │
    │       {                                                                        │
    │         "date": "2025-01-03",                                                  │
    │         "type": "drop",                                                        │
    │         "magnitude": -39.0,                                                    │
    │         "reason": "Sentiment dropped 39% - 'service' complaints: 8",          │
    │         "llm_insight": {                                                       │
    │           "analysis": "Multiple customers reported long wait times...",       │
    │           "recommendation": "Add staff during lunch rush hours"               │
    │         }                                                                      │
    │       }                                                                        │
    │     ],                                                                         │
    │     "baseline": { "avg_positive_pct": 75, "avg_daily_reviews": 16 }           │
    │   }                                                                            │
    └───────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Real-Time WebSocket Updates

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            WEBSOCKET ARCHITECTURE                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘

    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                        CONNECTION MANAGEMENT                                   │
    │                                                                                │
    │   WS /ws                                                                       │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  ConnectionManager:                                                      ││
    │   │  • active_connections: Set[WebSocket]                                    ││
    │   │  • last_analysis_id: tracks latest analysis                              ││
    │   │  • last_log_id: tracks latest activity log                               ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────────────────────────────────────────────┘

    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                         BACKGROUND POLLING (2s)                                │
    │                                                                                │
    │   poll_database() task:                                                        │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  Every 2 seconds:                                                        ││
    │   │  1. Check for new ReviewAnalysis records                                 ││
    │   │  2. Broadcast analysis update if new                                     ││
    │   │  3. Broadcast stats update (counts, active jobs)                         ││
    │   │  4. Check for new ActivityLog records                                    ││
    │   │  5. Broadcast activity log updates if new                                ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────────────────────────────────────────────┘

    ┌───────────────────────────────────────────────────────────────────────────────┐
    │                          MESSAGE TYPES                                         │
    │                                                                                │
    │   Analysis Update:                                                             │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  {                                                                       ││
    │   │    "type": "analysis",                                                   ││
    │   │    "data": {                                                             ││
    │   │      "review_id": "uuid",                                                ││
    │   │      "place_name": "Cafe Name",                                          ││
    │   │      "sentiment": "positive",                                            ││
    │   │      "score": 0.85,                                                      ││
    │   │      "summary_en": "Customer loved the coffee",                          ││
    │   │      "analyzed_at": "2025-01-15T10:30:00Z"                               ││
    │   │    }                                                                     ││
    │   │  }                                                                       ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    │                                                                                │
    │   Stats Update:                                                                │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  {                                                                       ││
    │   │    "type": "stats",                                                      ││
    │   │    "data": {                                                             ││
    │   │      "places_count": 45,                                                 ││
    │   │      "reviews_count": 1250,                                              ││
    │   │      "analyses_count": 1100,                                             ││
    │   │      "pending_analyses": 150,                                            ││
    │   │      "scrape_jobs": { "processing": 2, "completed": 10 },                ││
    │   │      "active_jobs": [...]                                                ││
    │   │    }                                                                     ││
    │   │  }                                                                       ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    │                                                                                │
    │   Activity Logs:                                                               │
    │   ┌─────────────────────────────────────────────────────────────────────────┐│
    │   │  {                                                                       ││
    │   │    "type": "logs",                                                       ││
    │   │    "data": [                                                             ││
    │   │      {                                                                   ││
    │   │        "id": "uuid",                                                     ││
    │   │        "timestamp": "2025-01-15T10:30:00Z",                              ││
    │   │        "level": "success",                                               ││
    │   │        "category": "analysis",                                           ││
    │   │        "action": "review_analyzed",                                      ││
    │   │        "message": "Review analyzed: Cafe Name (positive, 0.85)"          ││
    │   │      }                                                                   ││
    │   │    ]                                                                     ││
    │   │  }                                                                       ││
    │   └─────────────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION DEPLOYMENT                                        │
│                         Docker Compose Stack                                        │
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
    │   │   │                                                               │   │  │
    │   │   │   ┌─────────────────┐                                        │   │  │
    │   │   │   │    pgadmin      │                                        │   │  │
    │   │   │   │     :5050       │  (Database admin UI)                   │   │  │
    │   │   │   └─────────────────┘                                        │   │  │
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
    │   │   │   │   │  • WebSocket /ws                             │  │   │   │  │
    │   │   │   │   │  • JWT authentication                        │  │   │   │  │
    │   │   │   │   │  • Background orchestration                  │  │   │   │  │
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
    │   │   │   │   │ • Log        │      │ • Log        │            │   │   │  │
    │   │   │   │   └──────────────┘      └──────────────┘            │   │   │  │
    │   │   │   │                                                      │   │   │  │
    │   │   │   │   Depends on: postgres, rabbitmq, api                │   │   │  │
    │   │   │   │   Scale: docker-compose up --scale worker=N          │   │   │  │
    │   │   │   └─────────────────────────────────────────────────────┘   │   │  │
    │   │   │                                                               │   │  │
    │   │   │   ┌─────────────────────────────────────────────────────┐   │   │  │
    │   │   │   │                   FRONTENDS                          │   │   │  │
    │   │   │   │                                                      │   │   │  │
    │   │   │   │   ┌──────────────┐      ┌──────────────┐            │   │   │  │
    │   │   │   │   │  dashboard   │      │client-portal │            │   │   │  │
    │   │   │   │   │   :3000      │      │   :3002      │            │   │   │  │
    │   │   │   │   │              │      │              │            │   │   │  │
    │   │   │   │   │ • Next.js    │      │ • Next.js    │            │   │   │  │
    │   │   │   │   │ • Admin UI   │      │ • User UI    │            │   │   │  │
    │   │   │   │   │ • WebSocket  │      │ • Auth       │            │   │   │  │
    │   │   │   │   │ • Real-time  │      │ • Analytics  │            │   │   │  │
    │   │   │   │   └──────────────┘      └──────────────┘            │   │   │  │
    │   │   │   └─────────────────────────────────────────────────────┘   │   │  │
    │   │   │                                                               │   │  │
    │   │   │   ┌─────────────────────────────────────────────────────┐   │   │  │
    │   │   │   │                    Volumes                            │   │   │  │
    │   │   │   │                                                      │   │   │  │
    │   │   │   │   postgres_data    ← Database persistence            │   │   │  │
    │   │   │   │   rabbitmq_data    ← Queue persistence               │   │   │  │
    │   │   │   │   scraper_data     ← Scraper data                    │   │   │  │
    │   │   │   │   results_data     ← CSV downloads                   │   │   │  │
    │   │   │   │   pgadmin_data     ← pgAdmin config                  │   │   │  │
    │   │   │   └─────────────────────────────────────────────────────┘   │   │  │
    │   │   └──────────────────────────────────────────────────────────────┘   │  │
    │   └──────────────────────────────────────────────────────────────────────┘  │
    │                                        │                                     │
    │                                        │ HTTPS API calls                     │
    │                                        ▼                                     │
    │   ┌──────────────────────────────────────────────────────────────────────┐  │
    │   │                         GEMINI API                                    │  │
    │   │                      (Google Cloud)                                   │  │
    │   │                                                                       │  │
    │   │   Endpoint: https://generativelanguage.googleapis.com/v1beta/openai/ │  │
    │   │   Model: gemini-2.0-flash                                            │  │
    │   │   Auth: VLLM_API_KEY (Gemini API key)                                │  │
    │   └──────────────────────────────────────────────────────────────────────┘  │
    │                                                                              │
    └──────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Environment Variables

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           CONFIGURATION (config.py)                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────┬────────────────────────────────────────────────┐
│           VARIABLE                 │              DESCRIPTION                        │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  DATABASE_URL                      │  PostgreSQL connection string                   │
│  RABBITMQ_URL                      │  RabbitMQ connection string                     │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  VLLM_BASE_URL                     │  LLM API endpoint (OpenAI-compatible)          │
│                                    │  Default: Google Generative AI endpoint        │
│  VLLM_API_KEY                      │  Gemini API key                                 │
│  VLLM_MODEL                        │  Model name (default: gemini-2.0-flash)        │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  JWT_SECRET                        │  Secret for JWT token signing                   │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  SMTP_HOST                         │  Email server host (default: smtp.gmail.com)   │
│  SMTP_PORT                         │  Email server port (default: 587)              │
│  SMTP_USER                         │  Email username                                 │
│  SMTP_PASSWORD                     │  Email password/app password                    │
│  SMTP_FROM_EMAIL                   │  Sender email address                          │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  SCRAPER_API_URL                   │  Go scraper endpoint                            │
│  RESULTS_DIR                       │  Directory for CSV downloads                    │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  GCP_PROJECT_ID                    │  GCP project for Secret Manager (optional)     │
│  USE_SECRET_MANAGER                │  Enable GCP Secret Manager (default: false)    │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  QUEUE_NAME                        │  RabbitMQ queue (default: review_analysis)     │
│  DLQ_NAME                          │  Dead letter queue name                         │
│  PREFETCH_COUNT                    │  Worker prefetch count (default: 1)            │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  DASHBOARD_API_URL                 │  API URL for dashboard                          │
│  DASHBOARD_WS_URL                  │  WebSocket URL for dashboard                    │
│  CLIENT_PORTAL_API_URL             │  API URL for client portal                      │
└────────────────────────────────────┴────────────────────────────────────────────────┘

Secret Loading Priority:
1. GCP Secret Manager (if USE_SECRET_MANAGER=true and GCP_PROJECT_ID set)
2. Environment variables
3. Default values
```

---

## 13. Performance Characteristics

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           PERFORMANCE CHARACTERISTICS                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────┬────────────────────────────────────────────────┐
│           COMPONENT                │              THROUGHPUT                         │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  Google Maps Scraper               │  ~120 places/minute                            │
│  Extended Reviews                  │  Up to 300+ reviews/place                      │
│  LLM Analysis (Gemini)             │  ~30-60 reviews/minute per worker              │
│  Email Generation                  │  ~10 reports/minute                            │
│  RabbitMQ                          │  ~10,000 messages/second (theoretical)         │
│  PostgreSQL                        │  ~5,000 inserts/second                         │
│  WebSocket Broadcast               │  2-second polling interval                     │
└────────────────────────────────────┴────────────────────────────────────────────────┘

┌────────────────────────────────────┬────────────────────────────────────────────────┐
│           SCALING                  │              STRATEGY                           │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  Workers                           │  Horizontal: 2 → N replicas                    │
│                                    │  Command: docker-compose up --scale worker=N   │
│  Database                          │  Connection pooling (SQLAlchemy)               │
│  LLM (Gemini)                      │  Cloud API - scales automatically              │
│  Scraper                           │  Rate-limited by Google (single instance)      │
│  Frontends                         │  Static Next.js builds, CDN-ready              │
└────────────────────────────────────┴────────────────────────────────────────────────┘

┌────────────────────────────────────┬────────────────────────────────────────────────┐
│           ERROR HANDLING           │              MECHANISM                          │
├────────────────────────────────────┼────────────────────────────────────────────────┤
│  Scraper Failures                  │  Status tracked, error_message stored          │
│  LLM API Errors                    │  Retry with backoff, then DLQ                  │
│  LLM Parse Errors                  │  JSON extraction fallback, then DLQ            │
│  Database Failures                 │  Transaction rollback, activity logged         │
│  Message Processing                │  3 retries → Dead Letter Queue                 │
│  Worker Crashes                    │  Docker restart policy: unless-stopped         │
│  Duplicate Emails                  │  PostgreSQL advisory locks                     │
│  Auth Failures                     │  401 response, logged                          │
└────────────────────────────────────┴────────────────────────────────────────────────┘
```

---

## 14. File Structure

```
/home/user/nurliya/
│
├── .env                              # Local development credentials
├── .env.example                      # Template for environment variables
├── docker-compose.yml                # Service orchestration
├── Makefile                          # Common operations
├── ARCHITECTURE.md                   # This document
├── DEPLOYMENT.md                     # Production deployment guide
├── GCP_DEPLOYMENT_INSTRUCTIONS.md    # GCP-specific setup
├── nurliya-prd.md                    # Product requirements document
│
├── pipline/                          # Python backend application
│   ├── Dockerfile                    # Container definition
│   ├── requirements.txt              # Python dependencies
│   │
│   ├── api.py                        # FastAPI REST server + WebSocket
│   ├── orchestrator.py               # Pipeline orchestration
│   ├── worker.py                     # Queue consumer
│   │
│   ├── auth.py                       # JWT authentication
│   ├── scraper_client.py             # Go scraper HTTP client
│   ├── csv_parser.py                 # CSV parsing & normalization
│   ├── producer.py                   # CLI CSV processor
│   │
│   ├── llm_client.py                 # LLM interface (OpenAI-compatible)
│   ├── gemini_client.py              # Gemini-specific client (legacy)
│   ├── email_service.py              # Report generation & SMTP
│   │
│   ├── database.py                   # SQLAlchemy models (7 tables)
│   ├── rabbitmq.py                   # Queue setup
│   ├── config.py                     # Configuration with GCP Secret Manager
│   │
│   ├── activity_logger.py            # Database activity logging
│   ├── logging_config.py             # Structured logging setup
│   │
│   └── templates/
│       └── email_report.html         # Jinja2 email template
│
├── client-portal/                    # Next.js client application
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── app/                      # App router pages
│       │   ├── page.tsx              # Dashboard/overview
│       │   ├── login/page.tsx        # Login page
│       │   └── register/page.tsx     # Registration page
│       ├── components/
│       │   ├── ui/                   # Reusable UI components
│       │   └── AuthGuard.tsx         # Protected route wrapper
│       └── lib/
│           ├── api.ts                # API client
│           └── auth.tsx              # Auth context
│
├── dashboard/                        # Next.js admin dashboard
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       └── app/
│           └── page.tsx              # Real-time monitoring dashboard
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

## 15. Quick Start Commands

```bash
# Development
docker-compose up -d --build          # Start all services
docker-compose logs -f                # Stream all logs
curl localhost:8000/health            # Check API health

# Scaling
docker-compose up -d --scale worker=4 # Scale worker replicas

# Testing
curl -X POST localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123","name":"Test"}'

# Debugging
docker-compose logs -f api            # API logs only
docker-compose logs -f worker         # Worker logs only
docker exec -it nurliya-postgres psql -U nurliya  # DB shell

# Production
docker-compose -f docker-compose.yml up -d  # Production stack
```

---

*Document generated for Nurliya v2.0*
*Last updated: February 2026*
