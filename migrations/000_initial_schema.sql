-- ============================================================
-- Migration 000: Initial Schema  (COMPLETE — run on a fresh Supabase project)
-- All statements are idempotent (safe to re-run).
--
-- Covers every table the application reads or writes:
--   admin_users        core/auth.py
--   admin_sessions     core/auth.py
--   logs               core/db_logger.py
--   app_settings       core/settings_store.py
--   roles              core/rbac.py  (migration 003)
--   permissions        core/rbac.py  (migration 003)
--   role_permissions   core/rbac.py  (migration 003)
-- ============================================================


-- ──────────────────────────────────────────────────────────────
-- 1. admin_users
--    Columns expected by auth.py:
--      username TEXT PK, password_hash TEXT, role TEXT,
--      is_active BOOLEAN, email TEXT, display_name TEXT,
--      created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ,
--      last_login_at TIMESTAMPTZ
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_users (
    username        TEXT        PRIMARY KEY,
    password_hash   TEXT        NOT NULL DEFAULT '',
    role            TEXT        NOT NULL DEFAULT 'admin'
                                CHECK (role IN ('super_admin','admin','moderator','user')),
    is_active       BOOLEAN     NOT NULL DEFAULT true,
    email           TEXT,
    display_name    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_admin_users_role      ON admin_users (role);
CREATE INDEX IF NOT EXISTS idx_admin_users_is_active ON admin_users (is_active);


-- ──────────────────────────────────────────────────────────────
-- 2. admin_sessions
--    Columns expected by auth.py:
--      id TEXT PK (64-hex token), username TEXT, expires_at TIMESTAMPTZ,
--      created_at TIMESTAMPTZ
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_sessions (
    id          TEXT        PRIMARY KEY,
    username    TEXT        NOT NULL REFERENCES admin_users(username) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_sessions_username   ON admin_sessions (username);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires_at ON admin_sessions (expires_at);


-- ──────────────────────────────────────────────────────────────
-- 3. logs
--    Columns expected by db_logger.py:
--      id BIGSERIAL PK, log_type TEXT, source TEXT, query TEXT,
--      answer_preview TEXT, score FLOAT, vote TEXT, ts TIMESTAMPTZ,
--      extra JSONB
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS logs (
    id             BIGSERIAL   PRIMARY KEY,
    log_type       TEXT        NOT NULL DEFAULT 'unanswered',
    source         TEXT,
    query          TEXT,
    answer_preview TEXT,
    score          FLOAT,
    vote           TEXT,
    ts             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra          JSONB
);

CREATE INDEX IF NOT EXISTS idx_logs_log_type ON logs (log_type);
CREATE INDEX IF NOT EXISTS idx_logs_ts       ON logs (ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_source   ON logs (source);


-- ──────────────────────────────────────────────────────────────
-- 4. app_settings
--    Columns expected by settings_store.py:
--      key TEXT PK, value JSONB
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT  PRIMARY KEY,
    value JSONB NOT NULL
);

INSERT INTO app_settings (key, value)
VALUES ('enabled_sources', '["company","dubai_hr"]'::jsonb)
ON CONFLICT (key) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 5. roles
--    Columns expected by rbac.py: name TEXT PK, label TEXT,
--      level INT, is_system BOOLEAN, created_at TIMESTAMPTZ
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roles (
    name        TEXT        PRIMARY KEY,
    label       TEXT        NOT NULL,
    description TEXT,
    level       INTEGER     NOT NULL DEFAULT 1,
    is_system   BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO roles (name, label, level, is_system) VALUES
    ('super_admin', 'Super Admin', 4, true),
    ('admin',       'Admin',       3, true),
    ('moderator',   'Moderator',   2, true),
    ('user',        'User',        1, true)
ON CONFLICT (name) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 6. permissions
--    Columns expected by rbac.py: key TEXT PK, category TEXT,
--      label TEXT, sort_order INT
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS permissions (
    key         TEXT        PRIMARY KEY,
    category    TEXT        NOT NULL,
    label       TEXT        NOT NULL,
    description TEXT,
    sort_order  INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO permissions (key, category, label, sort_order) VALUES
    -- User Management
    ('users.view',           'User Management',    'View Users',        10),
    ('users.create',         'User Management',    'Create Users',      20),
    ('users.edit',           'User Management',    'Edit Users',        30),
    ('users.delete',         'User Management',    'Delete Users',      40),
    ('users.disable',        'User Management',    'Disable Users',     50),
    ('users.enable',         'User Management',    'Enable Users',      60),
    ('users.reset_password', 'User Management',    'Reset Password',    70),
    ('users.force_logout',   'User Management',    'Force Logout',      80),
    ('users.assign_roles',   'User Management',    'Assign Roles',      90),
    ('users.view_sessions',  'User Management',    'View Sessions',    100),
    -- Content Management
    ('documents.view',       'Content Management', 'View Documents',    10),
    ('documents.create',     'Content Management', 'Upload Documents',  20),
    ('documents.delete',     'Content Management', 'Delete Documents',  30),
    ('documents.rebuild',    'Content Management', 'Rebuild Index',     40),
    -- Sources
    ('sources.view',         'Sources',            'View Sources',      10),
    ('sources.add',          'Sources',            'Add Source',        20),
    ('sources.delete',       'Sources',            'Delete Source',     30),
    -- Dashboard
    ('dashboard.view',       'Dashboard',          'View Dashboard',    10),
    ('dashboard.logs',       'Dashboard',          'View Logs',         20),
    ('dashboard.debug',      'Dashboard',          'View Debug Info',   30),
    -- Settings
    ('settings.view',        'Settings',           'View Settings',     10),
    ('settings.edit',        'Settings',           'Edit Settings',     20),
    -- Roles
    ('roles.view',           'Roles',              'View Roles',        10),
    ('roles.edit',           'Roles',              'Edit Permissions',  20)
ON CONFLICT (key) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 7. role_permissions
--    Columns expected by rbac.py: role TEXT, permission TEXT
--    (composite PK: role + permission)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS role_permissions (
    role        TEXT        NOT NULL REFERENCES roles(name)       ON DELETE CASCADE,
    permission  TEXT        NOT NULL REFERENCES permissions(key)  ON DELETE CASCADE,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role, permission)
);

CREATE INDEX IF NOT EXISTS idx_role_permissions_role
    ON role_permissions (role);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission
    ON role_permissions (permission);

-- super_admin: all permissions
INSERT INTO role_permissions (role, permission)
SELECT 'super_admin', key FROM permissions
ON CONFLICT DO NOTHING;

-- admin: everything except roles.edit
INSERT INTO role_permissions (role, permission)
SELECT 'admin', key FROM permissions
WHERE key NOT IN ('roles.edit')
ON CONFLICT DO NOTHING;

-- moderator: content + own dashboard view
INSERT INTO role_permissions (role, permission)
SELECT 'moderator', key FROM permissions
WHERE key IN (
    'users.view',
    'documents.view', 'documents.create', 'documents.delete', 'documents.rebuild',
    'sources.view',
    'dashboard.view', 'dashboard.logs'
)
ON CONFLICT DO NOTHING;

-- user: minimal dashboard view
INSERT INTO role_permissions (role, permission)
SELECT 'user', key FROM permissions
WHERE key IN ('dashboard.view')
ON CONFLICT DO NOTHING;
