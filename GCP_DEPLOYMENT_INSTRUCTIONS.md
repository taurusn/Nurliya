# Nurliya GCP Deployment Instructions

## Current State (as of deployment)

### Completed
- [x] GCP Project: `top-script-426108-s4`
- [x] GCP APIs enabled: Compute Engine, Secret Manager
- [x] Secrets created in GCP Secret Manager:
  - `VLLM_API_KEY` (Gemini API key)
  - `SMTP_PASSWORD` (email password)
  - `JWT_SECRET` (authentication token)
- [x] VM created: `nurliya-prod` in `europe-west1-b`
  - Type: e2-standard-2 (2 vCPU, 8GB RAM)
  - Disk: 100GB SSD
  - IP: 34.38.34.159
- [x] Docker & Docker Compose installed on VM
- [x] Cloudflared installed on VM

### Remaining Steps
- [ ] Clone repository
- [ ] Create .env.production on VM
- [ ] Set up Cloudflare Tunnel
- [ ] Run docker compose
- [ ] Verify deployment

---

## Architecture

```
Domains (via Cloudflare Tunnel):
├── api.nurliya.com      → localhost:8000 (FastAPI)
├── app.nurliya.com      → localhost:3002 (Client Portal)
├── dashboard.nurliya.com → localhost:3000 (Dashboard)
└── admin.nurliya.com    → localhost:5050 (pgAdmin)
```

---

## Step-by-Step Instructions

### 1. Clone Repository

```bash
cd ~
git clone <REPOSITORY_URL> nurliya
cd nurliya
```

Or if no git repo, transfer files using scp from local machine.

### 2. Create .env.production

Create `/home/42group/nurliya/.env.production` with:

```env
# GCP Secret Manager
GCP_PROJECT_ID=top-script-426108-s4
USE_SECRET_MANAGER=true

# Database
DB_PASSWORD=Pzj7EAx1h3MeKB7pZd7JOaQtfJdKpa1E

# RabbitMQ
RABBITMQ_PASSWORD=Rq9kW2mNvL5xYp8tCf4hDjAs3bEu6zXi

# LLM (Gemini API)
VLLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
VLLM_API_KEY=AIzaSyBEr-r6bLSb3oHw13xBmz4CPERX7GlBnis
VLLM_MODEL=gemini-2.0-flash

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=business@nurliya.com
SMTP_PASSWORD=qhyn gpay ufxx lcea
SMTP_FROM_EMAIL=business@nurliya.com

# Auth
JWT_SECRET=10b4498eace08e50eb472af15a7194f44dc27877091712757917601f91df30e2

# Frontend URLs (build-time)
DASHBOARD_API_URL=https://api.nurliya.com
DASHBOARD_WS_URL=wss://api.nurliya.com/ws
CLIENT_PORTAL_API_URL=https://api.nurliya.com

# pgAdmin
PGADMIN_PASSWORD=Pg4dm1n_Nurl1ya_2025!
```

### 3. Set Up Cloudflare Tunnel

```bash
# Authenticate (opens browser)
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create nurliya

# Note the tunnel ID from the output, then create config:
mkdir -p ~/.cloudflared

cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: nurliya
credentials-file: /home/42group/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: api.nurliya.com
    service: http://localhost:8000
  - hostname: app.nurliya.com
    service: http://localhost:3002
  - hostname: dashboard.nurliya.com
    service: http://localhost:3000
  - hostname: admin.nurliya.com
    service: http://localhost:5050
  - service: http_status:404
EOF

# Route DNS (run for each domain)
cloudflared tunnel route dns nurliya api.nurliya.com
cloudflared tunnel route dns nurliya app.nurliya.com
cloudflared tunnel route dns nurliya dashboard.nurliya.com
cloudflared tunnel route dns nurliya admin.nurliya.com

# Install as system service
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### 4. Deploy with Docker Compose

```bash
cd ~/nurliya
docker compose --env-file .env.production up -d --build
```

This will take 5-10 minutes on first build.

### 5. Initialize Database

```bash
docker exec nurliya-api python -c "from database import create_tables; create_tables()"
```

### 6. Verify Deployment

```bash
# Check containers
docker compose ps

# Check API health
curl http://localhost:8000/health

# Check system health
curl http://localhost:8000/api/system-health
```

### 7. Production Hardening (Optional)

**Daily database backups:**
```bash
cat > ~/backup-db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/42group/backups"
mkdir -p $BACKUP_DIR
docker exec nurliya-postgres pg_dump -U nurliya nurliya | gzip > $BACKUP_DIR/nurliya-$(date +%Y%m%d-%H%M%S).sql.gz
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
EOF
chmod +x ~/backup-db.sh
(crontab -l 2>/dev/null; echo "0 2 * * * /home/42group/backup-db.sh") | crontab -
```

**Docker log rotation:**
```bash
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
sudo systemctl restart docker
```

---

## Troubleshooting

**Check container logs:**
```bash
docker compose logs -f api
docker compose logs -f worker
```

**Restart all services:**
```bash
docker compose restart
```

**Rebuild after code changes:**
```bash
docker compose down
docker compose --env-file .env.production up -d --build
```

**Check Cloudflare Tunnel status:**
```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -f
```

---

## Important Files

- `docker-compose.yml` - Service definitions
- `.env.production` - Environment variables
- `~/.cloudflared/config.yml` - Tunnel routing
- `pipline/config.py` - App config with Secret Manager support
