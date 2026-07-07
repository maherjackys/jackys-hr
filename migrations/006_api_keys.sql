-- Migration 006: API Keys table
-- Run in Supabase SQL editor

CREATE TABLE IF NOT EXISTS api_keys (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    key_hash      TEXT NOT NULL UNIQUE,
    key_prefix    TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by    TEXT NOT NULL DEFAULT '',
    last_used_at  TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'revoked')),
    permissions   JSONB NOT NULL DEFAULT '[]'::JSONB
);

CREATE INDEX IF NOT EXISTS api_keys_status_idx      ON api_keys (status);
CREATE INDEX IF NOT EXISTS api_keys_key_hash_idx    ON api_keys (key_hash);
CREATE INDEX IF NOT EXISTS api_keys_created_at_idx  ON api_keys (created_at DESC);
