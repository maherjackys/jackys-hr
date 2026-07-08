"""
Centralised logging to Supabase (prod) with local JSONL fallback (dev).

Two public functions — both are fire-and-forget, never raise:
  log_unanswered(query, source)
  log_feedback(source, question, answer_preview, best_score, vote)

Supabase is used when SUPABASE_URL and SUPABASE_KEY are present in
st.secrets. If secrets are missing (local dev), rows are written to the
local _append_jsonl fallback so nothing is lost.
"""
from __future__ import annotations

import concurrent.futures as _cf
import datetime
import logging
import os as _os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOCAL_UNANSWERED = _LOGS_DIR / "unanswered_{source}.jsonl"
_LOCAL_FEEDBACK   = _LOGS_DIR / "feedback.jsonl"


# ── Supabase client (cached at module level, initialised once) ────────────────

_supabase_client = None
_supabase_ready  = False   # True only after a successful client creation
_supabase_lock   = threading.Lock()


def _get_client():
    """Return a Supabase client or None if secrets are unavailable.

    create_client() can block the main thread: supabase-py's GoTrue auth
    initialisation may probe the auth endpoint with no timeout of its own.
    We read credentials in the main thread (st.secrets is not thread-safe),
    then run create_client() in a worker thread with a hard 5-second wall-
    clock deadline so a slow / unreachable Supabase never hangs the UI.
    """
    global _supabase_client, _supabase_ready
    # Fast path — no lock needed once ready
    if _supabase_ready:
        return _supabase_client
    # Double-checked locking: only one thread initialises the client
    with _supabase_lock:
        if _supabase_ready:
            return _supabase_client
        try:
            # ── Read credentials in the main thread ────────────────────────────
            url, key = "", ""
            try:
                import streamlit as _st
                url = _st.secrets.get("SUPABASE_URL", "")
                key = _st.secrets.get("SUPABASE_KEY", "")
            except Exception:
                pass
            # Community Cloud also injects secrets as env vars — use as fallback
            if not url:
                url = _os.environ.get("SUPABASE_URL", "")
            if not key:
                key = _os.environ.get("SUPABASE_KEY", "")

            if not url or not key:
                logger.info("db_logger: SUPABASE_URL/KEY not configured — JSONL fallback active.")
                return None

            # ── create_client() in a worker thread with hard timeout ──────────
            def _make_client():
                from supabase import create_client, ClientOptions
                return create_client(
                    url, key,
                    options=ClientOptions(postgrest_client_timeout=5),
                )

            with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
                _fut = _pool.submit(_make_client)
                try:
                    _supabase_client = _fut.result(timeout=5)
                except _cf.TimeoutError:
                    logger.warning("db_logger: create_client() timed out after 5 s — JSONL fallback.")
                    return None

            _supabase_ready = True
            logger.info("db_logger: Supabase client ready (%s…).", url[:40])
            return _supabase_client
        except Exception as exc:
            logger.warning("db_logger: client init failed (%s: %s) — JSONL fallback.", type(exc).__name__, exc)
            return None


def get_logging_mode() -> str:
    """Return 'supabase' if the client is ready, else 'local'."""
    return "supabase" if _supabase_ready else "local"


# ── Local fallback ────────────────────────────────────────────────────────────

def _local_append(path: Path, entry: dict, max_lines: int = 500) -> None:
    """Append a JSON line to a local file, rotating when full."""
    try:
        import json
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False)
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) >= max_lines:
                lines = lines[-(max_lines - 1):]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        logger.warning("db_logger: local fallback write failed for %s", path)


# ── Supabase insert ───────────────────────────────────────────────────────────

def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert any numpy/non-serialisable scalars to native Python types.

    FAISS returns scores as numpy.float32 which the Supabase JSON encoder
    rejects. Any object with an `.item()` method (numpy scalar protocol) is
    converted; everything else is left untouched.
    """
    cleaned = {}
    for k, v in row.items():
        if v is None:
            cleaned[k] = None
        elif hasattr(v, "item"):          # numpy scalar → native Python
            cleaned[k] = v.item()
        elif isinstance(v, float) and (v != v or v == float("inf") or v == float("-inf")):
            cleaned[k] = None             # NaN / inf → NULL
        else:
            cleaned[k] = v
    return cleaned


def _supabase_insert(row: dict[str, Any]) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.table("logs").insert(_clean_row(row)).execute()
    except Exception as exc:
        logger.warning("db_logger: Supabase insert failed (%s: %s) — row dropped.", type(exc).__name__, exc)


# ── Public API ────────────────────────────────────────────────────────────────

def log_unanswered(query: str, source: str) -> None:
    """Log a query that found no relevant documents."""
    try:
        client = _get_client()
        if client is not None:
            _supabase_insert({
                "log_type":       "unanswered",
                "source":         source,
                "query":          query,
                "answer_preview": None,
                "score":          None,
                "vote":           None,
            })
        else:
            _local_append(
                Path(str(_LOCAL_UNANSWERED).format(source=source)),
                {
                    "ts":     datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "query":  query,
                    "source": source,
                },
            )
    except Exception as exc:
        logger.warning("db_logger: log_unanswered failed (%s: %s).", type(exc).__name__, exc)


def log_feedback(
    source: str,
    question: str,
    answer_preview: str,
    best_score: float | None,
    vote: str,
) -> None:
    """Log a thumbs-up / thumbs-down vote from the user."""
    try:
        score = best_score if (best_score is not None and best_score != float("inf")) else None
        client = _get_client()
        if client is not None:
            _supabase_insert({
                "log_type":       "feedback",
                "source":         source,
                "query":          question,
                "answer_preview": answer_preview[:200] if answer_preview else None,
                "score":          score,
                "vote":           vote,
            })
        else:
            _local_append(
                _LOCAL_FEEDBACK,
                {
                    "ts":           datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "source":       source,
                    "query":        question,
                    "answer":       answer_preview[:200] if answer_preview else None,
                    "score":        score,
                    "vote":         vote,
                },
            )
    except Exception as exc:
        logger.warning("db_logger: log_feedback failed (%s: %s).", type(exc).__name__, exc)


def log_admin_action(action: str, source: str, filename: str = "", actor: str = "") -> None:
    """Log an admin action (upload / delete / rebuild / add_source) to the logs table."""
    try:
        detail = f"{action}: {filename}" if filename else action
        client = _get_client()
        if client is not None:
            _supabase_insert({
                "log_type":       "admin_action",
                "source":         source,
                "query":          detail[:500],
                "answer_preview": actor[:100] if actor else None,
                "score":          None,
                "vote":           None,
            })
        else:
            _local_append(
                _LOGS_DIR / "admin_actions.jsonl",
                {
                    "ts":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "action":  detail,
                    "source":  source,
                    "actor":   actor,
                },
            )
    except Exception as exc:
        logger.warning("db_logger: log_admin_action failed (%s: %s).", type(exc).__name__, exc)


def log_login_attempt(username: str, success: bool) -> None:
    """Log a login attempt to the login_history table (migration 005)."""
    try:
        client = _get_client()
        if client is not None:
            client.table("login_history").insert({
                "username": username[:100],
                "success":  success,
            }).execute()
        else:
            _local_append(
                _LOGS_DIR / "login_history.jsonl",
                {
                    "ts":       datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "username": username,
                    "success":  success,
                },
            )
    except Exception as exc:
        logger.warning("db_logger: log_login_attempt failed (%s: %s).", type(exc).__name__, exc)


def fetch_login_history(
    username: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], str | None]:
    """Fetch login history rows, newest first. Requires migration 005."""
    try:
        client = _get_client()
        if client is None:
            return [], "Supabase not available."
        q = client.table("login_history").select("id,username,success,created_at")
        if username:
            q = q.eq("username", username)
        q = q.order("created_at", desc=True).limit(limit)
        resp = q.execute()
        return resp.data or [], None
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        logger.warning("db_logger: fetch_login_history failed (%s).", msg)
        return [], msg


def fetch_logs(
    log_type: str | None = None,
    limit: int = 200,
    date_from: "datetime.date | None" = None,
    date_to: "datetime.date | None" = None,
    search: str | None = None,
    offset: int = 0,
) -> tuple[list[dict], str | None]:
    """Fetch rows from the logs table, newest first.

    Args:
        log_type:  'unanswered', 'feedback', 'admin_action', or None for all.
        limit:     max rows to return.
        date_from: include only rows with ts >= this date (UTC).
        date_to:   include only rows with ts <= this date + 1 day (UTC).
        search:    case-insensitive substring filter on the query column.
        offset:    skip this many rows (for pagination).

    Returns (rows, error_message). rows=[] and error_message set on any failure.
    """
    try:
        client = _get_client()
        if client is None:
            return [], "Supabase client is None — check SUPABASE_URL/KEY secrets."
        q = client.table("logs").select("id,ts,log_type,source,query,answer_preview,score,vote,actor")
        if log_type:
            q = q.eq("log_type", log_type)
        if date_from:
            q = q.gte("ts", date_from.isoformat())
        if date_to:
            _end = date_to + datetime.timedelta(days=1)
            q = q.lt("ts", _end.isoformat())
        if search and search.strip():
            q = q.ilike("query", f"%{search.strip()}%")
        q = q.order("ts", desc=True).limit(limit)
        if offset:
            q = q.range(offset, offset + limit - 1)
        response = q.execute()
        return response.data or [], None
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        logger.warning("db_logger: fetch_logs failed (%s).", msg)
        return [], msg
