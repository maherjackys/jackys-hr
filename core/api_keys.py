"""
API Key management — secure generation, sha-256 hashed storage.

Table: api_keys  (migration 006)
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid()
  name         TEXT NOT NULL
  key_hash     TEXT NOT NULL UNIQUE   -- sha256(raw_key) hex digest
  key_prefix   TEXT NOT NULL          -- first 8 chars only (for display)
  created_at   TIMESTAMPTZ DEFAULT NOW()
  created_by   TEXT NOT NULL
  last_used_at TIMESTAMPTZ
  status       TEXT DEFAULT 'active'  -- 'active' | 'revoked' | 'disabled'
  permissions  JSONB DEFAULT '[]'

Security contract:
  - Only the sha256 hash is stored; the raw key is returned ONCE on generation.
  - Callers MUST display and let the user copy the key immediately.
  - The key is never retrievable again from the server.
  - Format: hr_<40 hex chars>  (prefix makes keys identifiable in logs)
"""
from __future__ import annotations

import datetime
import hashlib
import logging
import secrets

logger = logging.getLogger(__name__)

# Explicit column list — never SELECT *  (RLS-compatible)
_COLS = "id,name,key_prefix,created_at,created_by,last_used_at,status,permissions"


def _db():
    from core.db_logger import _get_client
    return _get_client()


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────

def generate_api_key(
    name: str,
    created_by: str,
    permissions: list[str] | None = None,
) -> tuple[str, str | None]:
    """
    Generate and store a new API key.

    Returns (plaintext_key, error_string).
    plaintext_key is shown ONCE to the user — never store or re-display it.
    """
    name = (name or "").strip()
    if not name:
        return "", "Key name is required."
    try:
        c = _db()
        if c is None:
            return "", "Database not available."
        raw    = f"hr_{secrets.token_hex(20)}"   # 48 printable chars
        c.table("api_keys").insert({
            "name":        name[:100],
            "key_hash":    _hash_key(raw),
            "key_prefix":  raw[:12],  # 12 chars = "hr_" + 9 hex = 36 bits of randomness
            "created_by":  (created_by or "")[:100],
            "status":      "active",
            "permissions": permissions or [],
        }).execute()
        return raw, None
    except Exception as exc:
        logger.warning("api_keys.generate: %s", exc)
        return "", "Failed to generate key. Check server logs."


def list_api_keys(include_revoked: bool = False) -> tuple[list[dict], str | None]:
    """Return API keys (no hashes).  Optionally include revoked keys."""
    try:
        c = _db()
        if c is None:
            return [], "Database not available."
        q = c.table("api_keys").select(_COLS)
        if not include_revoked:
            q = q.neq("status", "revoked")
        resp = q.order("created_at", desc=True).limit(200).execute()
        return resp.data or [], None
    except Exception as exc:
        logger.warning("api_keys.list: %s", exc)
        return [], f"{type(exc).__name__}: {exc}"


def revoke_api_key(key_id: str) -> str | None:
    """Permanently revoke a key. Returns error string or None."""
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("api_keys").update({"status": "revoked"}).eq("id", key_id).execute()
        return None
    except Exception as exc:
        logger.warning("api_keys.revoke(%s): %s", key_id, exc)
        return "Failed to revoke. Check server logs."


def set_key_status(key_id: str, status: str) -> str | None:
    """Set status to 'active' or 'disabled'. Returns error string or None."""
    if status not in ("active", "disabled"):
        return "Status must be 'active' or 'disabled'."
    try:
        c = _db()
        if c is None:
            return "Database not available."
        c.table("api_keys").update({"status": status}).eq("id", key_id).execute()
        return None
    except Exception as exc:
        logger.warning("api_keys.set_status(%s): %s", key_id, exc)
        return "Failed to update status. Check server logs."


def verify_api_key(raw_key: str) -> dict | None:
    """
    Verify a plaintext key and update last_used_at.
    Returns the key row (no hash) or None if invalid/revoked.
    """
    try:
        c = _db()
        if c is None:
            return None
        resp = (
            c.table("api_keys")
            .select(_COLS)
            .eq("key_hash", _hash_key(raw_key))
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        # Best-effort last_used_at update
        try:
            c.table("api_keys").update({
                "last_used_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }).eq("id", row["id"]).execute()
        except Exception:
            pass
        return row
    except Exception as exc:
        logger.warning("api_keys.verify: %s", exc)
        return None
