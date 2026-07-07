-- ============================================================
-- Migration 004: app_settings table
-- Run once in the Supabase SQL Editor.
-- All statements are idempotent (safe to re-run).
--
-- Required by: core/settings_store.py
-- Columns: key TEXT PK, value JSONB
-- ============================================================

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT  PRIMARY KEY,
    value JSONB NOT NULL
);

INSERT INTO app_settings (key, value)
VALUES ('enabled_sources', '["company","dubai_hr"]'::jsonb)
ON CONFLICT (key) DO NOTHING;
