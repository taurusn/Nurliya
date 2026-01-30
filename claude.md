# Nurliya - Claude Context File

> **Purpose:** This file serves as an anchor for Claude Code sessions. Read this first to understand the project without re-reading all source files.

---

## Project Overview

**Name:** Nurliya (نورليّة)
**Type:** AI-powered sentiment analysis platform for Saudi businesses
**Target:** Cafes, restaurants, hotels, retail stores in Saudi Arabia
**Status:** Production-ready with FastAPI + Docker Compose

### What It Does
1. Accepts search query via REST API (e.g., "cafes in Riyadh")
2. Scrapes Google Maps reviews via integrated Go scraper
3. Parses results and stores in PostgreSQL
4. Queues reviews for analysis via RabbitMQ
5. Analyzes each review with Llama 3.1 8B (vLLM)
6. Returns structured analysis (sentiment, topics, Arabic replies)

---

## Production Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TENSORDOCK VM (206.168.83.147)                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Cloudflare Tunnel ──▶ :8000                                          │
│         │                                                               │
│         ▼                                                               │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                    DOCKER COMPOSE NETWORK                        │  │
│   │                                                                  │  │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │  │
│   │  │ postgres │  │ rabbitmq │  │ scraper  │  │ api      │        │  │
│   │  │ :5432    │  │ :5672    │  │ :8080    │  │ :8000    │        │  │
│   │  └──────────┘  └──────────┘  └──────────┘  └────┬─────┘        │  │
│   │                                                  │              │  │
│   │                              ┌───────────────────┘              │  │
│   │                              ▼                                  │  │
│   │  ┌──────────────────────────────────────────────────────────┐  │  │
│   │  │                      worker (x2)                          │  │  │
│   │  │  (consumes from RabbitMQ, calls vLLM, saves to Postgres) │  │  │
│   │  └──────────────────────────────────────────────────────────┘  │  │
│   │                              │                                  │  │
│   └──────────────────────────────┼──────────────────────────────────┘  │
│                                  │                                      │
│                                  ▼                                      │
│   ┌──────────────────────────────────────────────────────────────────┐ │
│   │  vLLM Server (on host, outside Docker)                           │ │
│   │  :8080 → Llama 3.1 8B                                            │ │
│   └──────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
nurliya/
├── claude.md                    # THIS FILE - Claude context anchor
├── nurliya-prd.md              # Product Requirements Document
├── docker-compose.yml          # All services orchestration
├── Makefile                    # Common commands (make up, make logs, etc.)
├── .env.production.example     # Production env template
├── results/                    # Scraper output storage
├── pipline/                    # Main Python pipeline
│   ├── Dockerfile             # Container build
│   ├── .env                   # Local dev credentials
│   ├── requirements.txt       # Python dependencies
│   ├── config.py              # Environment config loader
│   ├── database.py            # SQLAlchemy models (5 tables)
│   ├── api.py                 # FastAPI application (NEW)
│   ├── scraper_client.py      # Go scraper HTTP client (NEW)
│   ├── orchestrator.py        # Background task logic (NEW)
│   ├── csv_parser.py          # Parse scraper CSV → DB
│   ├── rabbitmq.py            # RabbitMQ connection + queues
│   ├── llm_client.py          # vLLM/OpenAI client
│   ├── producer.py            # CSV → DB → Queue
│   ├── worker.py              # Queue → LLM → Analysis DB
│   └── gemini_client.py       # DEPRECATED
└── google-maps-scraper/       # Go scraper (runs in web mode)
    ├── Dockerfile             # Scraper container
    ├── main.go                # Entry point
    └── ...                    # See README.md
```

---

## REST API Endpoints

### Scrape & Jobs

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/scrape` | Start scrape job with query |
| GET | `/api/jobs` | List all jobs |
| GET | `/api/jobs/{id}` | Get job status/progress |

### Places & Reviews

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/places` | List all scraped places |
| GET | `/api/places/{id}` | Get place details |
| GET | `/api/places/{id}/reviews` | Get reviews + analysis |
| GET | `/api/places/{id}/stats` | Get sentiment statistics |

### Health

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check for load balancer |

### API Examples

```bash
# Start a scrape
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"query": "coffee shops in Riyadh", "depth": 10}'

# Check job status
curl http://localhost:8000/api/jobs/{job_id}

# Get place reviews with analysis
curl http://localhost:8000/api/places/{place_id}/reviews
```

---

## New Files Reference

### `pipline/api.py` (~300 lines)
FastAPI application with all REST endpoints.

| Line | What |
|------|------|
| 1-20 | Imports and FastAPI setup |
| 22-80 | Pydantic request/response models |
| 82-95 | Startup event (creates tables) |
| 97-110 | Health check endpoint |
| 112-140 | POST /api/scrape (starts background task) |
| 142-180 | GET /api/jobs endpoints |
| 182-250 | GET /api/places endpoints |
| 252-300 | GET /api/places/{id}/stats |

### `pipline/scraper_client.py` (~140 lines)
HTTP client for the Go scraper's Web API.

| Function | Purpose |
|----------|---------|
| `create_job()` | Create scrape job via API |
| `get_job_status()` | Poll job status |
| `download_csv()` | Download results CSV |
| `wait_for_completion()` | Poll until done |
| `health_check()` | Check scraper availability |

### `pipline/orchestrator.py` (~200 lines)
Background task orchestration.

| Function | Purpose |
|----------|---------|
| `run_scrape_pipeline()` | Full scrape→analyze flow |
| `run_producer_async()` | Async wrapper for producer |
| `create_scrape_job()` | Create ScrapeJob record |
| `get_scrape_job_progress()` | Get detailed progress |

---

## Database Schema

### Tables (5 total)

#### `places`, `jobs`, `reviews`, `review_analysis`
(Same as before - see original schema)

#### `scrape_jobs` (NEW)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| query | VARCHAR(500) | Search query |
| status | VARCHAR(50) | pending/scraping/processing/completed/failed |
| scraper_job_id | VARCHAR(100) | ID from Go scraper |
| pipeline_job_ids | UUID[] | Array of Job IDs |
| places_found | INT | Count of places |
| reviews_total | INT | Total reviews queued |
| reviews_processed | INT | Analyzed count |
| error_message | TEXT | Error if failed |
| created_at | TIMESTAMP | |
| completed_at | TIMESTAMP | |

---

## Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| postgres | postgres:16 | 5432 | Database |
| rabbitmq | rabbitmq:3-management | 5672, 15672 | Message queue |
| scraper | ./google-maps-scraper | 8080 | Go scraper (web mode) |
| api | ./pipline | 8000 | FastAPI application |
| worker | ./pipline | - | Review analysis (2 replicas) |

---

## Production Deployment

### Quick Start
```bash
# 1. Configure secrets
cp .env.production.example .env.production
nano .env.production

# 2. Start everything
make up-build

# 3. Check logs
make logs

# 4. Initialize database
make init-db

# 5. Test
make test-scrape
```

### Makefile Commands
```bash
make up              # Start all services
make up-build        # Start with fresh build
make down            # Stop all services
make logs            # View all logs
make logs-api        # View API logs
make logs-worker     # View worker logs
make restart         # Restart all
make scale-workers WORKERS=4  # Scale workers
make health          # Check API health
make init-db         # Create tables
make test-scrape     # Test scrape endpoint
```

### Environment Variables
```env
DB_PASSWORD=<strong-password>
RABBITMQ_PASSWORD=<strong-password>
VLLM_BASE_URL=http://host.docker.internal:8080/v1
VLLM_API_KEY=token-sadnxai
```

---

## vLLM Server

**Location:** Running on host (outside Docker)
- **Port:** 8080
- **Model:** meta-llama/Llama-3.1-8B-Instruct
- **GPU:** RTX 4090 (24GB VRAM)

```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 --port 8080 \
  --enable-auto-tool-choice \
  --tool-call-parser llama3_json \
  --max-model-len 32000 \
  --gpu-memory-utilization 0.9 \
  --api-key token-sadnxai
```

---

## Data Flow

```
User Request: POST /api/scrape {"query": "cafes in Riyadh"}
        │
        ▼
┌─────────────────┐
│ api.py          │ Creates ScrapeJob, starts background task
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ orchestrator.py │ Calls scraper API, polls until complete
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ scraper_client  │ Downloads CSV from Go scraper
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ csv_parser.py   │ Parses CSV, saves Place + Reviews to DB
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ producer.py     │ Creates Jobs, queues review_ids to RabbitMQ
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ RabbitMQ Queue  │ review_analysis queue (durable)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ worker.py       │ Consumes messages, calls vLLM
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ llm_client.py   │ Sends to Llama 3.1 8B, parses JSON response
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PostgreSQL      │ Saves ReviewAnalysis with sentiment, topics, reply
└─────────────────┘
```

---

## Current Status

### Completed
- [x] Core pipeline (CSV → DB → Queue → LLM → Analysis)
- [x] FastAPI REST API with all endpoints
- [x] Scraper integration (Web API mode)
- [x] Background task orchestration
- [x] Docker Compose for all services
- [x] Production configuration (Makefile, env templates)
- [x] Worker scaling (multiple replicas)

### Ready for Production
- Deploy to Tensordock VM
- Configure Cloudflare tunnel
- Set strong passwords in .env.production

---

## Key Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| `api.py` | ~300 | FastAPI REST application |
| `orchestrator.py` | ~200 | Background task logic |
| `scraper_client.py` | ~140 | Scraper HTTP client |
| `worker.py` | ~175 | RabbitMQ consumer |
| `producer.py` | ~100 | CSV processor |
| `llm_client.py` | ~120 | vLLM API wrapper |
| `database.py` | ~115 | SQLAlchemy models |
| `docker-compose.yml` | ~90 | Service orchestration |

---

*Last updated: 2026-01-30*
