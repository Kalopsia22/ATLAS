-- ATLAS GeoSentinel — Supabase Schema (Vercel edition)
-- Run this once in your Supabase project → SQL Editor → Run

-- ── 1. Risk score history (one row per country per day) ──────────────────────
CREATE TABLE IF NOT EXISTS risk_scores (
    id               BIGSERIAL PRIMARY KEY,
    country_iso      CHAR(3)        NOT NULL,
    score_date       DATE           NOT NULL DEFAULT CURRENT_DATE,
    risk_score       NUMERIC(5,1)   NOT NULL,
    conflict_score   NUMERIC(5,1),
    sentiment_score  NUMERIC(5,1),
    event_velocity   NUMERIC(5,1),
    gdelt_tone       NUMERIC(6,2),
    trend            TEXT CHECK (trend IN ('rising', 'stable', 'falling')),
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    UNIQUE (country_iso, score_date)
);

CREATE INDEX IF NOT EXISTS idx_risk_scores_iso_date
    ON risk_scores (country_iso, score_date DESC);

CREATE INDEX IF NOT EXISTS idx_risk_scores_date
    ON risk_scores (score_date DESC);

-- ── 2. Live snapshot (single row, overwritten every 10 minutes by cron) ──────
-- This is what the /api/risk-scores route reads instantly — no aggregation.
CREATE TABLE IF NOT EXISTS live_snapshot (
    id          INT PRIMARY KEY DEFAULT 1,  -- always row 1
    payload     JSONB NOT NULL,             -- full scored + forecast JSON
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (id = 1)                          -- enforce single-row constraint
);

-- ── 3. Row Level Security — public read, no public write ──────────────────────
ALTER TABLE risk_scores   ENABLE ROW LEVEL SECURITY;
ALTER TABLE live_snapshot ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read risk_scores"
    ON risk_scores FOR SELECT USING (true);

CREATE POLICY "Public read live_snapshot"
    ON live_snapshot FOR SELECT USING (true);

-- Service role (used by cron function via SUPABASE_KEY) can write freely.
-- No additional policy needed — service role bypasses RLS by default.

-- ── 4. Convenience view: latest score per country ────────────────────────────
CREATE OR REPLACE VIEW latest_risk_scores AS
SELECT DISTINCT ON (country_iso)
    country_iso, score_date, risk_score,
    conflict_score, sentiment_score, event_velocity,
    gdelt_tone, trend
FROM risk_scores
ORDER BY country_iso, score_date DESC;
