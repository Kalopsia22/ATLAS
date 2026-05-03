"""
Vercel Cron Function — POST /api/cron
Schedule: every 10 minutes (vercel.json)
Hobby plan: 60s max  |  Pro plan: 300s max

Strategy for 60s budget:
  - GDELT fetch:     ~20s  (async, 5 concurrent)
  - Scoring:          ~5s  (linear model, all 47 countries)
  - Supabase writes:  ~3s  (two upserts)
  - Total:           ~28s  — comfortably under 60s

Prophet is intentionally skipped here to stay within 60s.
It runs on-demand in /api/risk-scores/[iso3] when history is available.
"""

import sys, os, json, asyncio, logging, time
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_lib"))

import db as db_module
import gdelt as gdelt_module
import scorer as scorer_module
from gdelt import TRACKED_COUNTRIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("atlas.cron")


def _ok(h, body: dict):
    h.send_response(200)
    h.send_header("Content-Type", "application/json")
    h.end_headers()
    h.wfile.write(json.dumps(body).encode())


def _err(h, code: int, msg: str):
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.end_headers()
    h.wfile.write(json.dumps({"error": msg}).encode())


def _verify(headers: dict) -> bool:
    secret = os.environ.get("CRON_SECRET", "")
    if not secret:
        return True
    auth = headers.get("authorization", "") or headers.get("Authorization", "")
    return auth == f"Bearer {secret}"


async def run_refresh() -> dict:
    t0 = time.monotonic()
    client = db_module.get_client()

    # 1. Fetch live GDELT signals (async, ~20s)
    logger.info("Fetching GDELT signals...")
    live_data = await gdelt_module.fetch_all_countries()
    logger.info(f"GDELT done in {time.monotonic()-t0:.1f}s")

    # 2. Load 90-day history for Prophet fallback (single Supabase query)
    since = (date.today().replace(year=date.today().year - 1)).isoformat()
    try:
        rows = client.table("risk_scores") \
            .select("country_iso,score_date,risk_score,trend") \
            .gte("score_date", since).order("score_date").execute().data or []
    except Exception as e:
        logger.warning(f"History load failed: {e}")
        rows = []

    history_by_iso: dict[str, list] = {}
    for r in rows:
        history_by_iso.setdefault(r["country_iso"], []).append({
            "date": r["score_date"],
            "risk_score": float(r["risk_score"]),
            "trend": r.get("trend", "stable"),
        })

    # 3. Score all countries using fast linear model (Prophet reserved for on-demand)
    logger.info("Scoring countries...")
    scored = []
    for iso3 in TRACKED_COUNTRIES:
        record = scorer_module.score_country(
            iso3,
            live_data.get(iso3, {}),
            history_by_iso.get(iso3, []),
            force_linear=True,   # stay within 60s budget
        )
        scored.append(record)
    logger.info(f"Scoring done in {time.monotonic()-t0:.1f}s")

    # 4. Upsert daily history
    today = date.today().isoformat()
    db_rows = [{
        "country_iso":     s["country_iso"],
        "score_date":      today,
        "risk_score":      s["risk_score"],
        "conflict_score":  s["conflict_score"],
        "sentiment_score": s["sentiment_score"],
        "event_velocity":  s["event_velocity"],
        "gdelt_tone":      s["gdelt_tone"],
        "trend":           s["trend"],
    } for s in scored]
    client.table("risk_scores").upsert(db_rows, on_conflict="country_iso,score_date").execute()

    # 5. Write live snapshot (single row read by /api/risk-scores instantly)
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps({
        "generated_at": now,
        "scores": sorted([{
            "country_iso":     s["country_iso"],
            "country_name":    TRACKED_COUNTRIES[s["country_iso"]],
            "risk_score":      s["risk_score"],
            "conflict_score":  s["conflict_score"],
            "sentiment_score": s["sentiment_score"],
            "event_velocity":  s["event_velocity"],
            "gdelt_tone":      s["gdelt_tone"],
            "trend":           s["trend"],
            "forecast_7d":     s["forecast_7d"],
            "forecast_30d":    s["forecast_30d"],
            "forecast":        s["forecast"],
            "forecast_method": s["forecast_method"],
        } for s in scored], key=lambda x: -x["risk_score"])
    })
    client.table("live_snapshot").upsert(
        [{"id": 1, "payload": payload, "updated_at": now}],
        on_conflict="id"
    ).execute()

    elapsed = round(time.monotonic() - t0, 1)
    logger.info(f"Cron complete in {elapsed}s")
    return {
        "status": "ok",
        "countries_scored": len(scored),
        "elapsed_seconds": elapsed,
        "forecast_method": "linear (on-demand Prophet available per country)",
        "generated_at": now,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        _ok(self, {"status": "cron ready", "schedule": "*/10 * * * *"})

    def do_POST(self):
        if not _verify(dict(self.headers)):
            _err(self, 401, "Unauthorized")
            return
        try:
            result = asyncio.run(run_refresh())
            _ok(self, result)
        except Exception as e:
            logger.error(f"Cron failed: {e}", exc_info=True)
            _err(self, 500, str(e))

    def log_message(self, fmt, *args):
        logger.info(fmt % args)
