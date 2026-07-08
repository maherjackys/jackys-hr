-- ============================================================
-- Migration 008: Enable Row Level Security on all tables
-- Run in Supabase SQL Editor.  Idempotent — safe to re-run.
--
-- WHY THIS MATTERS
-- ─────────────────
-- Supabase exposes every table via the auto-generated REST API.
-- Without RLS enabled, ANY request that obtains the anon key can
-- read/write every row in every table, regardless of who the
-- requester is.
--
-- This application uses the SERVICE ROLE key (SUPABASE_KEY) which
-- bypasses RLS by design — so enabling RLS does NOT break the app.
-- It is a defence-in-depth measure:
--
--   • If the anon key is ever accidentally exposed, attackers cannot
--     read admin_users, admin_sessions, api_keys, or logs.
--   • Satisfies SOC 2 / ISO 27001 "least privilege" controls.
--   • Prevents accidental data leakage via Supabase auto-API.
--
-- STRATEGY: Enable RLS with NO policies on every table.
-- Result: service-role key (app) retains full access;
--         anon key has ZERO access to every table.
-- ============================================================

-- ── Core auth tables ──────────────────────────────────────────
ALTER TABLE admin_users      ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_sessions   ENABLE ROW LEVEL SECURITY;

-- ── Logging tables ────────────────────────────────────────────
ALTER TABLE logs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE login_history    ENABLE ROW LEVEL SECURITY;

-- ── Configuration / feature store ────────────────────────────
ALTER TABLE app_settings     ENABLE ROW LEVEL SECURITY;

-- ── RBAC tables ───────────────────────────────────────────────
ALTER TABLE roles            ENABLE ROW LEVEL SECURITY;
ALTER TABLE permissions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;

-- ── API key + notification tables (migrations 006 + 007) ──────
ALTER TABLE api_keys         ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications    ENABLE ROW LEVEL SECURITY;

-- ── Verification (run manually after applying) ────────────────
-- SELECT tablename, rowsecurity
-- FROM   pg_tables
-- WHERE  schemaname = 'public'
-- ORDER  BY tablename;
-- Every application table should show rowsecurity = true.
