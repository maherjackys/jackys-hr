-- ============================================================
-- Migration 002: Security & Performance Indexes
-- Run once in the Supabase SQL Editor.
-- All statements are idempotent (safe to re-run).
-- ============================================================

-- 1. admin_sessions: fast lookup by username (used on every session restore)
CREATE INDEX IF NOT EXISTS idx_admin_sessions_username
  ON admin_sessions (username);

-- 2. admin_sessions: fast cleanup of expired sessions (TTL housekeeping)
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires_at
  ON admin_sessions (expires_at);

-- 3. logs: fast filtering by log_type (used by fetch_logs)
CREATE INDEX IF NOT EXISTS idx_logs_log_type
  ON logs (log_type);

-- 4. logs: fast ordering by timestamp (newest-first queries)
CREATE INDEX IF NOT EXISTS idx_logs_ts
  ON logs (ts DESC);

-- 5. logs: fast filtering by source
CREATE INDEX IF NOT EXISTS idx_logs_source
  ON logs (source);
