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
    get_enabled_sources() -> list[str]   — cached 60 s
    set_enabled_sources(sources)         — writes to Supabase, invalidates cache
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import streamlit as st

from config import KnowledgeSource

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ALL_SOURCES: list[str] = list(KnowledgeSource.__args__)  # type: ignore[attr-defined]
_SETTINGS_KEY = "enabled_sources"


# ── Supabase client (reuse db_logger's) ──────────────────────────────────────

def _client():
    from core.db_logger import _get_client
    return _get_client()


# ── Public API ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_enabled_sources() -> list[str]:
    """Return list of enabled source keys. Falls back to all sources on any error."""
    try:
        c = _client()
        if c is None:
            return list(_ALL_SOURCES)
        resp = c.table("app_settings").select("value").eq("key", _SETTINGS_KEY).execute()
        if resp.data:
            val = resp.data[0]["value"]
            if isinstance(val, list) and val:
                # Validate: only keep known sources
                return [s for s in val if s in _ALL_SOURCES] or list(_ALL_SOURCES)
        return list(_ALL_SOURCES)
    except Exception as exc:
        logger.warning("settings_store: get_enabled_sources failed (%s) — returning all.", exc)
        return list(_ALL_SOURCES)


def set_enabled_sources(sources: list[str]) -> str | None:
    """Persist enabled sources. Returns error string or None on success."""
    valid = [s for s in sources if s in _ALL_SOURCES]
    if not valid:
        return "At least one source must be enabled."
    try:
        c = _client()
        if c is None:
            return "Supabase not available — changes not saved."
        c.table("app_settings").upsert(
            {"key": _SETTINGS_KEY, "value": valid},
            on_conflict="key",
        ).execute()
        get_enabled_sources.clear()  # bust cache
        return None
    except Exception as exc:
        logger.warning("settings_store: set_enabled_sources failed (%s).", exc)
        return f"{type(exc).__name__}: {exc}"
