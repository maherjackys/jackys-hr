# Migrations Ledger

> **WARNING** — Migrations **008 (RLS)** and **009 (rate_limits)** must be run **manually** in the
> [Supabase SQL Editor](https://supabase.com/dashboard). They are **not** applied automatically.
>
> Before deploying to production, verify RLS is active with:
> ```sql
> SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' ORDER BY tablename;
> ```
> Every table should show `rowsecurity = true`.

---

## Migration Table

| # | Filename | Purpose | Status |
|---|----------|---------|--------|
| 000 | `000_initial_schema.sql` | Creates all core application tables (users, logs, chat history, documents, etc.) | ✅ Applied |
| 001 | `001_user_management.sql` | User management module — registration, roles, profile fields | ✅ Applied |
| 002 | `002_security_indexes.sql` | Security and performance indexes on key columns | ✅ Applied |
| 003 | `003_rbac_permissions.sql` | Role-Based Access Control permissions system | ✅ Applied |
| 004 | `004_app_settings.sql` | `app_settings` key-value table for runtime configuration | ✅ Applied |
| 005 | `005_enhanced_logging.sql` | Enhanced logging — adds `actor` column and `login_history` table | ✅ Applied |
| 006 | `006_api_keys.sql` | `api_keys` table for managing external API key storage | ✅ Applied |
| 007 | `007_notifications.sql` | `notifications` table for in-app user notifications | ✅ Applied |
| 008 | `008_enable_rls.sql` | Enables Row Level Security (RLS) on all public tables | ✅ Applied |
| 009 | `009_rate_limits.sql` | `rate_limit_hits` table for cross-session rate limiting | ⚠️ Pending — run manually |
