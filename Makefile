.PHONY: up down logs build restart clean init-db scale-workers health

# Default environment file
ENV_FILE ?= .env.production

# Start all services
up:
	docker compose --env-file $(ENV_FILE) up -d

# Start with build
up-build:
	docker compose --env-file $(ENV_FILE) up -d --build

# Stop all services
down:
	docker compose down

# Stop and remove volumes (WARNING: deletes data)
down-volumes:
	docker compose down -v

# View logs
logs:
	docker compose logs -f

# View logs for specific service
logs-api:
	docker compose logs -f api

logs-worker:
	docker compose logs -f worker

logs-scraper:
	docker compose logs -f scraper

# Build images without cache
build:
	docker compose build --no-cache

# Restart all services
restart:
	docker compose restart

# Restart specific service
restart-api:
	docker compose restart api

restart-worker:
	docker compose restart worker

restart-scraper:
	docker compose restart scraper

# Scale workers
scale-workers:
	docker compose up -d --scale worker=$(WORKERS)

# Initialize database tables
init-db:
	docker compose exec api python -c "from database import create_tables; create_tables()"

# Health check
health:
	@echo "Checking API health..."
	@curl -s http://localhost:8000/health | python -m json.tool || echo "API not responding"

# Clean up unused Docker resources
clean:
	docker system prune -f

# Development: run without Docker
dev-api:
	cd pipline && uvicorn api:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	cd pipline && python worker.py

# Test scrape endpoint
test-scrape:
	curl -X POST http://localhost:8000/api/scrape \
		-H "Content-Type: application/json" \
		-d '{"query": "coffee shops in Al Khobar", "depth": 5}'

# Show running containers
ps:
	docker compose ps

# Show container resource usage
stats:
	docker stats --no-stream
