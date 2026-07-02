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
_supabase_tried  = False


def _get_client():
    """Return a Supabase client or None if secrets are unavailable."""
    global _supabase_client, _supabase_tried
    if _supabase_tried:
        return _supabase_client
    _supabase_tried = True
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if not url or not key:
            logger.info("db_logger: Supabase secrets not set — using local JSONL fallback.")
            return None
        from supabase import create_client
        _supabase_client = create_client(url, key)
        logger.info("db_logger: Supabase client initialised.")
    except Exception:
        logger.warning("db_logger: Could not initialise Supabase client — using local fallback.", exc_info=True)
        _supabase_client = None
    return _supabase_client


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

def _supabase_insert(row: dict[str, Any]) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.table("logs").insert(row).execute()
    except Exception:
        logger.warning("db_logger: Supabase insert failed — row dropped.", exc_info=True)


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
    except Exception:
        logger.warning("db_logger: log_unanswered failed silently.", exc_info=True)


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
    except Exception:
        logger.warning("db_logger: log_feedback failed silently.", exc_info=True)
