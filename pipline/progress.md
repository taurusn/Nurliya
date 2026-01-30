# Nurliya Pipeline - Progress Log

---

## 2025-01-30

### Task 1.1: Create requirements.txt
**Status:** Complete
**File:** `requirements.txt`
**What:** Created Python dependencies file
**How:** Listed all required packages:
- python-dotenv (env loading)
- sqlalchemy (ORM)
- psycopg2-binary (PostgreSQL driver)
- google-generativeai (Gemini API)
- pandas (CSV parsing)
- pika (RabbitMQ client)

---

### Task 1.2: Create .env
**Status:** Complete
**File:** `.env`
**What:** Created environment credentials file
**How:** Added three config values:
- DATABASE_URL for PostgreSQL connection
- GEMINI_API_KEY for Gemini API
- RABBITMQ_URL for message queue

---

### Task 1.3: Create config.py
**Status:** Complete
**File:** `config.py`
**What:** Created configuration loader
**How:**
- Uses python-dotenv to load .env
- Exports DATABASE_URL, GEMINI_API_KEY, RABBITMQ_URL
- Defines queue names and Gemini model settings

---

### Task 1.4: Create database.py
**Status:** Complete
**File:** `database.py`
**What:** Created SQLAlchemy models for all 4 tables
**How:**
- `Place` - stores business info (name, address, rating, etc.)
- `Job` - tracks processing status and progress
- `Review` - stores raw reviews from scraper
- `ReviewAnalysis` - stores LLM analysis output
- Added relationships between tables
- Created `get_session()` helper and `create_tables()` function

---

### Task 1.5: Start PostgreSQL
**Status:** Complete
**What:** Started PostgreSQL 16 in Docker
**How:**
```bash
docker run --name nurliya-db \
  -e POSTGRES_USER=nurliya \
  -e POSTGRES_PASSWORD=nurliya123 \
  -e POSTGRES_DB=nurliya \
  -p 5432:5432 \
  -d postgres:16
```

---

### Task 1.6: Start RabbitMQ
**Status:** Complete
**What:** Started RabbitMQ with management UI in Docker
**How:**
```bash
docker run --name nurliya-rabbitmq \
  -e RABBITMQ_DEFAULT_USER=nurliya \
  -e RABBITMQ_DEFAULT_PASS=nurliya123 \
  -p 5672:5672 \
  -p 15672:15672 \
  -d rabbitmq:3-management
```
**Note:** Management UI at http://localhost:15672

---

### Task 1.7: Create database tables
**Status:** Complete
**What:** Created all 4 tables in PostgreSQL
**How:** Ran `python database.py` which calls `Base.metadata.create_all(engine)`

---

### Task 2.1: Create csv_parser.py
**Status:** Complete
**File:** `csv_parser.py`
**What:** Created CSV parser for scraper output
**How:**
- `parse_json_field()` - safely parses JSON fields from CSV
- `parse_csv()` - reads CSV, extracts place metadata and reviews
- `save_place_and_reviews()` - inserts place and reviews to DB
- Maps scraper fields: Name→author, Description→text, When→review_date
- Handles JSON fields: reviews_per_rating, open_hours, user_reviews

**Test Result:** Parsed 1 place (Slope Roastery) with 8 reviews

---

### Task 2.2: Test CSV parsing
**Status:** Complete
**What:** Verified parser works with sample data
**How:** Ran `python csv_parser.py` - successfully parsed ../results/results.csv

---

### Task 3.1: Create rabbitmq.py
**Status:** Complete
**File:** `rabbitmq.py`
**What:** Created RabbitMQ connection helper with queue setup
**How:**
- `get_connection()` - creates connection from URL
- `setup_queues()` - declares main queue + dead letter queue
- `publish_message()` - publishes persistent JSON messages
- `get_consumer_channel()` - returns channel with prefetch=1
- `get_producer_channel()` - returns channel for publishing
- Dead letter exchange for failed messages

**Test Result:** Connection successful, queue 'review_analysis' ready

---

### Task 3.2: Test RabbitMQ connection
**Status:** Complete
**What:** Verified RabbitMQ connectivity
**How:** Ran `python rabbitmq.py` - connection and queue setup successful

---

### Task 4.1: Create gemini_client.py
**Status:** Complete (deprecated)
**File:** `gemini_client.py`
**What:** Created Gemini API wrapper with function calling
**Note:** Deprecated due to API quota limits - switched to vLLM

---

### Task 5.1: Create producer.py
**Status:** Complete
**File:** `producer.py`
**What:** Created CSV processor that queues reviews
**How:**
- `create_job()` - creates job record in DB
- `update_job_status()` - updates job status
- `run_producer()` - main flow:
  1. Parse CSV with csv_parser
  2. Save place + reviews to DB
  3. Create job record
  4. Queue each review_id to RabbitMQ
  5. Update job status to "queued"
- CLI: `python producer.py --csv ../results/results.csv`

---

### Task 5.2: Create worker.py
**Status:** Complete
**File:** `worker.py`
**What:** Created RabbitMQ consumer that analyzes reviews
**How:**
- Graceful shutdown handling (SIGINT/SIGTERM)
- `update_job_progress()` - increments processed count
- `save_analysis()` - inserts to review_analysis table
- `process_message()` - main callback
- 2 second delay between requests to avoid rate limits
- CLI: `python worker.py`

---

### Task 5.3: Test producer flow
**Status:** Complete
**What:** Tested CSV → DB → RabbitMQ flow
**How:** Ran `python producer.py --csv ../results/results.csv`
**Result:**
- Parsed 1 place (Slope Roastery)
- Saved 8 reviews to PostgreSQL
- Created job with ID: 469b7238-90ea-4ad5-b4b7-422ddb32d140
- Queued 8 messages to RabbitMQ

---

## 2026-01-30 (vLLM Migration)

### Task 6.1: Set up Tensordock VM
**Status:** Complete
**What:** Created VM with RTX 4090 GPU
**How:** User provisioned via Tensordock dashboard
**Result:** VM at 206.168.83.147 with 24GB VRAM

---

### Task 6.2: Install vLLM
**Status:** Complete
**What:** Installed vLLM and dependencies on server
**How:**
```bash
pip install vllm
huggingface-cli login --token hf_xxx
```

---

### Task 6.3: Start vLLM server
**Status:** Complete
**What:** Started vLLM with Llama 3.1 8B Instruct
**How:**
```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 --port 8080 \
  --enable-auto-tool-choice \
  --tool-call-parser llama3_json \
  --max-model-len 32000 \
  --gpu-memory-utilization 0.9 \
  --api-key token-sadnxai
```
**API:** http://206.168.83.147:8080/v1

---

### Task 6.4: Create llm_client.py
**Status:** Complete
**File:** `llm_client.py`
**What:** Created OpenAI-compatible client for vLLM
**How:**
- Uses `openai` Python package
- Points to vLLM server at 206.168.83.147:8080
- Same system prompt as gemini_client.py
- Returns structured JSON analysis

---

### Task 6.5: Test full pipeline
**Status:** Complete
**What:** Ran worker to process all 8 queued reviews
**How:** `python worker.py`
**Result:**
- All 8 reviews analyzed successfully
- Sentiment detection working (positive/negative/neutral)
- Topic extraction working (food, drinks, service, etc.)
- Language detection working (ar, en, arabizi)
- Arabic summaries generated
- Saudi-dialect replies generated

---

## 2026-01-30 (API & Docker Integration)

### Task 7.1-7.6: API & Scraper Integration
**Status:** Complete
**What:** Created FastAPI REST application with scraper integration

**Files Created:**
- `scraper_client.py` - HTTP client for Go scraper Web API
- `orchestrator.py` - Background task orchestration
- `api.py` - FastAPI application with all endpoints

**Endpoints:**
- `POST /api/scrape` - Start scrape job with query
- `GET /api/jobs/{id}` - Check job progress
- `GET /api/places` - List all places
- `GET /api/places/{id}/reviews` - Get reviews + analysis
- `GET /api/places/{id}/stats` - Sentiment statistics
- `GET /health` - Health check

**Database Changes:**
- Added `ScrapeJob` model for tracking end-to-end jobs

---

### Task 8.1-8.5: Docker & Production
**Status:** Complete
**What:** Containerized all services with Docker Compose

**Files Created:**
- `pipline/Dockerfile` - Python container build
- `docker-compose.yml` - All services orchestration
- `.env.production.example` - Production env template
- `Makefile` - Common commands

**Services:**
- `postgres` - PostgreSQL 16 database
- `rabbitmq` - RabbitMQ with management UI
- `scraper` - Go scraper in web mode
- `api` - FastAPI application
- `worker` - Review analysis (2 replicas)

---

## Current Status

### Completed
- All Python files created and tested
- PostgreSQL running with tables and data
- RabbitMQ configured with queues
- CSV parser working
- Producer working (CSV → DB → Queue)
- vLLM server running on Tensordock (206.168.83.147:8080)
- Worker processing reviews with Llama 3.1 8B
- **FastAPI REST API with all endpoints**
- **Scraper integration via Web API**
- **Docker Compose for production deployment**
- **Full pipeline tested: 8 reviews analyzed successfully**

### Pending
- Deploy to Tensordock VM
- Configure Cloudflare tunnel
- Set production passwords

---

## Pipeline Status
```
[API Request] → [Scraper] → [CSV] → [Parser] → [PostgreSQL] → [RabbitMQ] → [Worker] → [vLLM] → [Analysis DB]
     ↑                                                                                              │
     └──────────────────────────────── GET /api/places/{id}/reviews ◄───────────────────────────────┘
```

---

## Server Info

**vLLM Server:**
- IP: 206.168.83.147
- Port: 8080
- Model: meta-llama/Llama-3.1-8B-Instruct
- GPU: RTX 4090 (24GB)
- API Key: token-sadnxai

**Test Endpoint:**
```bash
curl -H "Authorization: Bearer token-sadnxai" \
  http://206.168.83.147:8080/v1/models
```

---

## Usage

### Production (Docker Compose)
```bash
# Configure secrets
cp .env.production.example .env.production
nano .env.production

# Start all services
make up-build

# Check logs
make logs

# Initialize database
make init-db

# Test scrape
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"query": "coffee shops in Riyadh"}'
```

### Development (Local)
```bash
# Start worker
python worker.py

# Start API
uvicorn api:app --reload --port 8000

# Process CSV manually
python producer.py --csv ../results/results.csv
```

### Makefile Commands
```bash
make up              # Start all services
make down            # Stop all services
make logs            # View logs
make restart         # Restart all
make scale-workers WORKERS=4  # Scale workers
make health          # Check API health
```
