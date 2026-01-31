# Nurliya Production Deployment

## Architecture

```
                    Cloudflare Edge (SSL)
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
    ▼                      ▼                      ▼
api.nurliya.com  dashboard.nurliya.com  admin.nurliya.com
    │                      │                      │
    └──────────────────────┼──────────────────────┘
                           │
                    Cloudflare Tunnel
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         localhost:8000  :3000        :5050
            (API)     (Dashboard)   (pgAdmin)
```

## Services

| Service | Port | Domain | Description |
|---------|------|--------|-------------|
| API | 8000 | api.nurliya.com | FastAPI backend |
| Dashboard | 3000 | dashboard.nurliya.com | Next.js frontend |
| pgAdmin | 5050 | admin.nurliya.com | Database admin UI |
| PostgreSQL | 5432 | - | Database (internal) |
| RabbitMQ | 5672 | - | Message queue (internal) |
| Scraper | 8080 | - | Google Maps scraper (internal) |
| Worker | - | - | Review analysis workers |

## Environment Variables

### `.env.production`

```env
# Database
DB_PASSWORD=<strong-password>

# RabbitMQ
RABBITMQ_PASSWORD=<strong-password>

# vLLM (AI analysis)
VLLM_BASE_URL=http://host.docker.internal:8080/v1
VLLM_API_KEY=token-sadnxai

# SMTP (email notifications)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=business@nurliya.com
SMTP_PASSWORD=<app-password>
SMTP_FROM_EMAIL=business@nurliya.com

# Dashboard (build-time args)
DASHBOARD_API_URL=https://api.nurliya.com
DASHBOARD_WS_URL=wss://api.nurliya.com/ws

# pgAdmin
PGADMIN_PASSWORD=<strong-password>
```

## Secrets Management

Nurliya supports flexible secrets management with automatic fallback:

```
┌─────────────────────────────────────────────────────────────┐
│                    Secret Lookup Order                       │
├─────────────────────────────────────────────────────────────┤
│  1. GCP Secret Manager  (if enabled and available)          │
│          ↓ (not found)                                       │
│  2. Environment Variable                                     │
│          ↓ (not found)                                       │
│  3. Default Value                                            │
└─────────────────────────────────────────────────────────────┘
```

### Option 1: Environment Variables Only (Default)

No additional configuration needed. Use `.env` or `.env.production` files:

```bash
# Just start the services - env vars are used automatically
docker compose --env-file .env.production up -d
```

### Option 2: GCP Secret Manager with Env Fallback

Enable Secret Manager for production deployments on GCP:

#### 1. Set environment variables

```bash
# Add to .env.production
GCP_PROJECT_ID=your-gcp-project-id
USE_SECRET_MANAGER=true
```

#### 2. Create secrets in GCP

```bash
# Database connection string
echo -n "postgresql://nurliya:PASSWORD@HOST:5432/nurliya" | \
  gcloud secrets create DATABASE_URL --data-file=-

# RabbitMQ connection string
echo -n "amqp://nurliya:PASSWORD@HOST:5672/" | \
  gcloud secrets create RABBITMQ_URL --data-file=-

# vLLM API key
echo -n "your-vllm-api-key" | \
  gcloud secrets create VLLM_API_KEY --data-file=-

# SMTP password
echo -n "your-smtp-app-password" | \
  gcloud secrets create SMTP_PASSWORD --data-file=-
```

#### 3. Grant access to your service account

```bash
# For Compute Engine / GKE
gcloud secrets add-iam-policy-binding DATABASE_URL \
  --member="serviceAccount:YOUR_SA@PROJECT.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Repeat for each secret...
```

#### 4. Supported secrets

| Secret Name | Description | Required |
|-------------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `RABBITMQ_URL` | RabbitMQ connection string | Yes |
| `VLLM_API_KEY` | vLLM server API key | Yes |
| `VLLM_BASE_URL` | vLLM server URL | No |
| `VLLM_MODEL` | LLM model name | No |
| `SMTP_HOST` | SMTP server hostname | No |
| `SMTP_PORT` | SMTP server port | No |
| `SMTP_USER` | SMTP username | No |
| `SMTP_PASSWORD` | SMTP password | No |
| `SMTP_FROM_EMAIL` | Sender email address | No |
| `SCRAPER_API_URL` | Scraper service URL | No |

### Fallback Behavior

The system gracefully handles missing components:

- **Secret Manager package not installed**: Uses env vars only
- **GCP credentials unavailable**: Uses env vars only
- **Specific secret not in Secret Manager**: Falls back to env var for that secret
- **Neither available**: Uses default value (if defined)

This allows the same codebase to run locally (env vars) and in GCP (Secret Manager) without code changes.

## Cloudflare Tunnel Setup

### 1. Install cloudflared

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

### 2. Authenticate

```bash
cloudflared tunnel login
```

### 3. Create tunnel

```bash
cloudflared tunnel create nurliya
```

### 4. Configure ingress rules

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: nurliya
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: api.nurliya.com
    service: http://localhost:8000
  - hostname: dashboard.nurliya.com
    service: http://localhost:3000
  - hostname: admin.nurliya.com
    service: http://localhost:5050
  - service: http_status:404
```

### 5. Route DNS

```bash
cloudflared tunnel route dns nurliya api.nurliya.com
cloudflared tunnel route dns nurliya dashboard.nurliya.com
cloudflared tunnel route dns nurliya admin.nurliya.com
```

### 6. Run as service

```bash
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared
```

## Deployment Commands

### Start all services

```bash
docker compose --env-file .env.production up -d --build
```

### Initialize database

```bash
docker exec nurliya-api python -c "from database import create_tables; create_tables()"
```

### Check health

```bash
curl http://localhost:8000/health
```

### View logs

```bash
docker compose logs -f           # All services
docker compose logs -f api       # API only
docker compose logs -f worker    # Workers only
```

### Scale workers

```bash
docker compose up -d --scale worker=4
```

### Stop all services

```bash
docker compose down
```

## TODO Before Production

- [x] ~~Consolidate `.env` and `.env.production` into single file~~ Flexible secrets management implemented
- [x] Add GCP Secret Manager support with env var fallback
- [ ] Add CORS middleware to API (allow dashboard.nurliya.com)
- [ ] Create `deploy.sh` script for one-command deployment
- [ ] Create `setup-tunnel.sh` for Cloudflare tunnel automation
- [ ] Add review deduplication (author + text + place_id)
- [ ] Set up database backups
- [ ] Configure monitoring/alerting
