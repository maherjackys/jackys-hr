"""
Centralized RBAC permission middleware for the Admin Dashboard.

Never duplicate role checks — import from here.

Roles (lowest → highest):
    user (1) → moderator (2) → admin (3) → super_admin (4)

Usage:
    from core.permissions import has_role, require_role, current_role

    # Silently check
    if has_role("admin"):
        do_something()

    # Show 403 and return False if denied (use inside a tab body)
    if not require_role("admin"):
        st.stop()   # or just return — st.stop() exits the whole script

    # Get current role
    role = current_role()
"""
from __future__ import annotations

from core.auth import _ROLE_LEVEL

_ROLE_LABELS = {
    "super_admin": "Super Admin",
    "admin":       "Admin",
    "moderator":   "Moderator",
    "user":        "User",
}


def current_role() -> str:
    """Return the current admin user's role from Streamlit session_state.

    Returns 'user' (lowest privilege) when the role is not set — safe default.
    """
    try:
        import streamlit as st
        return st.session_state.get("admin_role") or "user"
    except Exception:
        return "user"


def has_role(min_role: str) -> bool:
    """Return True if the current user meets or exceeds *min_role*."""
    return _ROLE_LEVEL.get(current_role(), 0) >= _ROLE_LEVEL.get(min_role, 0)


def require_role(min_role: str) -> bool:
    """Render a 403 Access Denied block and return False if permission denied.

    Returns True when the current user meets the requirement.
    Call at the top of any tab section or action block.

    Example:
        with tab_settings:
            if not require_role("admin"):
                pass  # 403 already shown — nothing else will render
            else:
                # ... tab content
    """
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


# Alias — more readable in `with` contexts
guard = require_role
