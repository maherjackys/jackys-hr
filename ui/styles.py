"""CSS loader for the Streamlit app."""
from __future__ import annotations

from pathlib import Path

import streamlit as st


def inject_css(css_path: Path) -> None:
    try:
        css = css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
