-- Migration 005: Enhanced logging — actor column + login_history table
-- Run in Supabase SQL Editor.

-- Add actor column to logs (stores which admin triggered the action).
-- answer_preview is repurposed for actor in admin_action rows (backward compat).
-- A dedicated actor column is cleaner for new rows.
ALTER TABLE logs ADD COLUMN IF NOT EXISTS actor TEXT;

-- Back-fill actor from answer_preview for existing admin_action rows where
-- answer_preview looks like a username (short, no HTML).
UPDATE logs
SET    actor = answer_preview
WHERE  log_type = 'admin_action'
  AND  answer_preview IS NOT NULL
  AND  length(answer_preview) <= 100;

-- Login history table — records every login attempt for security auditing.
CREATE TABLE IF NOT EXISTS login_history (
    id         BIGSERIAL PRIMARY KEY,
    username   TEXT        NOT NULL,
    success    BOOLEAN     NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS login_history_username_idx ON login_history (username);
CREATE INDEX IF NOT EXISTS login_history_created_idx  ON login_history (created_at DESC);

-- Row-level security (optional — recommended for production)
-- ALTER TABLE login_history ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "service_role_only" ON login_history USING (auth.role() = 'service_role');
