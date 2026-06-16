"""
Centralized configuration.

All tunable values live here instead of scattered across the codebase.
Reading the API key has a single, explicit resolution order and never
logs or echoes the secret value.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    docs_dir: Path = BASE_DIR / "hr_documents"
    db_dir: Path = BASE_DIR / "faiss_db"
    css_path: Path = BASE_DIR / "style.css"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024

    # FAISS uses L2 distance: LOWER = more similar. Above this, treat the
    # question as out of scope rather than risking a hallucinated answer.
    similarity_threshold: float = 1.8
    retrieval_k: int = 3

    max_history_messages: int = 20
    max_input_chars: int = 1500
    max_requests_per_minute: int = 12

    chunk_size: int = 1000
    chunk_overlap: int = 200

    llm_retry_attempts: int = 2
    llm_retry_base_delay_seconds: float = 1.0

    history_turns_for_context: int = 3


def get_settings() -> Settings:
    return Settings()


def get_groq_api_key() -> str:
    """
    Resolution order: environment variable -> Streamlit secrets -> empty.
    The returned value is never logged.
    """
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    try:
        return str(st.secrets.get("GROQ_API_KEY", "")).strip()
    except Exception:
        return ""
