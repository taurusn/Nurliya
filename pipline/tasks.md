# Nurliya Pipeline - Tasks

## Phase 1: Foundation
- [x] 1.1 Create requirements.txt
- [x] 1.2 Create .env with credentials
- [x] 1.3 Create config.py
- [x] 1.4 Create database.py with models
- [x] 1.5 Start PostgreSQL container
- [x] 1.6 Start RabbitMQ container
- [x] 1.7 Create database tables

## Phase 2: CSV Parser
- [x] 2.1 Create csv_parser.py
- [x] 2.2 Test parsing sample CSV

## Phase 3: Queue System
- [x] 3.1 Create rabbitmq.py helper
- [x] 3.2 Test queue connection

## Phase 4: LLM Integration
- [x] 4.1 Create gemini_client.py (deprecated)
- [x] 4.2 Create llm_client.py for vLLM
- [x] 4.3 Test single review analysis with Llama 3.1 8B

## Phase 5: Pipeline
- [x] 5.1 Create producer.py
- [x] 5.2 Create worker.py
- [x] 5.3 Test producer flow (CSV → DB → Queue)
- [x] 5.4 Test worker flow (Queue → LLM → Analysis DB)

## Phase 6: vLLM Server Setup
- [x] 6.1 Set up Tensordock VM (206.168.83.147) with RTX 4090
- [x] 6.2 Install vLLM and dependencies
- [x] 6.3 Download Llama 3.1 8B Instruct
- [x] 6.4 Start vLLM server on port 8080
- [x] 6.5 Test API endpoint

## Phase 7: API & Scraper Integration
- [x] 7.1 Create scraper_client.py (HTTP client for Go scraper)
- [x] 7.2 Create orchestrator.py (background task logic)
- [x] 7.3 Create api.py (FastAPI application)
- [x] 7.4 Add ScrapeJob model to database.py
- [x] 7.5 Update config.py with scraper/API settings
- [x] 7.6 Update requirements.txt (fastapi, uvicorn, httpx)

## Phase 8: Docker & Production
- [x] 8.1 Create pipline/Dockerfile
- [x] 8.2 Create docker-compose.yml (all services)
- [x] 8.3 Create .env.production.example
- [x] 8.4 Create Makefile (common commands)
- [x] 8.5 Update claude.md with new architecture

## Phase 9: Deployment (Pending)
- [ ] 9.1 Deploy to Tensordock VM
- [ ] 9.2 Configure Cloudflare tunnel
- [ ] 9.3 Set production passwords
- [ ] 9.4 Test end-to-end flow

---

## Files Created
| File | Status | Purpose |
|------|--------|---------|
| requirements.txt | Done | Python dependencies |
| .env | Done | Credentials |
| config.py | Done | Environment config |
| database.py | Done | SQLAlchemy models (5 tables) |
| csv_parser.py | Done | Parse scraper CSV |
| rabbitmq.py | Done | RabbitMQ helper |
| gemini_client.py | Deprecated | Gemini API wrapper |
| llm_client.py | Done | vLLM/OpenAI API wrapper |
| producer.py | Done | Queue reviews |
| worker.py | Done | Analyze reviews |
| api.py | Done | FastAPI REST application |
| scraper_client.py | Done | Go scraper HTTP client |
| orchestrator.py | Done | Background task logic |
| Dockerfile | Done | Container build |

## Root Files
| File | Status | Purpose |
|------|--------|---------|
| docker-compose.yml | Done | All services orchestration |
| Makefile | Done | Common commands |
| .env.production.example | Done | Production env template |
| claude.md | Done | Claude context anchor |
