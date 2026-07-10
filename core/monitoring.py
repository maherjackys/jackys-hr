"""
Application monitoring — Sentry integration.

init_sentry() is idempotent and never raises.  Call it once at process
start (app.py) before any st.* calls.  capture(exc, **ctx) records an
exception with optional key/value context, scrubbing secrets.

Dev mode: when SENTRY_DSN is absent, both functions are no-ops and log
at INFO level so local development stays noise-free.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False
_SCRUB_KEYS = frozenset({"password", "secret", "token", "api_key", "authorization"})


def _scrub(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *data* with sensitive keys replaced by '[Filtered]'."""
    return {
        k: "[Filtered]" if any(s in k.lower() for s in _SCRUB_KEYS) else v
        for k, v in data.items()
    }


def _before_send(event: dict, hint: dict) -> dict:  # noqa: ARG001
    """Scrub headers and extra context before sending to Sentry."""
    try:
        if "request" in event and "headers" in event["request"]:
            event["request"]["headers"] = _scrub(event["request"]["headers"])
        if "extra" in event:
            event["extra"] = _scrub(event["extra"])
    except Exception:
        pass
    return event


def init_sentry() -> None:
    """Initialise Sentry once.  Safe to call multiple times."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        dsn = _get_dsn()
        if not dsn:
            logger.info("SENTRY_DSN not set — monitoring disabled (dev mode).")
            _initialized = True
            return
        try:
            import sentry_sdk
            from sentry_sdk.integrations.threading import ThreadingIntegration
            sentry_sdk.init(
                dsn=dsn,
                traces_sample_rate=0.0,
                send_default_pii=False,
                environment=os.environ.get("SENTRY_ENV", "production"),
                before_send=_before_send,
                # Disable threading integration — it wraps Thread.run() in a way
                # that conflicts with Streamlit's add_script_run_ctx on Python 3.14.
                # propagate_hub=False prevents the thread-wrapping that causes:
                # TypeError: _run_with_thread_state() takes 0 positional arguments but 1 was given
                integrations=[ThreadingIntegration(propagate_hub=False)],
                default_integrations=False,
            )
            _initialized = True
            logger.info("Sentry initialised (environment=%s).", os.environ.get("SENTRY_ENV", "production"))
        except Exception as exc:
            logger.warning("Sentry init failed: %s — monitoring disabled.", exc)
            _initialized = True


def capture(exc: BaseException, **ctx: Any) -> None:
    """Capture *exc* in Sentry with optional string context. Never raises."""
    if not _initialized:
        init_sentry()
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in ctx.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def _get_dsn() -> str:
    """Return SENTRY_DSN from st.secrets (preferred) or os.environ."""
    try:
        import streamlit as st
        return st.secrets.get("SENTRY_DSN", "")
    except Exception:
        pass
    return os.environ.get("SENTRY_DSN", "")
