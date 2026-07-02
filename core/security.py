"""
Lightweight input validation and prompt-injection defense.

Keeps the chatbot resilient against oversized payloads (cost / abuse
control), strips control characters, and detects common prompt-injection
patterns before text reaches the LLM.

This is not a substitute for output-encoding — Streamlit's st.write()
already escapes user content safely when rendered.
"""
from __future__ import annotations

import base64
import logging
import re

logger = logging.getLogger(__name__)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Prompt-injection patterns — only unambiguous injection phrases
# Overly broad patterns (act as, pretend, you are now) were removed because
# they blocked innocent HR questions like "Who can act as my approver?"
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"(?:^|\s)system\s*:", re.I),
    re.compile(r"(?:^|\s)assistant\s*:", re.I),
    re.compile(r"\bdisregard\b.*\binstructions?\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bdan\s+mode\b", re.I),
]

# Base64-like payload: long run of b64 alphabet chars — often used to hide injections
_B64_PAYLOAD = re.compile(r"[A-Za-z0-9+/=]{40,}")


def _is_b64_payload(text: str) -> bool:
    """Return True if text contains a suspicious base64-like block (≥40 chars)."""
    match = _B64_PAYLOAD.search(text)
    if not match:
        return False
    blob = match.group(0)
    try:
        decoded = base64.b64decode(blob + "==").decode("utf-8", errors="replace")
        # Only flag if decoded content looks like instructions
        lowered = decoded.lower()
        return any(kw in lowered for kw in ("ignore", "system:", "assistant:", "pretend", "jailbreak"))
    except Exception:
        return False


def sanitize_input(text: str, max_chars: int) -> tuple[str, str | None]:
    """
    Returns (clean_text, error_key).

    error_key is one of:
      None                — input is clean
      "empty"             — blank after stripping
      "input_too_long"    — exceeds max_chars
      "injection_attempt" — prompt-injection pattern detected
    """
    if not text or not text.strip():
        return "", "empty"

    cleaned = _CONTROL_CHARS.sub("", text).strip()

    if len(cleaned) > max_chars:
        return cleaned[:max_chars], "input_too_long"

    # Prompt-injection: strip silently and answer normally — avoids false-positive warnings
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            logger.warning("Injection phrase stripped from query: %r", cleaned[:80])
            cleaned = pattern.sub("", cleaned).strip()

    # Base64 payloads are unambiguously malicious — still block these
    if _is_b64_payload(cleaned):
        logger.warning("Base64 payload detected: %r", cleaned[:50])
        sanitized = _B64_PAYLOAD.sub("[…]", cleaned).strip()
        return sanitized, "injection_attempt"

    return cleaned, None
