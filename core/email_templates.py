"""
Email template store — backed by app_settings.

Key format: email_template.{name}
Value JSONB: {subject, body, variables: list[str], updated_at, updated_by}

Templates are display-only by default (sending requires external SMTP/SendGrid config).

Public API:
    get_template(name)                         → dict
    save_template(name, subject, body, actor)  → error_str | None
    restore_default(name, actor)               → error_str | None
    list_templates()                           → list[dict]       (cached 60 s)
    TEMPLATE_NAMES                             → list[str]        (ordered)
"""
from __future__ import annotations

import datetime
import logging

import streamlit as st

logger = logging.getLogger(__name__)

_KEY_PREFIX = "email_template."

# ── Built-in defaults ─────────────────────────────────────────────────────────
_DEFAULTS: dict[str, dict] = {
    "welcome": {
        "label":    "Welcome Email",
        "subject":  "Welcome to HR Policy Assistant — {{display_name}}",
        "body": (
            "Hi {{display_name}},\n\n"
            "Your admin account has been created on the HR Policy Assistant platform.\n\n"
            "  Username : {{username}}\n"
            "  Role     : {{role}}\n\n"
            "Please log in and change your password immediately.\n\n"
            "Best regards,\n"
            "HR Policy Assistant"
        ),
        "variables": ["{{display_name}}", "{{username}}", "{{role}}"],
    },
    "password_reset": {
        "label":   "Password Reset",
        "subject": "Password Reset — HR Policy Assistant",
        "body": (
            "Hi {{display_name}},\n\n"
            "Your password has been reset by an administrator.\n\n"
            "If you did not request this, contact your system administrator immediately.\n\n"
            "Best regards,\n"
            "HR Policy Assistant"
        ),
        "variables": ["{{display_name}}", "{{username}}"],
    },
    "account_disabled": {
        "label":   "Account Disabled",
        "subject": "Account Disabled — HR Policy Assistant",
        "body": (
            "Hi {{display_name}},\n\n"
            "Your account on the HR Policy Assistant has been disabled.\n\n"
            "Reason: {{reason}}\n\n"
            "Contact your administrator to re-enable your account.\n\n"
            "Best regards,\n"
            "HR Policy Assistant"
        ),
        "variables": ["{{display_name}}", "{{username}}", "{{reason}}"],
    },
    "password_changed": {
        "label":   "Password Changed",
        "subject": "Password Changed — HR Policy Assistant",
        "body": (
            "Hi {{display_name}},\n\n"
            "Your password was changed on {{changed_at}}.\n\n"
            "If you did not make this change, contact your administrator immediately.\n\n"
            "Best regards,\n"
            "HR Policy Assistant"
        ),
        "variables": ["{{display_name}}", "{{changed_at}}"],
    },
    "general_notification": {
        "label":   "General Notification",
        "subject": "Notification — HR Policy Assistant",
        "body": (
            "Hi {{display_name}},\n\n"
            "{{message}}\n\n"
            "Best regards,\n"
            "HR Policy Assistant"
        ),
        "variables": ["{{display_name}}", "{{message}}"],
    },
}

TEMPLATE_NAMES: list[str] = list(_DEFAULTS.keys())


def _db():
    from core.db_logger import _get_client
    return _get_client()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_template(name: str) -> dict:
    """Return the template dict for *name*. Falls back to built-in default."""
    if name not in _DEFAULTS:
        return {}
    try:
        c = _db()
        if c is not None:
            resp = (
                c.table("app_settings")
                .select("key,value")
                .eq("key", f"{_KEY_PREFIX}{name}")
                .limit(1)
                .execute()
            )
            if resp.data:
                val = resp.data[0]["value"]
                if isinstance(val, dict) and "subject" in val:
                    return {"name": name, "label": _DEFAULTS[name]["label"], **val}
    except Exception as exc:
        logger.warning("email_templates.get(%s): %s", name, exc)
    return _build_default(name)


def save_template(
    name: str,
    subject: str,
    body: str,
    actor: str = "",
) -> str | None:
    """Save or update a template. Returns error string or None."""
    if name not in _DEFAULTS:
        return f"Unknown template '{name}'."
    try:
        c = _db()
        if c is None:
            return "Database not available."
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        value = {
            "subject":    subject.strip()[:500],
            "body":       body[:10_000],
            "variables":  _DEFAULTS[name]["variables"],
            "updated_at": now,
            "updated_by": (actor or "")[:100],
        }
        c.table("app_settings").upsert(
            {"key": f"{_KEY_PREFIX}{name}", "value": value},
            on_conflict="key",
        ).execute()
        list_templates.clear()
        return None
    except Exception as exc:
        logger.warning("email_templates.save(%s): %s", name, exc)
        return "Failed to save template. Check server logs."


def restore_default(name: str, actor: str = "") -> str | None:
    """Restore a template to its built-in default content."""
    if name not in _DEFAULTS:
        return f"Unknown template '{name}'."
    d = _DEFAULTS[name]
    return save_template(name, d["subject"], d["body"], actor=actor)


@st.cache_data(ttl=60)
def list_templates() -> list[dict]:
    """Return all templates, mixing DB values with defaults."""
    return [get_template(name) for name in TEMPLATE_NAMES]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_default(name: str) -> dict:
    d = _DEFAULTS.get(name, {})
    return {
        "name":       name,
        "label":      d.get("label", name),
        "subject":    d.get("subject", ""),
        "body":       d.get("body", ""),
        "variables":  d.get("variables", []),
        "updated_at": None,
        "updated_by": None,
    }


def render_preview(template: dict, sample_values: dict | None = None) -> str:
    """Return the body with sample_values substituted for preview."""
    body = template.get("body", "")
    samples = sample_values or {
        "{{display_name}}": "Jane Smith",
        "{{username}}":     "jsmith",
        "{{role}}":         "moderator",
        "{{reason}}":       "Policy violation",
        "{{changed_at}}":   datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "{{message}}":      "This is a sample notification message.",
    }
    for var, val in samples.items():
        body = body.replace(var, val)
    return body
