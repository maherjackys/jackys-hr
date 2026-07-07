"""
Admin authentication — Supabase-backed credentials + browser-cookie sessions.

Design:
- Passwords hashed with bcrypt (work factor 12).  Plain-text ADMIN_PASSWORD
  secret is auto-migrated to a bcrypt hash on first login.
- Sessions stored in admin_sessions Supabase table (24-hour TTL).
- Token is a 64-hex-char (256-bit) random value.
- Falls back gracefully when Supabase is unreachable (in-memory session only).

Roles (lowest → highest):  user → moderator → admin → super_admin
  - super_admin : full access; can manage any other account.
  - admin       : content management; can manage moderator/user accounts.
  - moderator   : logs + docs; no source management or user management.
  - user        : read-only dashboard stats.

Public API:
    check_login(password, username="admin")                → (ok: bool, error: str)
    create_session(username, ttl_hours=24)                 → token: str
    verify_session(token)                                  → username | None
    invalidate_session(token)                              → None
    update_password(username, new_password)                → error_str | None
    bootstrap_admin_user()                                 → None  (idempotent)
    cleanup_expired_sessions()                             → None  (housekeeping)
    validate_new_password(pw, confirm)                     → error_str | None

    get_user_role(username)                                → str
    get_all_users()                                        → list[dict]
    create_admin_user(username, password, role, …)         → error_str | None
    update_admin_user(username, **fields)                  → error_str | None
    delete_admin_user(username)                            → error_str | None
    force_logout_user(username)                            → error_str | None
    get_user_sessions(username)                            → list[dict]
    can_manage_user(actor_role, target_role)               → bool
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_SESSION_TTL_HOURS   = 24
_MIN_PASSWORD_LEN    = 8
_MAX_LOGIN_ATTEMPTS  = 5    # lockout after this many failures per window
_LOCKOUT_WINDOW_SECS = 300  # 5-minute sliding window
_LOCKOUT_SECS        = 900  # 15-minute lockout

# In-process store: username → list of failure timestamps
_login_failures: dict[str, list[float]] = {}

VALID_ROLES = ("super_admin", "admin", "moderator", "user")
_ROLE_LEVEL = {"super_admin": 4, "admin": 3, "moderator": 2, "user": 1}


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


# ── Role helpers ──────────────────────────────────────────────────────────────

def can_manage_user(actor_role: str, target_role: str) -> bool:
    """Return True when an actor with *actor_role* may manage a *target_role* account."""
    return _ROLE_LEVEL.get(actor_role, 0) > _ROLE_LEVEL.get(target_role, 0)


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

def create_session(username: str, ttl_hours: int = _SESSION_TTL_HOURS) -> str:
    """Insert a session row in admin_sessions, return the 64-hex token.

    Pass ttl_hours=720 (30 days) when the user ticks "Remember me".
    """
    token   = secrets.token_hex(32)   # 256-bit
    expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
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
    """Fetch the admin_users row (includes role, is_active) or None."""
    try:
        c = _db()
        if c is None:
            return None
        resp = (
            c.table("admin_users")
            .select("username,password_hash,role,is_active")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as exc:
        logger.warning("auth.get_admin_user error: %s", exc)
    return None


def get_user_role(username: str) -> str:
    """Return the role for *username* from the DB.

    Falls back to 'user' (least-privilege) when the DB is unavailable,
    preventing a Supabase outage from silently granting elevated roles.
    The bootstrap 'admin' account keeps super_admin only when the DB is
    reachable and that role is stored there.
    """
    try:
        c = _db()
        if c is None:
            logger.warning("auth.get_user_role: DB unavailable — defaulting to 'user' for %s", username)
            return "user"
        resp = (
            c.table("admin_users")
            .select("role")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        if resp.data:
            role = resp.data[0].get("role")
            if role in VALID_ROLES:
                return role
    except Exception as exc:
        logger.warning("auth.get_user_role error: %s", exc)
    return "user"


def get_all_users() -> list[dict]:
    """Return all admin_users rows (password_hash excluded), ordered by created_at."""
    try:
        c = _db()
        if c is None:
            return []
        try:
            resp = (
                c.table("admin_users")
                .select(
                    "username,role,is_active,email,display_name,"
                    "created_at,updated_at,last_login_at"
                )
                .order("created_at", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception:
            # Pre-migration fallback: new columns may not exist yet
            resp = (
                c.table("admin_users")
                .select("username,created_at")
                .order("created_at", desc=False)
                .execute()
            )
            return [
                {
                    "username":   r["username"],
                    "role":       "super_admin" if r["username"] == "admin" else "admin",
                    "is_active":  True,
                    "created_at": r.get("created_at"),
                }
                for r in (resp.data or [])
            ]
    except Exception as exc:
        logger.warning("auth.get_all_users error: %s", exc)
        return []


def create_admin_user(
    username: str,
    password: str,
    role: str = "admin",
    email: str = "",
    display_name: str = "",
) -> str | None:
    """Insert a new admin_users row.  Returns None on success, error string on failure."""
    if not username or not password:
        return "Username and password are required."
    if role not in VALID_ROLES:
        return f"Invalid role '{role}'. Must be one of: {', '.join(VALID_ROLES)}."
    try:
        c = _db()
        if c is None:
            return "Database not available."
        if get_admin_user(username):
            return f"Username '{username}' already exists."
        c.table("admin_users").insert({
            "username":      username,
            "password_hash": hash_password(password),
            "role":          role,
            "is_active":     True,
            "email":         email or None,
            "display_name":  display_name or None,
        }).execute()
        return None
    except Exception as exc:
        logger.warning("auth.create_admin_user error: %s", exc)
        return "Failed to create user. Check server logs for details."


def update_admin_user(username: str, **fields) -> str | None:
    """Update non-password fields on an admin_users row.

    Allowed fields: role, is_active, email, display_name.
    Returns None on success, error string on failure.
    """
    allowed = {"role", "is_active", "email", "display_name"}
    update_data: dict = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("email", "display_name") and v == "":
            v = None
        update_data[k] = v

    if not update_data:
        return None
    if "role" in update_data and update_data["role"] not in VALID_ROLES:
        return f"Invalid role '{update_data['role']}'."
    try:
        c = _db()
        if c is None:
            return "Database not available."
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        c.table("admin_users").update(update_data).eq("username", username).execute()
        return None
    except Exception as exc:
        logger.warning("auth.update_admin_user error: %s", exc)
        return "Failed to update user. Check server logs for details."


def delete_admin_user(username: str) -> str | None:
    """Delete an admin_users row and all its sessions.  Returns None on success."""
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("admin_sessions").delete().eq("username", username).execute()
        c.table("admin_users").delete().eq("username", username).execute()
        return None
    except Exception as exc:
        logger.warning("auth.delete_admin_user error: %s", exc)
        return "Failed to delete user. Check server logs for details."


def force_logout_user(username: str) -> str | None:
    """Delete all sessions for *username* (forces re-login).  Returns None on success."""
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("admin_sessions").delete().eq("username", username).execute()
        return None
    except Exception as exc:
        logger.warning("auth.force_logout_user error: %s", exc)
        return "Failed to revoke sessions. Check server logs for details."


def get_user_sessions(username: str) -> list[dict]:
    """Return all non-expired sessions for *username*, newest first."""
    try:
        c = _db()
        if c is None:
            return []
        now = datetime.now(timezone.utc).isoformat()
        resp = (
            c.table("admin_sessions")
            .select("id,username,created_at,expires_at")
            .eq("username", username)
            .gt("expires_at", now)
            .order("created_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.warning("auth.get_user_sessions error: %s", exc)
        return []


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
            {
                "username":      "admin",
                "password_hash": hash_password(plain),
                "role":          "super_admin",
                "is_active":     True,
            },
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
        return "Failed to update password. Check server logs for details."


def _update_last_login(username: str) -> None:
    """Record timestamp of a successful login.  Non-critical; never raises."""
    try:
        c = _db()
        if c:
            c.table("admin_users").update({
                "last_login_at": datetime.now(timezone.utc).isoformat(),
            }).eq("username", username).execute()
    except Exception:
        pass


# ── Login rate limiting ───────────────────────────────────────────────────────

def _record_failure(username: str) -> None:
    now = time.monotonic()
    failures = _login_failures.get(username, [])
    failures = [t for t in failures if now - t < _LOCKOUT_WINDOW_SECS]
    failures.append(now)
    _login_failures[username] = failures


def _is_locked_out(username: str) -> tuple[bool, int]:
    """Return (locked, seconds_remaining). Cleans up stale entries."""
    now = time.monotonic()
    failures = _login_failures.get(username, [])
    # Keep only failures within the window
    failures = [t for t in failures if now - t < _LOCKOUT_WINDOW_SECS]
    _login_failures[username] = failures
    if len(failures) >= _MAX_LOGIN_ATTEMPTS:
        oldest = min(failures)
        remaining = int(_LOCKOUT_SECS - (now - oldest))
        if remaining > 0:
            return True, remaining
        # Lockout expired — clear and allow
        _login_failures[username] = []
    return False, 0


def _clear_failures(username: str) -> None:
    _login_failures.pop(username, None)


# ── Login verification ────────────────────────────────────────────────────────

def check_login(password: str, username: str = "admin") -> tuple[bool, str]:
    """Verify credentials.  Returns (ok, error_message).

    Priority:
    1. DB bcrypt hash  (post-migration)
    2. Plain ADMIN_PASSWORD secret (legacy) — auto-migrates on success.

    Also checks is_active and records last_login_at on success.
    """
    # Check lockout before doing any work
    locked, secs_left = _is_locked_out(username)
    if locked:
        mins = (secs_left + 59) // 60
        return False, f"Too many failed attempts. Please try again in {mins} minute(s)."

    # 1. Try DB
    user = get_admin_user(username)
    if user:
        if user.get("is_active") is False:
            return False, "Account is disabled. Contact your administrator."
        if verify_password(password, user["password_hash"]):
            _clear_failures(username)
            _update_last_login(username)
            _log_login(username, True)
            return True, ""
        _record_failure(username)
        _log_login(username, False)
        return False, "Incorrect username or password."

    # 2. Fallback: plain-text secret
    correct = _get_secret("ADMIN_PASSWORD")
    if not correct:
        return False, "No credentials configured (set ADMIN_PASSWORD or create admin_users row)."

    if secrets.compare_digest(password.encode("utf-8"), correct.encode("utf-8")):
        _auto_migrate(username, password)
        _clear_failures(username)
        _update_last_login(username)
        _log_login(username, True)
        return True, ""

    _record_failure(username)
    _log_login(username, False)
    return False, "Incorrect username or password."


def _log_login(username: str, success: bool) -> None:
    """Fire-and-forget login attempt log — never raises."""
    try:
        from core.db_logger import log_login_attempt
        log_login_attempt(username, success)
    except Exception:
        pass


def _auto_migrate(username: str, plain: str) -> None:
    """Store bcrypt hash in DB after a successful plain-text login."""
    try:
        c = _db()
        if c:
            c.table("admin_users").upsert(
                {
                    "username":      username,
                    "password_hash": hash_password(plain),
                    "role":          "super_admin",
                    "is_active":     True,
                },
                on_conflict="username",
            ).execute()
            logger.info("auth: auto-migrated %s to bcrypt hash.", username)
    except Exception:
        pass
