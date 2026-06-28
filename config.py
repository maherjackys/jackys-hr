"""
Centralized configuration.

All tunable values live here instead of scattered across the codebase.
Reading the API key has a single, explicit resolution order and never
logs or echoes the secret value.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent

# Knowledge source type — extensible for future sources
KnowledgeSource = Literal["company", "dubai_hr"]


@dataclass(frozen=True)
class Settings:
    # ── Document directories ──────────────────────────────────────────────────
    docs_dir: Path = field(default_factory=lambda: BASE_DIR / "hr_documents")
    dubai_docs_dir: Path = field(default_factory=lambda: BASE_DIR / "dubai_hr_documents")

    # ── FAISS index directories ────────────────────────────────────────────────
    db_dir: Path = field(default_factory=lambda: BASE_DIR / "faiss_db")
    dubai_db_dir: Path = field(default_factory=lambda: BASE_DIR / "dubai_faiss_db")

    # ── Static assets ──────────────────────────────────────────────────────────
    css_path: Path = field(default_factory=lambda: BASE_DIR / "style.css")

    # ── Embedding & LLM ───────────────────────────────────────────────────────
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.35
    llm_max_tokens: int = 2048

    # ── Retrieval ─────────────────────────────────────────────────────────────
    # FAISS L2 distance: LOWER value = MORE similar. Scores range ~0 (identical)
    # to ~4+ (unrelated). Tune both thresholds together.
    similarity_threshold: float = 1.4    # reject docs above this (too dissimilar)
    retrieval_k: int = 8                  # fetch more candidates before threshold filter
    min_score_to_show_source: float = 1.2 # only cite the source doc if score ≤ this

    # ── Text chunking ─────────────────────────────────────────────────────────
    # Larger chunks preserve policy context that spans multiple sentences.
    chunk_size: int = 1200
    chunk_overlap: int = 200

    # ── Conversation limits ───────────────────────────────────────────────────
    max_history_messages: int = 20
    max_input_chars: int = 1500
    history_turns_for_context: int = 3

    # ── Rate limiting ─────────────────────────────────────────────────────────
    max_requests_per_minute: int = 12

    def docs_dir_for(self, source: KnowledgeSource) -> Path:
        """Return the correct documents directory for the given source."""
        return self.dubai_docs_dir if source == "dubai_hr" else self.docs_dir

    def db_dir_for(self, source: KnowledgeSource) -> Path:
        """Return the correct FAISS DB directory for the given source."""
        return self.dubai_db_dir if source == "dubai_hr" else self.db_dir


def get_settings() -> Settings:
    return Settings()


def get_groq_api_key() -> str:
    """
    Resolution order (first non-empty value wins):
      1. Streamlit secrets  →  st.secrets["GROQ_API_KEY"]
      2. Environment variable  →  os.environ["GROQ_API_KEY"]

    Returns an empty string if neither is set so callers can prompt the user.
    This function never logs or echoes the key.
    """
    try:
        key = st.secrets.get("GROQ_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY", "")
