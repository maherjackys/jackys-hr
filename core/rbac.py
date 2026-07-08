"""
RBAC permission store — database-backed with local fallback.

Tables (migration 003):
    permissions      : catalog of all available permission definitions
    role_permissions : which permissions each role has
    roles            : role metadata (name, label, level, is_system)

Public API:
    load_session_permissions(role)                     → frozenset[str]
    has_permission(perm)                               → bool
    require_permission(perm)                           → bool
    get_role_permissions(role)                         → frozenset[str]
    get_all_permissions()                              → list[dict]
    get_roles()                                        → list[dict]
    set_role_permissions(role, perms, actor_role)      → error_str | None

Falls back to _FALLBACK_PERMISSIONS when Supabase is unavailable or
migration 003 has not been run yet — the system remains functional.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── All known permission keys ─────────────────────────────────────────────────
_ALL_PERM_KEYS: frozenset[str] = frozenset({
    "users.view", "users.create", "users.edit", "users.delete",
    "users.disable", "users.enable", "users.reset_password",
    "users.force_logout", "users.assign_roles", "users.view_sessions",
    "documents.view", "documents.create", "documents.delete", "documents.rebuild",
    "sources.view", "sources.add", "sources.delete",
    "dashboard.view", "dashboard.logs", "dashboard.debug",
    "dashboard.analytics", "audit.view", "security.view",
    "settings.view", "settings.edit",
    "roles.view", "roles.edit",
    "features.view", "features.edit",
    "api_keys.view", "api_keys.manage",
    "templates.view", "templates.edit",
    "system.health",
    "notifications.view",
})


# ── Permission catalog (fallback when DB not available) ───────────────────────
_PERMISSION_CATALOG: list[dict[str, Any]] = [
    {"key": "users.view",           "category": "User Management",    "label": "View Users",       "sort_order": 10},
    {"key": "users.create",         "category": "User Management",    "label": "Create Users",     "sort_order": 20},
    {"key": "users.edit",           "category": "User Management",    "label": "Edit Users",       "sort_order": 30},
    {"key": "users.delete",         "category": "User Management",    "label": "Delete Users",     "sort_order": 40},
    {"key": "users.disable",        "category": "User Management",    "label": "Disable Users",    "sort_order": 50},
    {"key": "users.enable",         "category": "User Management",    "label": "Enable Users",     "sort_order": 60},
    {"key": "users.reset_password", "category": "User Management",    "label": "Reset Password",   "sort_order": 70},
    {"key": "users.force_logout",   "category": "User Management",    "label": "Force Logout",     "sort_order": 80},
    {"key": "users.assign_roles",   "category": "User Management",    "label": "Assign Roles",     "sort_order": 90},
    {"key": "users.view_sessions",  "category": "User Management",    "label": "View Sessions",    "sort_order": 100},
    {"key": "documents.view",       "category": "Content Management", "label": "View Documents",   "sort_order": 10},
    {"key": "documents.create",     "category": "Content Management", "label": "Upload Documents", "sort_order": 20},
    {"key": "documents.delete",     "category": "Content Management", "label": "Delete Documents", "sort_order": 30},
    {"key": "documents.rebuild",    "category": "Content Management", "label": "Rebuild Index",    "sort_order": 40},
    {"key": "sources.view",         "category": "Sources",            "label": "View Sources",     "sort_order": 10},
    {"key": "sources.add",          "category": "Sources",            "label": "Add Source",       "sort_order": 20},
    {"key": "sources.delete",       "category": "Sources",            "label": "Delete Source",    "sort_order": 30},
    {"key": "dashboard.view",       "category": "Dashboard",          "label": "View Dashboard",     "sort_order": 10},
    {"key": "dashboard.logs",       "category": "Dashboard",          "label": "View Logs",          "sort_order": 20},
    {"key": "dashboard.analytics",  "category": "Dashboard",          "label": "View Analytics",     "sort_order": 25},
    {"key": "audit.view",           "category": "Dashboard",          "label": "View Audit Trail",   "sort_order": 30},
    {"key": "security.view",        "category": "Dashboard",          "label": "View Security Center","sort_order": 35},
    {"key": "dashboard.debug",      "category": "Dashboard",          "label": "View Debug Info",    "sort_order": 40},
    {"key": "settings.view",        "category": "Settings",           "label": "View Settings",    "sort_order": 10},
    {"key": "settings.edit",        "category": "Settings",           "label": "Edit Settings",    "sort_order": 20},
    {"key": "roles.view",           "category": "Roles",              "label": "View Roles",       "sort_order": 10},
    {"key": "roles.edit",           "category": "Roles",              "label": "Edit Permissions", "sort_order": 20},
    {"key": "features.view",        "category": "Feature Flags",      "label": "View Flags",       "sort_order": 10},
    {"key": "features.edit",        "category": "Feature Flags",      "label": "Edit Flags",       "sort_order": 20},
    {"key": "api_keys.view",        "category": "API Keys",           "label": "View API Keys",    "sort_order": 10},
    {"key": "api_keys.manage",      "category": "API Keys",           "label": "Manage API Keys",  "sort_order": 20},
    {"key": "templates.view",       "category": "Email Templates",    "label": "View Templates",   "sort_order": 10},
    {"key": "templates.edit",       "category": "Email Templates",    "label": "Edit Templates",   "sort_order": 20},
    {"key": "system.health",        "category": "System",             "label": "View System Health","sort_order": 10},
    {"key": "notifications.view",   "category": "System",             "label": "View Notifications","sort_order": 20},
]


# ── Default permissions per role (canonical source of truth) ─────────────────
# Used both as the DB fallback and as the target for "Reset to Default".
DEFAULT_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "super_admin": frozenset(_ALL_PERM_KEYS),
    "admin":       frozenset(_ALL_PERM_KEYS - {"roles.edit"}),
    "moderator":   frozenset({
        "users.view",
        "documents.view", "documents.create", "documents.delete", "documents.rebuild",
        "sources.view",
        "dashboard.view", "dashboard.logs", "dashboard.analytics", "audit.view",
        "features.view", "templates.view", "api_keys.view",
        "system.health", "notifications.view",
    }),
    "user":        frozenset({"dashboard.view"}),
}

# Keep the old name as an alias so nothing else breaks
_FALLBACK = DEFAULT_ROLE_PERMISSIONS

_FALLBACK_ROLES: list[dict] = [
    {"name": "super_admin", "label": "Super Admin", "level": 4, "is_system": True},
    {"name": "admin",       "label": "Admin",       "level": 3, "is_system": True},
    {"name": "moderator",   "label": "Moderator",   "level": 2, "is_system": True},
    {"name": "user",        "label": "User",        "level": 1, "is_system": True},
]


def _db():
    from core.db_logger import _get_client
    return _get_client()


import streamlit as st  # noqa: E402  (imported here to allow non-Streamlit usage of constants above)


@st.cache_data(ttl=300)
def get_role_permissions(role: str) -> frozenset[str]:
    """Return the set of permission keys for *role* (cached 5 min).

    Queries role_permissions in Supabase; falls back to _FALLBACK on any error.
    """
    try:
        c = _db()
        if c is None:
            return _FALLBACK.get(role, frozenset())
        resp = (
            c.table("role_permissions")
            .select("permission")
            .eq("role", role)
            .execute()
        )
        if resp.data is None:
            return _FALLBACK.get(role, frozenset())
        return frozenset(r["permission"] for r in resp.data)
    except Exception as exc:
        logger.warning("rbac.get_role_permissions(%s) error: %s — using fallback", role, exc)
        return _FALLBACK.get(role, frozenset())


def load_session_permissions(role: str) -> frozenset[str]:
    """Fetch permissions for *role* and store them in session_state.

    Call this immediately after login and after session restore.
    Returns the loaded frozenset so callers can use it without a second lookup.
    """
    perms = get_role_permissions(role)
    try:
        st.session_state.user_permissions = perms
    except Exception:
        pass
    return perms


def has_permission(perm: str) -> bool:
    """Return True if the current session user has *perm*.

    Reads from st.session_state.user_permissions which is populated by
    load_session_permissions() at login / session restore.
    """
    try:
        perms = st.session_state.get("user_permissions") or frozenset()
        return perm in perms
    except Exception:
        return False


def require_permission(perm: str) -> bool:
    """Render a 403 block and return False when *perm* is missing.

    Returns True immediately when the permission is present.
    Designed for inline tab guards: ``if not require_permission("x"): return``
    """
    if has_permission(perm):
        return True
    try:
        _role = st.session_state.get("admin_role", "unknown")
        st.error(
            f"🚫 **403 Forbidden** — Permission `{perm}` required.  "
            f"Your role **{_role}** does not have this permission."
        )
    except Exception:
        pass
    return False


@st.cache_data(ttl=3600)
def get_all_permissions() -> list[dict]:
    """Return the permission catalog ordered by category + sort_order.

    Queries the permissions table; falls back to _PERMISSION_CATALOG.
    """
    try:
        c = _db()
        if c is None:
            return sorted(_PERMISSION_CATALOG, key=lambda p: (p["category"], p["sort_order"]))
        resp = (
            c.table("permissions")
            .select("key,category,label,sort_order")
            .order("category")
            .order("sort_order")
            .execute()
        )
        if resp.data:
            return resp.data
        return sorted(_PERMISSION_CATALOG, key=lambda p: (p["category"], p["sort_order"]))
    except Exception as exc:
        logger.warning("rbac.get_all_permissions error: %s — using fallback", exc)
        return sorted(_PERMISSION_CATALOG, key=lambda p: (p["category"], p["sort_order"]))


@st.cache_data(ttl=3600)
def get_roles() -> list[dict]:
    """Return all roles ordered by level descending.

    Queries the roles table; falls back to _FALLBACK_ROLES.
    """
    try:
        c = _db()
        if c is None:
            return _FALLBACK_ROLES
        resp = (
            c.table("roles")
            .select("name,label,level,is_system")
            .order("level", desc=True)
            .execute()
        )
        if resp.data:
            return resp.data
        return _FALLBACK_ROLES
    except Exception as exc:
        logger.warning("rbac.get_roles error: %s — using fallback", exc)
        return _FALLBACK_ROLES


def set_role_permissions(
    role: str,
    permissions: list[str],
    actor_role: str,
    actor_permissions: frozenset[str] | None = None,
) -> str | None:
    """Replace all permissions for *role* in the database.

    Security rules enforced here (backend — not just UI):
    - Only super_admin can modify any role's permissions.
    - super_admin permissions are immutable (protected by design).
    - All permission keys must exist in _ALL_PERM_KEYS.
    - Non-super_admin actors cannot grant permissions they don't hold
      (prevents privilege escalation via role editing).

    Returns None on success, error string on failure.
    """
    if actor_role != "super_admin":
        return "Only Super Admin can modify role permissions."
    if role == "super_admin":
        return "Super Admin permissions cannot be modified."
    invalid = [p for p in permissions if p not in _ALL_PERM_KEYS]
    if invalid:
        return f"Unknown permissions: {', '.join(invalid)}"
    # Privilege escalation guard: actor cannot grant perms they don't hold.
    # (Redundant for super_admin since they hold all perms; kept for defence-in-depth.)
    if actor_role != "super_admin" and actor_permissions is not None:
        escalated = [p for p in permissions if p not in actor_permissions]
        if escalated:
            return f"Cannot grant permissions you do not hold: {', '.join(escalated)}"
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("role_permissions").delete().eq("role", role).execute()
        if permissions:
            c.table("role_permissions").upsert(
                [{"role": role, "permission": p} for p in permissions],
                on_conflict="role,permission",
            ).execute()
        return None
    except Exception as exc:
        logger.warning("rbac.set_role_permissions error: %s", exc)
        return f"{type(exc).__name__}: {exc}"
