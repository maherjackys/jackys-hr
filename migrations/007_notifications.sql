-- Migration 007: Notifications table
-- Run in Supabase SQL editor

CREATE TABLE IF NOT EXISTS notifications (
    id          BIGSERIAL PRIMARY KEY,
    type        TEXT NOT NULL DEFAULT 'info' CHECK (type IN ('info', 'warning', 'error', 'security')),
    title       TEXT NOT NULL,
    message     TEXT NOT NULL DEFAULT '',
    priority    INTEGER NOT NULL DEFAULT 1 CHECK (priority BETWEEN 1 AND 3),
    is_read     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata    JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS notifications_is_read_idx   ON notifications (is_read);
CREATE INDEX IF NOT EXISTS notifications_type_idx      ON notifications (type);
CREATE INDEX IF NOT EXISTS notifications_created_idx   ON notifications (created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_priority_idx  ON notifications (priority DESC);
