"""
Centralized RBAC permission middleware for the Admin Dashboard.

This module provides both role-level checks (has_role / require_role) and
fine-grained permission checks (has_permission / require_permission) backed
by the role_permissions Supabase table (migration 003).

Usage:
    from core.permissions import has_role, require_role
    from core.permissions import has_permission, require_permission

    if has_role("admin"):              ...  # role-level hierarchy check
    if has_permission("users.create"): ...  # DB-backed permission check
"""
from __future__ import annotations

from core.auth import _ROLE_LEVEL
from core.rbac import (  # noqa: F401  (re-exported for convenience)
    has_permission,
    require_permission,
    load_session_permissions,
)

_ROLE_LABELS = {
    "super_admin": "Super Admin",
    "admin":       "Admin",
    "moderator":   "Moderator",
    "user":        "User",
}


def current_role() -> str:
    """Return the current admin user's role. Defaults to 'user' when unset."""
    try:
        import streamlit as st
        return st.session_state.get("admin_role") or "user"
    except Exception:
        return "user"


def has_role(min_role: str) -> bool:
    """Return True if the current user meets or exceeds *min_role*."""
    return _ROLE_LEVEL.get(current_role(), 0) >= _ROLE_LEVEL.get(min_role, 0)


def require_role(min_role: str) -> bool:
    """Render a 403 block and return False if the role requirement is not met."""
    if has_role(min_role):
        return True
    try:
        import streamlit as st
        _role = current_role()
        _label = _ROLE_LABELS.get(min_role, min_role.replace("_", " ").title())
        _cur_label = _ROLE_LABELS.get(_role, _role.replace("_", " ").title())
        st.error(
            f"🚫 **403 Access Denied**\n\n"
            f"This section requires **{_label}** or higher.  "
            f"Your current role: **{_cur_label}**."
        )
    except Exception:
        pass
    return False


# Alias — more readable in guard contexts
guard = require_role
