"""
Cross-session rate limiter — Supabase-primary, in-memory fallback.

Public API
----------
is_rate_limited(max_requests_per_minute) -> bool
    True  → caller is over the limit; do NOT serve the request.
    False → caller is within the limit; request was recorded.

Client key
----------
Priority: X-Forwarded-For first hop → X-Real-Ip header → Streamlit
session-id → "anon:unknown".  IP keys are prefixed "ip:", session keys
"sess:" so they can never collide.

Stores
------
Primary: Supabase `rate_limit_hits` table (migration 009).
Fallback: module-level dict guarded by threading.Lock, capped at 5 000
keys.  Used only when the DB raises; logs a WARNING.

Fail-open: if both paths fail the request is allowed so a monitoring
outage never becomes a DoS against our own users.

A new browser tab or page refresh does NOT reset the limit because the
key is IP- or session-based, not widget-state-based.
"""
from __future__ import annotations

import logging
import time
import threading
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

# ── In-memory fallback store ──────────────────────────────────────────────────
_mem_lock  = threading.Lock()
_mem_store: dict[str, deque] = {}   # key → deque of epoch-float timestamps
_MEM_KEY_CAP = 5_000

# ── Opportunistic DB pruning throttle ────────────────────────────────────────
_prune_lock        = threading.Lock()
_last_prune: float = 0.0
_PRUNE_INTERVAL    = 300.0   # seconds (5 minutes)


def _client_key() -> str:
    """Resolve a stable, session-or-IP-scoped key for the current request."""
    try:
        import streamlit as st
        headers = st.context.headers
        fwd = headers.get("X-Forwarded-For", "")
        if fwd:
            return "ip:" + fwd.split(",")[0].strip()
        real_ip = headers.get("X-Real-Ip", "")
        if real_ip:
            return "ip:" + real_ip.strip()
    except Exception:
        pass
    try:
        import streamlit as st
        sid = st.session_state.get("_session_id")
        if not sid:
            import uuid
            sid = uuid.uuid4().hex
            st.session_state["_session_id"] = sid
        return "sess:" + sid
    except Exception:
        pass
    return "anon:unknown"


def _db_check_and_record(key: str, window_secs: int, limit: int) -> Optional[bool]:
    """
    Check the DB count for *key* in the last *window_secs* seconds.
    If count >= limit → return True (rate limited, do NOT insert).
    Else insert a row and return False (allowed).
    Returns None on any DB error so the caller can fall back.
    """
    try:
        from core.db_logger import _get_client
        client = _get_client()
        if client is None:
            return None

        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_secs)).isoformat()

        resp = (
            client.table("rate_limit_hits")
            .select("id", count="exact")
            .eq("key", key)
            .gt("ts", cutoff)
            .execute()
        )
        count = resp.count if resp.count is not None else 0

        if count >= limit:
            return True   # over limit

        client.table("rate_limit_hits").insert({"key": key}).execute()

        # Opportunistic pruning (once per process per _PRUNE_INTERVAL)
        global _last_prune
        now = time.monotonic()
        if now - _last_prune > _PRUNE_INTERVAL:
            with _prune_lock:
                if now - _last_prune > _PRUNE_INTERVAL:
                    _last_prune = now
                    try:
                        from datetime import datetime, timezone, timedelta
                        old_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
                        client.table("rate_limit_hits").delete().lt("ts", old_cutoff).execute()
                    except Exception:
                        pass

        return False   # allowed
    except Exception as exc:
        logger.warning("rate_limiter: DB path failed (%s: %s) — using memory fallback.",
                       type(exc).__name__, exc)
        return None


def _mem_check_and_record(key: str, window_secs: int, limit: int) -> bool:
    """In-memory sliding-window rate check.  Always returns a bool."""
    now = time.monotonic()
    cutoff = now - window_secs
    with _mem_lock:
        if key not in _mem_store:
            if len(_mem_store) >= _MEM_KEY_CAP:
                # Evict oldest key (first inserted — dict preserves order in Python 3.7+)
                _mem_store.pop(next(iter(_mem_store)))
            _mem_store[key] = deque()
        dq = _mem_store[key]
        # Prune old entries
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            return True   # over limit
        dq.append(now)
        return False      # allowed


def is_rate_limited(max_requests_per_minute: int = 20) -> bool:
    """
    Return True if the current client has exceeded *max_requests_per_minute*
    within the last 60 seconds.  Fail-open: returns False if monitoring fails.
    """
    key = _client_key()
    try:
        db_result = _db_check_and_record(key, window_secs=60, limit=max_requests_per_minute)
        if db_result is not None:
            return db_result
        # DB unavailable — use memory fallback
        return _mem_check_and_record(key, window_secs=60, limit=max_requests_per_minute)
    except Exception as exc:
        logger.error("rate_limiter: both paths failed (%s) — failing open.", exc)
        return False   # fail-open: monitoring outage must not block users
