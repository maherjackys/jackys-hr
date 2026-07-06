-- ============================================================
-- Migration 001: User Management Module
-- Run once in the Supabase SQL Editor.
-- All statements are idempotent (safe to re-run).
-- ============================================================

-- 1. Add new columns to admin_users
ALTER TABLE admin_users
  ADD COLUMN IF NOT EXISTS role          TEXT        NOT NULL DEFAULT 'admin',
  ADD COLUMN IF NOT EXISTS is_active     BOOLEAN     NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS email         TEXT,
  ADD COLUMN IF NOT EXISTS display_name  TEXT,
  ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

-- 2. Elevate the original admin account to super_admin
UPDATE admin_users SET role = 'super_admin' WHERE username = 'admin';

-- 3. Role check constraint
ALTER TABLE admin_users
  DROP CONSTRAINT IF EXISTS admin_users_role_check;
ALTER TABLE admin_users
  ADD CONSTRAINT admin_users_role_check
  CHECK (role IN ('super_admin', 'admin', 'moderator', 'user'));

-- 4. Performance indexes
CREATE INDEX IF NOT EXISTS idx_admin_users_role      ON admin_users (role);
CREATE INDEX IF NOT EXISTS idx_admin_users_is_active ON admin_users (is_active);
