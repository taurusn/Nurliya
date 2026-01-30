# Next Session: Deploy to Tensordock

## What Was Done
- Built full API integration (FastAPI + Go scraper)
- Created Docker Compose for all services (postgres, rabbitmq, scraper, api, worker)
- Production config ready (Makefile, .env.production.example)
- All code complete and tested locally

## What's Next

### 1. Access Tensordock VM
```bash
ssh user@206.168.83.147
```

### 2. Clone Repository
```bash
git clone <repo-url> nurliya
cd nurliya
```

### 3. Configure Production Secrets
```bash
cp .env.production.example .env.production
nano .env.production
# Set strong passwords for DB_PASSWORD and RABBITMQ_PASSWORD
```

### 4. Ensure vLLM is Running
```bash
# vLLM should already be running on port 8080
curl http://localhost:8080/v1/models -H "Authorization: Bearer token-sadnxai"
```

### 5. Deploy with Docker Compose
```bash
make up-build
make init-db
make logs
```

### 6. Configure Cloudflare
- Create tunnel: `cloudflared tunnel create nurliya`
- Route DNS: `cloudflared tunnel route dns nurliya api.<domain>.com`
- Point tunnel to `http://localhost:8000`

### 7. Test
```bash
curl -X POST https://api.<domain>.com/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"query": "cafes in Riyadh"}'
```

## Key Files
- `docker-compose.yml` - All services
- `.env.production` - Secrets (create from example)
- `Makefile` - Commands (make up, make logs, etc.)
- `claude.md` - Full context for Claude

## Notes
- vLLM runs on HOST (not in Docker) - already set up
- Workers connect via `host.docker.internal:8080`
- API exposed on port 8000
