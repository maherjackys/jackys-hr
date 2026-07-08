"""
Feature flag store — backed by app_settings table.

Key format in DB:  feature_flag.{flag_key}
Value (JSONB):     {enabled, description, updated_at, updated_by}

Public API:
    is_feature_enabled(key, default=True)   → bool
    get_feature_flag(key)                   → dict | None
    set_feature_flag(key, enabled, …)       → error_str | None
    list_feature_flags()                    → list[dict]          (cached 30 s)
    delete_feature_flag(key)                → error_str | None
"""
from __future__ import annotations

import datetime
import logging
import re

import streamlit as st

logger = logging.getLogger(__name__)

_KEY_PREFIX = "feature_flag."
_SLUG_RE    = re.compile(r"^[a-z][a-z0-9_]{0,59}$")

# ── Built-in defaults (bootstrapped on first load) ────────────────────────────
_DEFAULT_FLAGS: list[dict] = [
    {"key": "rag_enabled",         "enabled": True,  "description": "Enable RAG document retrieval (disable for LLM-only mode)"},
    {"key": "feedback_enabled",    "enabled": True,  "description": "Allow users to submit thumbs up/down feedback on answers"},
    {"key": "multilingual",        "enabled": True,  "description": "Enable automatic Arabic/English language detection"},
    {"key": "suggestions_enabled", "enabled": True,  "description": "Show suggested questions on the chat interface"},
    {"key": "dark_mode",           "enabled": True,  "description": "Allow users to toggle dark mode in the chat app"},
    {"key": "source_switching",    "enabled": True,  "description": "Allow users to switch knowledge source in the chat app"},
    {"key": "admin_dashboard",     "enabled": True,  "description": "Enable the admin dashboard (disable for maintenance)"},
    {"key": "log_queries",         "enabled": True,  "description": "Log all user queries to Supabase for analytics"},
]


def _db():
    from core.db_logger import _get_client
    return _get_client()


def is_valid_flag_key(key: str) -> bool:
    return bool(_SLUG_RE.match(key))


# ── Core CRUD ─────────────────────────────────────────────────────────────────

def get_feature_flag(key: str) -> dict | None:
    """Return the flag dict for *key* or None if not found."""
    try:
        c = _db()
        if c is None:
            return None
        resp = (
            c.table("app_settings")
            .select("key,value")
            .eq("key", f"{_KEY_PREFIX}{key}")
            .limit(1)
            .execute()
        )
        if resp.data:
            val = resp.data[0]["value"]
            if isinstance(val, dict):
                return {"key": key, **val}
    except Exception as exc:
        logger.warning("feature_flags.get(%s): %s", key, exc)
    return None


def is_feature_enabled(key: str, default: bool = True) -> bool:
    """Return enabled state; returns *default* if flag not found or DB unavailable."""
    flag = get_feature_flag(key)
    return bool(flag.get("enabled", default)) if flag else default


def set_feature_flag(
    key: str,
    enabled: bool,
    description: str = "",
    actor: str = "",
) -> str | None:
    """Create or update a feature flag.  Returns error string or None on success."""
    if not is_valid_flag_key(key):
        return f"Invalid key '{key}'. Use lowercase letters, digits, underscore (a–z start)."
    try:
        c = _db()
        if c is None:
            return "Database not available."
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        existing = get_feature_flag(key)
        desc = description.strip() or (existing.get("description", "") if existing else "")
        value = {
            "enabled":     enabled,
            "description": desc[:500],
            "updated_at":  now,
            "updated_by":  actor[:100],
        }
        c.table("app_settings").upsert(
            {"key": f"{_KEY_PREFIX}{key}", "value": value},
            on_conflict="key",
        ).execute()
        list_feature_flags.clear()
        return None
    except Exception as exc:
        logger.warning("feature_flags.set(%s): %s", key, exc)
        return "Failed to save flag. Check server logs."


def delete_feature_flag(key: str) -> str | None:
    """Remove a feature flag from the DB.  Returns error string or None."""
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("app_settings").delete().eq("key", f"{_KEY_PREFIX}{key}").execute()
        list_feature_flags.clear()
        return None
    except Exception as exc:
        logger.warning("feature_flags.delete(%s): %s", key, exc)
        return "Failed to delete flag. Check server logs."


@st.cache_data(ttl=30)
def list_feature_flags() -> list[dict]:
    """Return all feature flags; bootstraps defaults on first call."""
    try:
        c = _db()
        if c is None:
            return _fallback_defaults()
        resp = (
            c.table("app_settings")
            .select("key,value")
            .like("key", f"{_KEY_PREFIX}%")
            .order("key")
            .execute()
        )
        rows = resp.data or []
        if not rows:
            _bootstrap_defaults()
            # Re-query so we return the actual DB-written rows, not in-memory statics
            resp2 = (
                c.table("app_settings")
                .select("key,value")
                .like("key", f"{_KEY_PREFIX}%")
                .order("key")
                .execute()
            )
            rows = resp2.data or []
            if not rows:
                return _fallback_defaults()
        flags = []
        for row in rows:
            flag_key = row["key"][len(_KEY_PREFIX):]
            val = row["value"] or {}
            flags.append({"key": flag_key, **val})
        return flags
    except Exception as exc:
        logger.warning("feature_flags.list: %s", exc)
        return _fallback_defaults()


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def _fallback_defaults() -> list[dict]:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return [
        {**f, "updated_at": now, "updated_by": "system"}
        for f in _DEFAULT_FLAGS
    ]


def _bootstrap_defaults() -> None:
    """Insert default flags if none exist yet (idempotent)."""
    try:
        c = _db()
        if c is None:
            return
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rows = [
            {
                "key": f"{_KEY_PREFIX}{f['key']}",
                "value": {
                    "enabled":     f["enabled"],
                    "description": f["description"],
                    "updated_at":  now,
                    "updated_by":  "system",
                },
            }
            for f in _DEFAULT_FLAGS
        ]
        c.table("app_settings").upsert(rows, on_conflict="key").execute()
        logger.info("feature_flags: bootstrapped %d defaults", len(rows))
    except Exception as exc:
        logger.warning("feature_flags._bootstrap: %s", exc)
