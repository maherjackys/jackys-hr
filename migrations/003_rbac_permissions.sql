-- ============================================================
-- Migration 003: RBAC Permissions System
-- Run once in the Supabase SQL Editor.
-- All statements are idempotent (safe to re-run).
-- ============================================================

-- 1. roles — metadata table for all roles (built-in + future custom)
CREATE TABLE IF NOT EXISTS roles (
    name        TEXT PRIMARY KEY,
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


-- 2. permissions — catalog of all available permission keys
CREATE TABLE IF NOT EXISTS permissions (
    key         TEXT PRIMARY KEY,
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


-- 3. role_permissions — maps each role to its set of permissions
CREATE TABLE IF NOT EXISTS role_permissions (
    role        TEXT        NOT NULL REFERENCES roles(name)       ON DELETE CASCADE,
    permission  TEXT        NOT NULL REFERENCES permissions(key)  ON DELETE CASCADE,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role, permission)
);

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


-- 4. Performance indexes
CREATE INDEX IF NOT EXISTS idx_role_permissions_role
    ON role_permissions (role);

CREATE INDEX IF NOT EXISTS idx_role_permissions_permission
    ON role_permissions (permission);
