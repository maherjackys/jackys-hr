"""
Supabase-backed app settings with in-process cache.

Table schema (run once in Supabase SQL editor):
    CREATE TABLE IF NOT EXISTS app_settings (
        key   TEXT PRIMARY KEY,
        value JSONB NOT NULL
    );
    INSERT INTO app_settings (key, value)
    VALUES ('enabled_sources', '["company", "dubai_hr"]'::jsonb)
    ON CONFLICT DO NOTHING;

Functions:
    get_enabled_sources() -> list[str]       — cached 60 s
    set_enabled_sources(sources)             — writes to Supabase, invalidates cache
    register_source(key)                     — appends new source key, idempotent
    is_valid_source_key(key)                 — slug validation (lowercase, alnum, _)
    get_password_protection_enabled() -> bool — cached 30 s; default True
    set_password_protection_enabled(enabled) — writes to Supabase, invalidates cache
"""
from __future__ import annotations

import logging
import re

import streamlit as st

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "enabled_sources"
_FALLBACK_SOURCES = ["company", "dubai_hr"]
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def is_valid_source_key(key: str) -> bool:
    """Return True when *key* is a valid source slug: lowercase, alphanumeric + underscore."""
    return bool(_SLUG_RE.match(key))


# ── Supabase client (reuse db_logger's) ──────────────────────────────────────

def _client():
    from core.db_logger import _get_client
    return _get_client()


# ── Public API ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_enabled_sources() -> list[str]:
    """Return list of enabled source keys from Supabase, or fallback on any error.

    No longer filters against a hardcoded allowlist — new sources registered
    via register_source() will appear here.
    """
    try:
        c = _client()
        if c is None:
            return list(_FALLBACK_SOURCES)
        resp = c.table("app_settings").select("value").eq("key", _SETTINGS_KEY).execute()
        if resp.data:
            val = resp.data[0]["value"]
            if isinstance(val, list) and val:
                # Re-validate each slug against the same regex used at write time
                valid = [s for s in val if isinstance(s, str) and is_valid_source_key(s)]
                if valid:
                    return valid
        return list(_FALLBACK_SOURCES)
    except Exception as exc:
        logger.warning("settings_store: get_enabled_sources failed (%s) — returning fallback.", exc)
        return list(_FALLBACK_SOURCES)


def set_enabled_sources(sources: list[str]) -> str | None:
    """Persist enabled sources. Returns error string or None on success."""
    valid = [s for s in sources if isinstance(s, str) and is_valid_source_key(s)]
    if not valid:
        return "At least one valid source must be enabled."
    try:
        c = _client()
        if c is None:
            return "Supabase not available — changes not saved."
        c.table("app_settings").upsert(
            {"key": _SETTINGS_KEY, "value": valid},
            on_conflict="key",
        ).execute()
        get_enabled_sources.clear()
        return None
    except Exception as exc:
        logger.warning("settings_store: set_enabled_sources failed (%s).", exc)
        return "Failed to save settings. Check server logs for details."


_PW_PROTECTION_KEY = "password_protection_enabled"


@st.cache_data(ttl=30)
def get_password_protection_enabled() -> bool:
    """Return whether the employee app password gate is active.

    Defaults to True (safe) when the setting is absent or Supabase is unavailable.
    """
    try:
        c = _client()
        if c is None:
            return True
        resp = c.table("app_settings").select("value").eq("key", _PW_PROTECTION_KEY).execute()
        if resp.data:
            val = resp.data[0]["value"]
            if isinstance(val, bool):
                return val
        return True
    except Exception as exc:
        logger.warning("settings_store: get_password_protection_enabled failed (%s).", exc)
        return True


def set_password_protection_enabled(enabled: bool) -> str | None:
    """Persist the password-protection toggle. Returns error string or None on success."""
    try:
        c = _client()
        if c is None:
            return "Supabase not available — changes not saved."
        c.table("app_settings").upsert(
            {"key": _PW_PROTECTION_KEY, "value": enabled},
            on_conflict="key",
        ).execute()
        get_password_protection_enabled.clear()
        return None
    except Exception as exc:
        logger.warning("settings_store: set_password_protection_enabled failed (%s).", exc)
        return "Failed to save settings. Check server logs."


def register_source(key: str) -> str | None:
    """Append *key* to enabled_sources in Supabase (idempotent).

    Returns None on success, error string on failure.
    """
    if not is_valid_source_key(key):
        return f"Invalid source key '{key}'. Use lowercase letters, digits, and underscores only."
    try:
        current = get_enabled_sources()
        if key in current:
            return None  # already registered — not an error
        return set_enabled_sources(current + [key])
    except Exception as exc:
        logger.warning("settings_store: register_source failed (%s).", exc)
        return "Failed to register source. Check server logs for details."
