"""
Lightweight input validation.

Keeps the chatbot resilient against oversized payloads (cost / abuse
control) and strips control characters, without adding heavyweight
dependencies. This is not a substitute for output-encoding — Streamlit's
st.write() already escapes user content safely when rendered.
"""
from __future__ import annotations

import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_input(text: str, max_chars: int) -> tuple[str, str | None]:
    """
    Returns (clean_text, error_key).
    error_key is one of: None, "empty", "too_long".
    """
    if not text or not text.strip():
        return "", "empty"

    cleaned = _CONTROL_CHARS.sub("", text).strip()

    if len(cleaned) > max_chars:
        return cleaned[:max_chars], "too_long"

    return cleaned, None
