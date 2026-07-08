"""
Notification center — backed by the notifications table (migration 007).

Types:    info | warning | error | security
Priority: 1 = low | 2 = medium | 3 = high (critical)

Public API:
    create_notification(title, message, type_, priority, metadata)  → error | None
    get_unread_count()                                               → int   (cached 15 s)
    list_notifications(unread_only, type_filter, limit)             → (rows, error)
    mark_read(id)      → error | None
    mark_all_read()    → error | None
    delete_notification(id)  → error | None
    clear_all_read()   → error | None
"""
from __future__ import annotations

import logging
import time

import streamlit as st

logger = logging.getLogger(__name__)

_COLS = "id,type,title,message,priority,is_read,created_at,metadata"
_VALID_TYPES = frozenset({"info", "warning", "error", "security"})

# Re-entrancy guard + rate-limit for notify_db_failure
_IN_NOTIFY_DB_FAILURE: bool = False
_LAST_DB_FAILURE_NOTIF: float = 0.0
_DB_FAILURE_COOLDOWN_SECS: float = 60.0


def _db():
    from core.db_logger import _get_client
    return _get_client()


# ── Write ─────────────────────────────────────────────────────────────────────

def create_notification(
    title: str,
    message: str,
    type_: str = "info",
    priority: int = 1,
    metadata: dict | None = None,
) -> str | None:
    """Insert a notification row.  Returns error string or None on success."""
    if type_ not in _VALID_TYPES:
        type_ = "info"
    priority = max(1, min(3, int(priority)))
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("notifications").insert({
            "type":     type_,
            "title":    title[:200],
            "message":  message[:1000],
            "priority": priority,
            "is_read":  False,
            "metadata": metadata or {},
        }).execute()
        get_unread_count.clear()
        return None
    except Exception as exc:
        logger.warning("notifications.create: %s", exc)
        return "Failed to create notification."


# ── Read ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=15)
def get_unread_count() -> int:
    """Return count of unread notifications (cached 15 s).

    Uses PostgREST exact count to avoid fetching all row IDs over the wire.
    """
    try:
        c = _db()
        if c is None:
            return 0
        resp = (
            c.table("notifications")
            .select("id", count="exact")
            .eq("is_read", False)
            .execute()
        )
        return resp.count or 0
    except Exception:
        return 0


def list_notifications(
    unread_only: bool = False,
    type_filter: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], str | None]:
    """Fetch notifications, newest first."""
    try:
        c = _db()
        if c is None:
            return [], "Database not available."
        q = c.table("notifications").select(_COLS)
        if unread_only:
            q = q.eq("is_read", False)
        if type_filter and type_filter in _VALID_TYPES:
            q = q.eq("type", type_filter)
        resp = q.order("created_at", desc=True).limit(limit).execute()
        return resp.data or [], None
    except Exception as exc:
        logger.warning("notifications.list: %s", exc)
        return [], f"{type(exc).__name__}: {exc}"


# ── Mutations ─────────────────────────────────────────────────────────────────

def mark_read(notification_id: int) -> str | None:
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
        get_unread_count.clear()
        return None
    except Exception as exc:
        logger.warning("notifications.mark_read(%s): %s", notification_id, exc)
        return "Failed to mark as read."


def mark_all_read() -> str | None:
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("notifications").update({"is_read": True}).eq("is_read", False).execute()
        get_unread_count.clear()
        return None
    except Exception as exc:
        logger.warning("notifications.mark_all_read: %s", exc)
        return "Failed to mark all read."


def delete_notification(notification_id: int) -> str | None:
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("notifications").delete().eq("id", notification_id).execute()
        get_unread_count.clear()
        return None
    except Exception as exc:
        logger.warning("notifications.delete(%s): %s", notification_id, exc)
        return "Failed to delete notification."


def clear_all_read() -> str | None:
    """Delete all read notifications (housekeeping)."""
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("notifications").delete().eq("is_read", True).execute()
        return None
    except Exception as exc:
        logger.warning("notifications.clear_all_read: %s", exc)
        return "Failed to clear notifications."


# ── Auto-generators ───────────────────────────────────────────────────────────

def notify_failed_logins(username: str, count: int) -> None:
    """Fire a security notification when failure threshold is crossed."""
    if count >= 5:
        try:
            create_notification(
                title="Multiple Failed Login Attempts Detected",
                message=(
                    f"Account '{username}' has had {count} failed login attempts "
                    "in the last 5 minutes. The account is now locked for 15 minutes."
                ),
                type_="security",
                priority=3,
                metadata={"username": username, "failure_count": count},
            )
        except Exception:
            pass


def notify_db_failure(error: str) -> None:
    """Fire an error notification on DB connection failure.

    Rate-limited to one notification per 60 s; re-entrant calls are dropped
    to prevent infinite recursion when the DB is down.
    """
    global _IN_NOTIFY_DB_FAILURE, _LAST_DB_FAILURE_NOTIF
    if _IN_NOTIFY_DB_FAILURE:
        return
    now = time.monotonic()
    if now - _LAST_DB_FAILURE_NOTIF < _DB_FAILURE_COOLDOWN_SECS:
        return
    _IN_NOTIFY_DB_FAILURE = True
    try:
        _LAST_DB_FAILURE_NOTIF = now
        create_notification(
            title="Database Connection Failure",
            message=f"Supabase client could not connect: {error[:200]}",
            type_="error",
            priority=2,
        )
    except Exception:
        pass
    finally:
        _IN_NOTIFY_DB_FAILURE = False
