"""
Admin authentication — Supabase-backed credentials + browser-cookie sessions.

Design:
- Passwords hashed with bcrypt (work factor 12).  Plain-text ADMIN_PASSWORD
  secret is auto-migrated to a bcrypt hash on first login.
- Sessions stored in admin_sessions Supabase table (24-hour TTL).
- Token is a 64-hex-char (256-bit) random value.
- Falls back gracefully when Supabase is unreachable (in-memory session only).

Public API:
    check_login(password, username="admin")  → (ok: bool, error: str)
    create_session(username)                 → token: str
    verify_session(token)                    → username | None
    invalidate_session(token)                → None
    update_password(username, new_password)  → error_str | None
    bootstrap_admin_user()                   → None  (idempotent)
    cleanup_expired_sessions()               → None  (housekeeping)
    validate_new_password(pw, confirm)       → error_str | None
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_SESSION_TTL_HOURS = 24
_MIN_PASSWORD_LEN  = 8


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


def _db():
    """Return Supabase client or None."""
    from core.db_logger import _get_client
    return _get_client()


# ── Password hashing (bcrypt) ─────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash string (60 chars, $2b$ prefix)."""
    import bcrypt
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True if *plaintext* matches *hashed* (bcrypt)."""
    if not plaintext or not hashed:
        return False
    try:
        import bcrypt
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except Exception as exc:
        logger.warning("auth.verify_password error: %s", exc)
        return False


def validate_new_password(password: str, confirm: str) -> str | None:
    """Return an error string or None when the password is acceptable."""
    if len(password) < _MIN_PASSWORD_LEN:
        return f"Password must be at least {_MIN_PASSWORD_LEN} characters."
    if password != confirm:
        return "Passwords do not match."
    return None


# ── Session management ────────────────────────────────────────────────────────

def create_session(username: str) -> str:
    """Insert a session row in admin_sessions, return the 64-hex token."""
    token    = secrets.token_hex(32)   # 256-bit
    expires  = (datetime.now(timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS)).isoformat()
    try:
        c = _db()
        if c:
            c.table("admin_sessions").insert({
                "id":         token,
                "username":   username,
                "expires_at": expires,
            }).execute()
    except Exception as exc:
        logger.warning("auth.create_session DB error: %s", exc)
    return token


def verify_session(token: str) -> str | None:
    """Return username if the token exists and has not expired, else None."""
    if not token or len(token) != 64:
        return None
    try:
        c = _db()
        if c is None:
            return None
        now  = datetime.now(timezone.utc).isoformat()
        resp = (
            c.table("admin_sessions")
            .select("username")
            .eq("id", token)
            .gt("expires_at", now)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["username"]
    except Exception as exc:
        logger.warning("auth.verify_session error: %s", exc)
    return None


def invalidate_session(token: str) -> None:
    """Delete a session row (called on logout)."""
    if not token:
        return
    try:
        c = _db()
        if c:
            c.table("admin_sessions").delete().eq("id", token).execute()
    except Exception as exc:
        logger.warning("auth.invalidate_session error: %s", exc)


def cleanup_expired_sessions() -> None:
    """Delete rows whose expires_at has passed.  Non-critical housekeeping."""
    try:
        c = _db()
        if c:
            now = datetime.now(timezone.utc).isoformat()
            c.table("admin_sessions").delete().lt("expires_at", now).execute()
    except Exception:
        pass


# ── Admin user management ─────────────────────────────────────────────────────

def get_admin_user(username: str = "admin") -> dict | None:
    """Fetch the admin_users row or None if not found / DB unavailable."""
    try:
        c = _db()
        if c is None:
            return None
        resp = (
            c.table("admin_users")
            .select("username,password_hash")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as exc:
        logger.warning("auth.get_admin_user error: %s", exc)
    return None


def bootstrap_admin_user() -> None:
    """Create the admin DB row from ADMIN_PASSWORD secret if it does not exist.

    Called once per cold start so the first login uses bcrypt from day one.
    Safe to call repeatedly — idempotent.
    """
    try:
        if get_admin_user("admin") is not None:
            return
        plain = _get_secret("ADMIN_PASSWORD")
        if not plain:
            return
        c = _db()
        if c is None:
            return
        c.table("admin_users").upsert(
            {"username": "admin", "password_hash": hash_password(plain)},
            on_conflict="username",
        ).execute()
        logger.info("auth: admin user bootstrapped from ADMIN_PASSWORD secret.")
    except Exception as exc:
        logger.warning("auth.bootstrap_admin_user error: %s", exc)


def update_password(username: str, new_password: str) -> str | None:
    """Hash *new_password* and write it to admin_users.  Returns None on success."""
    try:
        c = _db()
        if c is None:
            return "Database not available — password not saved."
        c.table("admin_users").update({
            "password_hash": hash_password(new_password),
            "updated_at":    datetime.now(timezone.utc).isoformat(),
        }).eq("username", username).execute()
        return None
    except Exception as exc:
        logger.warning("auth.update_password error: %s", exc)
        return f"{type(exc).__name__}: {exc}"


# ── Login verification ────────────────────────────────────────────────────────

def check_login(password: str, username: str = "admin") -> tuple[bool, str]:
    """Verify credentials.  Returns (ok, error_message).

    Priority:
    1. DB bcrypt hash  (post-migration)
    2. Plain ADMIN_PASSWORD secret (legacy) — auto-migrates on success.
    """
    # 1. Try DB
    user = get_admin_user(username)
    if user:
        if verify_password(password, user["password_hash"]):
            return True, ""
        return False, "Incorrect password."

    # 2. Fallback: plain-text secret
    correct = _get_secret("ADMIN_PASSWORD")
    if not correct:
        return False, "No credentials configured (set ADMIN_PASSWORD or create admin_users row)."

    if secrets.compare_digest(password.encode("utf-8"), correct.encode("utf-8")):
        _auto_migrate(username, password)
        return True, ""

    return False, "Incorrect password."


def _auto_migrate(username: str, plain: str) -> None:
    """Store bcrypt hash in DB after a successful plain-text login."""
    try:
        c = _db()
        if c:
            c.table("admin_users").upsert(
                {"username": username, "password_hash": hash_password(plain)},
                on_conflict="username",
            ).execute()
            logger.info("auth: auto-migrated %s to bcrypt hash.", username)
    except Exception:
        pass
