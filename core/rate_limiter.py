"""
Per-session sliding-window rate limiter.

State is stored in st.session_state, which resets per browser session —
adequate protection for a single-instance Streamlit Cloud deployment.
For a horizontally-scaled deployment, swap this for a shared store
(e.g. Redis) keyed by an authenticated user id.
"""
from __future__ import annotations

import time

import streamlit as st

_STATE_KEY = "_rate_limit_timestamps"


def is_rate_limited(max_requests_per_minute: int) -> bool:
    now = time.time()
    timestamps: list[float] = st.session_state.get(_STATE_KEY, [])
    timestamps = [ts for ts in timestamps if now - ts < 60]

    if len(timestamps) >= max_requests_per_minute:
        st.session_state[_STATE_KEY] = timestamps
        return True

    timestamps.append(now)
    st.session_state[_STATE_KEY] = timestamps
    return False
