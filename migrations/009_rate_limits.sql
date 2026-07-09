-- 009: cross-session rate-limit hit log
-- Run in Supabase SQL Editor (requires service-role or superuser).
CREATE TABLE IF NOT EXISTS rate_limit_hits (
    id   BIGSERIAL PRIMARY KEY,
    key  TEXT        NOT NULL,
    ts   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_hits_key_ts
    ON rate_limit_hits (key, ts DESC);
ALTER TABLE rate_limit_hits ENABLE ROW LEVEL SECURITY;
