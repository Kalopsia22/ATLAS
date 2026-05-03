# ATLAS GeoSentinel — Vercel Full-Stack Edition
### Geopolitical Risk Intelligence Platform · All-in-one Vercel deployment

> One GitHub repo. One Vercel project. Zero separate backend service.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Vercel Project                       │
│                                                          │
│  ┌─────────────────────┐   ┌───────────────────────┐   │
│  │   Next.js Frontend  │   │  Python API Functions  │   │
│  │  /src/app/page.tsx  │   │  /api/risk-scores/     │   │
│  │  Deck.gl world map  │   │  /api/history/         │   │
│  │  Time-slider        │◄──│  /api/countries/       │   │
│  │  Country panel      │   │  (read-only, ~200ms)   │   │
│  └─────────────────────┘   └───────────────────────┘   │
│                                        ▲                 │
│  ┌─────────────────────────────────────┤                 │
│  │     Vercel Cron  (*/10 * * * *)     │                 │
│  │  /api/cron/refresh.py               │                 │
│  │  1. Fetch GDELT signals             │                 │
│  │  2. Run Prophet forecasting         │                 │
│  │  3. Write → Supabase                │                 │
│  └─────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │     Supabase     │
              │  risk_scores     │  ← daily history (time-slider)
              │  live_snapshot   │  ← current scores (instant reads)
              └──────────────────┘
```

**Key insight:** The `/api/risk-scores` route is *instant* — it just reads a pre-computed JSONB blob from Supabase that the cron function writes every 10 minutes. Prophet never runs on a user request. Cold start is ~200ms.

---

## Deploy in 4 steps

### Step 1 — Set up Supabase (free)

1. Go to [supabase.com](https://supabase.com) → New Project
2. Once created → **SQL Editor** → paste the contents of `supabase_schema.sql` → **Run**
3. Go to **Settings** → **API** → copy:
   - **Project URL** → `SUPABASE_URL`
   - **service_role** key (secret) → `SUPABASE_KEY`  
     ⚠️ Use the **service_role** key, not anon — the cron function needs write access

### Step 2 — Push to GitHub

```bash
git init
git add .
git commit -m "feat: ATLAS GeoSentinel — Vercel full-stack"
gh repo create atlas --public --source=. --push
```

### Step 3 — Deploy to Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project** → import your `atlas` repo
2. Framework: **Next.js** (auto-detected)
3. Root directory: `.` (repo root — no subdirectory)
4. **Environment Variables** → add:
   ```
   SUPABASE_URL          = https://xxxx.supabase.co
   SUPABASE_KEY          = your-service-role-key
   CRON_SECRET           = (Vercel generates this — copy from Cron Jobs page after deploy)
   NEXT_PUBLIC_CRON_SECRET = same value as CRON_SECRET
   ```
5. Click **Deploy**

### Step 4 — Trigger the first cron run

After deploy, the cron runs automatically every 10 minutes. To trigger immediately:

```bash
# Replace with your Vercel URL and CRON_SECRET
curl -X POST https://your-atlas.vercel.app/api/cron/refresh \
  -H "Authorization: Bearer your-cron-secret"
```

Or click **Refresh** in the dashboard UI.

Verify data is flowing:
```
GET https://your-atlas.vercel.app/api/risk-scores
```
Should return 47 country scores within seconds of the cron completing.

---

## Local Development

```bash
npm install --legacy-peer-deps

# Create local env file
cp .env.example .env.local
# Fill in SUPABASE_URL and SUPABASE_KEY

npm run dev
# Visit http://localhost:3000
```

To test the cron function locally:
```bash
curl -X POST http://localhost:3000/api/cron/refresh
```

---

## API Reference

| Route | Method | Description |
|---|---|---|
| `/api/risk-scores` | GET | All country scores (from live_snapshot) |
| `/api/risk-scores/[iso3]` | GET | Country detail + history + forecast |
| `/api/history?iso3=UKR` | GET | 90-day history for one country |
| `/api/history?all=true` | GET | Full timeline for all countries (time-slider) |
| `/api/countries` | GET | List of all 47 tracked countries |
| `/api/cron/refresh` | POST | Trigger Prophet scoring + Supabase write |

---

## Optional: Unlock ACLED Data

Register free at [acleddata.com](https://acleddata.com/access-data/) then add to Vercel:
```
ACLED_KEY   = your-key
ACLED_EMAIL = you@email.com
```
This replaces static conflict baselines with real event counts and fatality data.

---

## Roadmap

- [x] v1.0 — Deck.gl world map, GDELT scoring, FastAPI  
- [x] v1.2 — Prophet forecasting, Supabase history, time-slider  
- [x] v1.3 — Vercel-native full-stack (this version)  
- [ ] v2.0 — ThreatCast: WebSocket escalation alerts (requires separate worker)  
- [ ] v2.1 — OSINT Fusion: NER entity graph  
- [ ] v3.0 — CriticalShield: Infrastructure cascade simulation  
- [ ] v3.1 — MacroLens: Granger causality + RAG intelligence briefs  

---

## License
Research and educational use only. Data sourced from GDELT, ACLED, and open public APIs.
