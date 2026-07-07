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
from typing import TYPE_CHECKING  # noqa: F401  (kept for any runtime type checks)

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent

# Kept as str alias — no longer a Literal so new sources can be added at runtime
KnowledgeSource = str


@dataclass(frozen=True)
class Settings:
    # ── Document directories (named dirs for the two built-in sources) ────────
    docs_dir: Path = field(default_factory=lambda: BASE_DIR / "hr_documents")
    dubai_docs_dir: Path = field(default_factory=lambda: BASE_DIR / "dubai_hr_documents")

    # ── FAISS index directories ────────────────────────────────────────────────
    db_dir: Path = field(default_factory=lambda: BASE_DIR / "faiss_db")
    dubai_db_dir: Path = field(default_factory=lambda: BASE_DIR / "dubai_faiss_db")

    # ── Static assets ──────────────────────────────────────────────────────────
    css_path: Path = field(default_factory=lambda: BASE_DIR / "style.css")

    # ── Embedding & LLM ───────────────────────────────────────────────────────
    # paraphrase-multilingual-MiniLM-L12-v2: 0.22 GB ONNX, 384-dim.
    # Supports Arabic + English. Fits comfortably in Streamlit Cloud 1 GB RAM.
    # Does NOT use e5-style "passage:"/"query:" prefixes.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_fallback_model: str = "llama-3.1-8b-instant"  # used when primary hits rate limit
    llm_temperature: float = 0.45
    llm_max_tokens: int = 2048

    # ── Retrieval ─────────────────────────────────────────────────────────────
    # FAISS L2 distance: LOWER = MORE similar.
    # multilingual-e5-small (normalized) produces on-topic scores ~0.2–0.7;
    # off-topic scores typically >0.85. Starting values — tune after testing.
    similarity_threshold: float = 0.85   # reject docs above this (too dissimilar)
    retrieval_k: int = 8                  # fetch more candidates before threshold filter
    # Show high-confidence expander citation only when score is clearly relevant.
    min_score_to_show_source: float = 0.75  # expander if score ≤ this; inline badge otherwise

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

    def docs_dir_for(self, source: str) -> Path:
        """Return the documents directory for *source*.

        Built-in sources use their legacy named dirs.
        Any new source "foo" gets BASE_DIR/foo_documents/.
        """
        if source == "company":
            return self.docs_dir
        if source == "dubai_hr":
            return self.dubai_docs_dir
        return BASE_DIR / f"{source}_documents"

    def db_dir_for(self, source: str) -> Path:
        """Return the FAISS index directory for *source*.

        Built-in sources use their legacy named dirs.
        Any new source "foo" gets BASE_DIR/foo_faiss_db/.
        """
        if source == "company":
            return self.db_dir
        if source == "dubai_hr":
            return self.dubai_db_dir
        return BASE_DIR / f"{source}_faiss_db"


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
