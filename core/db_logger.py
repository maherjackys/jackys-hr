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

import datetime
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOCAL_UNANSWERED = _LOGS_DIR / "unanswered_{source}.jsonl"
_LOCAL_FEEDBACK   = _LOGS_DIR / "feedback.jsonl"


# ── Supabase client (cached at module level, initialised once) ────────────────

_supabase_client = None
_supabase_ready  = False   # True only after a successful client creation


def _get_client():
    """Return a Supabase client or None if secrets are unavailable.

    Does NOT permanently cache failure — secrets may not be loaded on the
    very first call (e.g. during engine init before Streamlit runtime is up).
    Once the client is successfully created it is cached for the process.
    """
    global _supabase_client, _supabase_ready
    if _supabase_ready:
        return _supabase_client
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if not url or not key:
            logger.info("db_logger: SUPABASE_URL/KEY not in secrets — local JSONL fallback active.")
            return None
        from supabase import create_client
        _supabase_client = create_client(url, key)
        _supabase_ready  = True
        logger.info("db_logger: Supabase client initialised (%s).", url[:40])
        return _supabase_client
    except Exception as exc:
        logger.warning("db_logger: Supabase client init failed (%s: %s) — local fallback.", type(exc).__name__, exc)
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
                "question":       query,
                "answer_preview": None,
                "best_score":     None,
                "vote":           None,
            })
        else:
            _local_append(
                Path(str(_LOCAL_UNANSWERED).format(source=source)),
                {
                    "ts":     datetime.datetime.utcnow().isoformat() + "Z",
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
                "question":       question,
                "answer_preview": answer_preview[:200] if answer_preview else None,
                "best_score":     score,
                "vote":           vote,
            })
        else:
            _local_append(
                _LOCAL_FEEDBACK,
                {
                    "ts":           datetime.datetime.utcnow().isoformat() + "Z",
                    "source":       source,
                    "question":     question,
                    "answer":       answer_preview[:200] if answer_preview else None,
                    "best_score":   score,
                    "vote":         vote,
                },
            )
    except Exception as exc:
        logger.warning("db_logger: log_feedback failed (%s: %s).", type(exc).__name__, exc)


def fetch_logs(log_type: str | None = None, limit: int = 200) -> tuple[list[dict], str | None]:
    """Fetch rows from the logs table, newest first.

    Args:
        log_type: 'unanswered', 'feedback', or None for all rows.
        limit: max rows to return.

    Returns (rows, error_message). rows=[] and error_message set on any failure.
    Correct PostgREST builder order: select → filter → order → limit → execute.
    """
    try:
        client = _get_client()
        if client is None:
            return [], "Supabase client is None — check SUPABASE_URL/KEY secrets."
        q = client.table("logs").select("*")
        if log_type:                          # never pass .eq() when filtering all
            q = q.eq("log_type", log_type)
        q = q.order("ts", desc=True).limit(limit)
        response = q.execute()
        return response.data or [], None
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        logger.warning("db_logger: fetch_logs failed (%s).", msg)
        return [], msg
