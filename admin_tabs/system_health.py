"""Admin tab for lightweight system health checks."""
from __future__ import annotations

import os

import streamlit as st


def render_system_health_tab() -> None:
    from config import get_groq_api_key, get_settings
    from core.db_logger import _get_client, get_logging_mode
    from core.settings_store import get_enabled_sources

    st.subheader("System Health")
    settings = get_settings()
    sources = get_enabled_sources()

    checks: list[dict[str, str]] = []
    checks.append({
        "Check": "Groq API key",
        "Status": "OK" if get_groq_api_key() else "Missing",
        "Detail": "Configured" if get_groq_api_key() else "Set GROQ_API_KEY",
    })
    checks.append({
        "Check": "Supabase client",
        "Status": "OK" if _get_client() else "Unavailable",
        "Detail": get_logging_mode(),
    })
    checks.append({"Check": "Python runtime", "Status": "OK", "Detail": os.sys.version.split()[0]})

    for source in sources:
        docs_dir = settings.docs_dir_for(source)
        db_dir = settings.db_dir_for(source)
        docs_count = len([p for p in docs_dir.iterdir() if p.is_file()]) if docs_dir.exists() else 0
        index_file = db_dir / "index.faiss"
        checks.append({
            "Check": f"Documents: {source}",
            "Status": "OK" if docs_dir.exists() else "Missing",
            "Detail": f"{docs_count} files in {docs_dir.name}",
        })
        checks.append({
            "Check": f"FAISS index: {source}",
            "Status": "OK" if index_file.exists() else "Missing",
            "Detail": index_file.name,
        })

    st.dataframe(checks, use_container_width=True, hide_index=True)
