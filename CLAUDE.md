# Nurliya

AI-powered review intelligence platform for Saudi businesses. Scrapes Google Maps reviews, runs LLM sentiment analysis, discovers product/service taxonomies via clustering, and provides analytics dashboards.

## Architecture

```
Google Maps → Go Scraper → CSV → FastAPI → RabbitMQ → Worker Pool
                                     ↕
                          PostgreSQL + Qdrant + MinIO
                                     ↕
                    3 Next.js Frontends (Dashboard, Onboarding, Client)
```

### Services (docker-compose)

| Service | Port | Tech |
|---------|------|------|
| api | 8000 | FastAPI + Python 3.11 |
| worker | — | Python (2+ replicas) |
| scraper | 8080 | Go + Playwright |
| dashboard | 3000 | Next.js 14 |
| onboarding-portal | 3001 | Next.js 14 |
| client-portal | 3002 | Next.js 14 |
| postgres | 5432 | PostgreSQL 16 |
| rabbitmq | 5672 | RabbitMQ 3 |
| qdrant | 6333 | Qdrant |
| minio | 9000 | MinIO |
| pgadmin | 5050 | pgAdmin 4 |

## Directory Structure

- `pipline/` — Python backend (note: intentional typo in folder name, do NOT rename)
- `onboarding-portal/` — Taxonomy review UI (Next.js)
- `dashboard/` — Admin monitoring (Next.js)
- `client-portal/` — Client analytics (Next.js)
- `google-maps-scraper/` — Go scraper (forked, mostly read-only)
- `lab/` — Experimental scripts (gitignored)

## Key Backend Files

- `pipline/api.py` — FastAPI endpoints (large file, 2800+ lines)
- `pipline/worker.py` — RabbitMQ consumer, review analysis, mention extraction
- `pipline/clustering_job.py` — HDBSCAN clustering + anchor pre-classification
- `pipline/anchor_manager.py` — Learning system (anchors, corrections, archives)
- `pipline/vector_store.py` — Qdrant client (MENTIONS_COLLECTION, PRODUCTS_COLLECTION)
- `pipline/database.py` — SQLAlchemy models (30+ tables)
- `pipline/embedding_client.py` — Sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2, 384-dim)
- `pipline/llm_client.py` — Gemini 2.0 Flash via OpenAI-compatible API
- `pipline/csv_parser.py` — Google Maps scraper CSV parsing
- `pipline/image_store.py` — MinIO object storage for menu images

## Learning System

The taxonomy discovery uses a "Learn, Discover" architecture:

1. **Anchors** (PostgreSQL JSONB) — 384-dim centroids learned from approved taxonomies
2. **Classification** — Cosine similarity against anchors (threshold: 0.80 learned, 0.70 import, 0.75 archive)
3. **Discovery** — HDBSCAN clustering for unmatched mentions, LLM labels clusters
4. **Corrections** — User bulk-moves update both anchors (2x weight) AND Qdrant vectors
5. **Archives** — Previous approved taxonomies feed back into clustering

Always use `normalize_business_type()` from `anchor_manager.py` — never use raw `place.category` for anchor lookups.

## Common Commands

```bash
make up-build          # Start all services with rebuild
make logs-api          # API logs
make logs-worker       # Worker logs
make restart-api       # Restart API only
make health            # Health check
make scale-workers WORKERS=4  # Scale workers
make init-db           # Initialize database tables
make dev-api           # Run API locally without Docker
```

## Development Patterns

- **Migrations**: SQL files in `pipline/migrations/`, run manually via psql
- **Non-blocking learning**: All anchor_manager functions wrap in try/except, log warnings on failure
- **Session handling**: API endpoints create sessions via `get_session()`. Pass session to functions that modify data. Functions called from clustering (no shared session) create their own `SessionLocal()`
- **Seed/import anchors are never deleted** — only correction/learned ones can be cleaned up
- **Stats are batch-computed**: Product/category stats recomputed from RawMention table at publish time, not incrementally

## Commit Style

```
feat: short description of feature
fix: short description of bug fix
chore: non-functional changes
docs: documentation only
```

Keep commit messages concise (1-2 lines). Use imperative mood.

## Environment

- **Production**: GCP VM (e2-standard-2, europe-west1-b), Cloudflare Tunnel for SSL
- **Secrets**: GCP Secret Manager with .env fallback
- **Branch**: `feature/taxonomy-system` is the active development branch
