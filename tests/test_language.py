"""
Unit tests for the pure-logic modules (no Streamlit, no network calls).
Run with: pip install pytest && pytest tests/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.language import LANG_AR, LANG_EN, detect_language, is_greeting, t
from core.security import sanitize_input


def test_detect_language_arabic():
    assert detect_language("ما هي سياسة اللباس؟") == LANG_AR


def test_detect_language_english():
    assert detect_language("What is the dress code?") == LANG_EN


def test_detect_language_empty_defaults_to_english():
    assert detect_language("") == LANG_EN


def test_is_greeting_arabic():
    assert is_greeting("مرحبا") is True


def test_is_greeting_english():
    assert is_greeting("hello there") is True


def test_is_greeting_false_for_real_question():
    assert is_greeting("what is the dress code?") is False


def test_translation_falls_back_to_key_when_missing():
    assert t("unknown_key", LANG_AR) == "unknown_key"


def test_translation_returns_requested_language():
    assert t("greeting_reply", LANG_EN) != t("greeting_reply", LANG_AR)


def test_sanitize_input_flags_text_over_limit():
    text = "a" * 2000
    cleaned, error = sanitize_input(text, max_chars=1500)
    assert error == "too_long"
    assert len(cleaned) == 1500


def test_sanitize_input_flags_empty_text():
    cleaned, error = sanitize_input("   ", max_chars=1500)
    assert error == "empty"
    assert cleaned == ""


def test_sanitize_input_accepts_valid_text():
    cleaned, error = sanitize_input("What is the dress code?", max_chars=1500)
    assert error is None
    assert cleaned == "What is the dress code?"


def test_sanitize_input_strips_control_characters():
    cleaned, error = sanitize_input("Hello\x00World", max_chars=1500)
    assert error is None
    assert "\x00" not in cleaned
