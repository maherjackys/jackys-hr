"""Admin tab placeholder for email template settings."""
from __future__ import annotations

import streamlit as st


def render_email_templates_tab() -> None:
    st.subheader("Email Templates")
    st.info(
        "Email template storage is not implemented in the current database schema. "
        "This tab is kept available so the admin navigation does not break."
    )
