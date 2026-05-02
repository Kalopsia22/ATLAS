# ATLAS GeoSentinel — Fly.io Edition
### Always-on · No cold starts · Free tier · Python + Next.js

---

## Architecture

```
atlas-fly/
├── backend/          FastAPI + Prophet   → atlas-backend.fly.dev
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/  risk.py  countries.py  health.py
│   │   ├── services/ gdelt.py scorer.py database.py scheduler.py
│   │   └── models/   risk.py
│   ├── Dockerfile
│   ├── fly.toml
│   └── requirements.txt
└── frontend/         Next.js + Deck.gl  → atlas-frontend.fly.dev
    ├── src/
    ├── Dockerfile
    └── fly.toml
```

**Key difference from Vercel:** The backend is a persistent container — the
Prophet scheduler runs as a real background thread every 10 minutes with no
time limits. No cron functions, no cold starts, no splitting ML across services.

---

## Deploy

### Prerequisites
```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Log in (creates free account if you don't have one)
fly auth login
```

### Step 1 — Supabase (2 min)
1. [supabase.com](https://supabase.com) → New Project
2. SQL Editor → paste `supabase_schema.sql` → Run
3. Settings → API → copy **Project URL** and **service_role key**

### Step 2 — Push to GitHub
```bash
git init && git add . && git commit -m "ATLAS GeoSentinel — Fly.io"
gh repo create atlas --public --source=. --push
```

### Step 3 — Deploy Backend
```bash
cd backend

# Create the Fly app (first time only)
fly apps create atlas-backend

# Set secrets
fly secrets set \
  SUPABASE_URL=https://xxxx.supabase.co \
  SUPABASE_KEY=your-service-role-key \
  ALLOWED_ORIGINS=https://atlas-frontend.fly.dev

# Deploy
fly deploy

# Verify
curl https://atlas-backend.fly.dev/api/health
```

### Step 4 — Deploy Frontend
```bash
cd ../frontend

# Create the Fly app
fly apps create atlas-frontend

# Point frontend at the backend
fly secrets set NEXT_PUBLIC_API_URL=https://atlas-backend.fly.dev

# Deploy
fly deploy
```

### Step 5 — Verify
```bash
# Backend health
curl https://atlas-backend.fly.dev/api/health

# Risk scores (populated after first 10-min scheduler run)
curl https://atlas-backend.fly.dev/api/risk-scores

# Frontend
open https://atlas-frontend.fly.dev
```

---

## Auto-deploy from GitHub

```bash
# Backend
cd backend
fly deploy --remote-only   # Fly builds in the cloud, not locally

# Set up GitHub Actions auto-deploy (optional):
# fly tokens create deploy -x 999999h
# Add as FLY_API_TOKEN secret in GitHub repo settings
```

Example `.github/workflows/deploy.yml`:
```yaml
name: Deploy to Fly.io
on:
  push:
    branches: [main]
jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: fly deploy --remote-only
        working-directory: backend
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}

  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: fly deploy --remote-only
        working-directory: frontend
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

---

## API Reference

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health + cache status |
| `GET /api/risk-scores` | All 47 country scores |
| `GET /api/risk-scores/{iso3}` | Country detail + forecast |
| `GET /api/history/{iso3}` | 90-day history |
| `GET /api/history/timeline/all` | Full timeline (time-slider) |
| `GET /api/countries` | Tracked countries list |
| `POST /api/risk-scores/refresh` | Trigger immediate refresh |

---

## Free Tier Limits

Fly.io free tier includes:
- 3 shared-cpu-1x VMs with 256MB RAM (we use 2)
- 160GB outbound transfer/month
- Persistent volumes up to 3GB (not needed — we use Supabase)

Our usage: 2 VMs (backend 1GB RAM, frontend 512MB) — **within free limits**.
The `auto_stop_machines = false` in fly.toml keeps both always-on.

---

## Roadmap
- [x] v1.3 — Fly.io always-on deployment
- [ ] v2.0 — ThreatCast WebSocket escalation alerts
- [ ] v2.1 — OSINT Fusion entity graph
- [ ] v3.0 — CriticalShield infrastructure cascade
- [ ] v3.1 — MacroLens Granger + RAG briefs
