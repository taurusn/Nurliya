# Nurliya

AI-powered review intelligence platform for Saudi Arabian businesses. Scrapes Google Maps reviews at scale, discovers product taxonomies via clustering, and runs dialect-aware sentiment analysis — all in Arabic.

## What It Does

1. **Scrapes** Google Maps reviews (120+ places/min, up to 300 reviews per place)
2. **Extracts** product and aspect mentions from review text using LLM
3. **Clusters** mentions via HDBSCAN to discover product taxonomies automatically
4. **Analyzes** sentiment per product/category with Saudi dialect awareness
5. **Generates** professional Arabic replies in Saudi dialect
6. **Detects** anomalies by comparing daily sentiment against 7-day baselines
7. **Delivers** HTML email reports with actionable insights

## Architecture

```
                         Cloudflare Tunnel (SSL)
                                  |
         ┌────────────────────────┼────────────────────────┐
         |                        |                        |
   Client Portal          API (FastAPI)             Dashboard
   Next.js :3002            :8000                  Next.js :3000
         |                    |   |                        |
         |        ┌───────────┘   └───────────┐            |
         |        |                           |            |
   Onboarding   Go Scraper              Worker Pool (x3)
   Next.js :3001  :8080                       |
                                    ┌─────────┼─────────┐
                                    |         |         |
                                 Gemini   Embeddings  HDBSCAN
                                 2.0 Flash  MiniLM    Clustering
                                              |
         ┌──────────┬──────────┬──────────┬───┴───┬──────────┐
      PostgreSQL  RabbitMQ    Redis     Qdrant   MinIO    pgAdmin
        :5432      :5672      :6379    :6333     :9000     :5050
```

## Two-Phase Pipeline

**Phase 1 — Extract & Discover (new places):**
- LLM extracts product/aspect mentions from each review
- Mentions are embedded (MiniLM 384-dim) and deduplicated via Qdrant (0.85 threshold)
- HDBSCAN clusters mentions into product groups
- LLM labels clusters with human-readable names (Arabic + English)
- Draft taxonomy is presented in the Onboarding Portal for human review

**Phase 2 — Sentiment Analysis (after taxonomy approval):**
- Reviews are re-analyzed with approved taxonomy as context
- LLM matches mentions to known products, classifies sentiment per aspect
- Generates bilingual summaries and Saudi-dialect replies
- Updates per-product/category statistics incrementally

## ML/NLP Stack

| Component | Method |
|-----------|--------|
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (384-dim) |
| Vector DB | Qdrant — entity resolution, mention deduplication |
| Clustering | HDBSCAN (density-based, min_cluster_size=3) |
| Hierarchy | Centroid similarity grouping (threshold=0.70) |
| Variant Grouping | DBSCAN sub-clustering + LLM cross-lingual merge |
| Sentiment | Gemini 2.0 Flash with structured JSON output |
| Arabic Normalization | Custom pipeline: diacritics, tatweel, alef/yeh/kaf variant mapping |
| Anomaly Detection | 7-day rolling baseline comparison + LLM-generated insights |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI, SQLAlchemy 2.0, JWT auth |
| Workers | RabbitMQ consumers (3 replicas), async processing |
| LLM | Gemini 2.0 Flash (OpenAI-compatible API) |
| Embeddings | sentence-transformers (MiniLM) |
| Clustering | HDBSCAN, scikit-learn |
| Vector DB | Qdrant |
| Database | PostgreSQL 16 (12 tables) |
| Cache | Redis 7 |
| Object Storage | MinIO (menu images) |
| Scraper | Go + Chromium headless |
| Frontends | 3x Next.js apps (client portal, dashboard, onboarding) |
| Deployment | Docker Compose, Cloudflare Tunnel |

## Database Schema

**Core:** `users`, `places`, `reviews`, `jobs`, `scrape_jobs`, `review_analysis`, `activity_logs`, `anomaly_insights`

**Taxonomy:** `place_taxonomies`, `taxonomy_categories`, `taxonomy_products`, `raw_mentions`

## Quick Start

```bash
# 1. Configure
cp .env.production.example .env.production
# Fill in: DB_PASSWORD, RABBITMQ_PASSWORD, VLLM_API_KEY, SMTP credentials, JWT_SECRET

# 2. Start
make up-build

# 3. Initialize database
make init-db

# 4. Test
make health
make test-scrape
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| api | 8000 | FastAPI REST + WebSocket |
| worker | — | Review analysis (3 replicas) |
| scraper | 8080 | Google Maps Go scraper |
| client-portal | 3002 | User-facing app |
| dashboard | 3000 | Admin monitoring |
| onboarding-portal | 3001 | Taxonomy review UI |
| postgres | 5432 | Database |
| rabbitmq | 5672 | Message queue |
| qdrant | 6333 | Vector store |
| redis | 6379 | Cache + locks |
| minio | 9000 | Object storage |
| pgadmin | 5050 | DB admin |

## Makefile

```bash
make up              # Start all services
make up-build        # Build and start
make down            # Stop all
make logs            # Tail all logs
make logs-api        # Tail API logs
make logs-worker     # Tail worker logs
make scale-workers WORKERS=5  # Scale worker pool
make health          # API health check
make init-db         # Create tables
make test-scrape     # Test scrape endpoint
make ps              # Show running containers
make stats           # Container resource usage
```

## Project Structure

```
nurliya/
├── pipline/                    # Python backend
│   ├── api.py                  # FastAPI REST + WebSocket endpoints
│   ├── worker.py               # RabbitMQ consumer, LLM orchestration
│   ├── llm_client.py           # Gemini API integration
│   ├── embedding_client.py     # MiniLM embeddings + Arabic normalization
│   ├── vector_store.py         # Qdrant wrapper, entity resolution
│   ├── clustering_job.py       # HDBSCAN taxonomy discovery
│   ├── mention_grouping.py     # Variant detection + cross-lingual merge
│   ├── insights.py             # Anomaly detection + LLM analysis
│   ├── database.py             # SQLAlchemy models (12 tables)
│   ├── orchestrator.py         # Scrape pipeline coordination
│   ├── email_service.py        # HTML report generation
│   ├── auth.py                 # JWT authentication
│   └── ...
├── client-portal/              # Next.js — user-facing app
├── dashboard/                  # Next.js — admin monitoring
├── onboarding-portal/          # Next.js — taxonomy review UI
├── google-maps-scraper/        # Go scraper (Chromium headless)
├── docker-compose.yml
├── Makefile
└── docs/
    ├── ARCHITECTURE.md         # Detailed system architecture (1,800+ lines)
    └── DEPLOYMENT.md           # Production deployment guide
```

## Arabic NLP Challenges

The platform handles Saudi Arabic review text which presents unique challenges:

- **Dialect mixing** — Najdi, Hijazi, and MSA in the same review
- **Arabizi** — Latin transliteration ("laatiih" = "لاتيه" = latte)
- **Cross-lingual products** — Same item referenced in Arabic and English
- **Morphological variance** — Diacritics, tatweel, alef/yeh/kaf character variants

The embedding model (MiniLM) achieves 0.78-0.96 similarity for same-language variants but only 0.29-0.73 for cross-lingual pairs. The platform compensates with LLM-based cross-lingual merging and a human-in-the-loop taxonomy approval step.
