"""
Persistent background scheduler — runs inside the FastAPI process.
On Fly.io containers stay alive permanently so this thread runs uninterrupted.
Refreshes risk scores every 10 minutes using full Prophet forecasting.
"""

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from app.services.gdelt import TRACKED_COUNTRIES, fetch_all_countries
from app.services.scorer import score_country
from app.services.database import is_configured, upsert_scores, get_all_history
from app.models.risk import RiskScore

logger = logging.getLogger("atlas.scheduler")

REFRESH_INTERVAL = 600  # 10 minutes

# In-memory cache — always available instantly
_cache: list[RiskScore] = []
_last_refresh: Optional[datetime] = None
_lock = threading.Lock()


def get_cached_scores() -> list[RiskScore]:
    with _lock:
        return list(_cache)


def get_last_refresh() -> Optional[datetime]:
    return _last_refresh


async def _do_refresh():
    global _cache, _last_refresh
    logger.info("Starting risk score refresh...")
    t0 = time.monotonic()

    # 1. GDELT signals
    live_data = await fetch_all_countries()

    # 2. History from Supabase (for Prophet)
    all_history = {}
    if is_configured():
        all_history = await get_all_history(days=90)

    # 3. Score every country — Prophet when history available
    scores = []
    now = datetime.now(timezone.utc)
    for iso3, name in TRACKED_COUNTRIES.items():
        record = score_country(
            iso3=iso3,
            live=live_data.get(iso3, {}),
            history=all_history.get(iso3, []),
            force_linear=False,  # use Prophet — we have time on Fly
        )
        scores.append(RiskScore(
            country_iso=iso3,
            country_name=name,
            risk_score=record["risk_score"],
            conflict_score=record["conflict_score"],
            sentiment_score=record["sentiment_score"],
            event_velocity=record["event_velocity"],
            forecast_7d=record["forecast_7d"],
            forecast_30d=record["forecast_30d"],
            trend=record["trend"],
            last_updated=now,
            gdelt_tone=record["gdelt_tone"],
            forecast=record["forecast"],
            forecast_method=record["forecast_method"],
        ))

    sorted_scores = sorted(scores, key=lambda x: -x.risk_score)

    # 4. Update in-memory cache atomically
    with _lock:
        _cache = sorted_scores
        _last_refresh = now

    # 5. Persist to Supabase (non-blocking)
    if is_configured():
        rows = [s.model_dump() for s in sorted_scores]
        await upsert_scores(rows)

    elapsed = round(time.monotonic() - t0, 1)
    logger.info(f"Refresh complete — {len(scores)} countries in {elapsed}s "
                f"(method: {scores[0].forecast_method if scores else 'none'})")


def _run_scheduler():
    """Runs in a daemon thread — starts immediately, then loops every 10 min."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def loop_forever():
        while True:
            try:
                await _do_refresh()
            except Exception as e:
                logger.error(f"Refresh failed: {e}", exc_info=True)
            await asyncio.sleep(REFRESH_INTERVAL)

    loop.run_until_complete(loop_forever())


def start():
    """Called once at FastAPI startup — launches the scheduler daemon thread."""
    t = threading.Thread(target=_run_scheduler, daemon=True, name="atlas-scheduler")
    t.start()
    logger.info("Scheduler thread started — first refresh running in background.")
