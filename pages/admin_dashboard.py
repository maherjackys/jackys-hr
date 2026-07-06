"""
Admin Dashboard — password-gated control panel.

Access: /admin_dashboard (URL-only, not shown in sidebar navigation).
"""
from __future__ import annotations

import datetime
import os
import sys

import streamlit as st

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_secret(key: str, default: str = "") -> str:
    """Read a secret from st.secrets first, then os.environ."""
    try:
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


def _require_password() -> bool:
    """Show password gate. Return True when authenticated."""
    if st.session_state.get("admin_authed"):
        return True

    st.title("🔐 Admin Login")
    pwd = st.text_input("Password", type="password", key="admin_pwd_input")
    if st.button("Login", type="primary"):
        correct = _get_secret("ADMIN_PASSWORD")
        if correct and pwd == correct:
            st.session_state.admin_authed = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


# ── Page config (only when this page is active via st.navigation) ─────────────
st.set_page_config(
    page_title="Admin Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

print("ADMIN_PAGE_LOADED", flush=True, file=sys.stderr)

if not _require_password():
    st.stop()

# ── Main admin UI ─────────────────────────────────────────────────────────────
st.title("📊 Admin Dashboard")

tab_logs, tab_settings, tab_debug = st.tabs(["📋 Logs", "⚙️ Settings", "🐛 Debug"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB: Logs
# ─────────────────────────────────────────────────────────────────────────────
with tab_logs:
    st.subheader("Query Logs")

    col_filter, col_limit, col_btn = st.columns([2, 1, 1])
    with col_filter:
        log_type_filter = st.selectbox(
            "Log type",
            options=["all", "unanswered", "feedback"],
            key="log_type_filter",
        )
    with col_limit:
        log_limit = st.number_input("Max rows", min_value=10, max_value=1000, value=200, step=10, key="log_limit")
    with col_btn:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        fetch_btn = st.button("🔄 Fetch Logs", type="primary", use_container_width=True)

    if fetch_btn:
        from core.db_logger import fetch_logs
        ltype = log_type_filter if log_type_filter != "all" else None
        with st.spinner("Fetching…"):
            rows, err = fetch_logs(log_type=ltype, limit=int(log_limit))
        if err:
            st.error(f"Error: {err}")
        elif not rows:
            st.info("No rows found.")
        else:
            import pandas as pd
            df = pd.DataFrame(rows)
            st.success(f"Fetched {len(df)} rows.")
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download CSV",
                data=csv,
                file_name=f"logs_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

    # ── Local fallback logs ───────────────────────────────────────────────────
    st.divider()
    st.subheader("Local Fallback Logs")
    from pathlib import Path
    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    jsonl_files = sorted(logs_dir.glob("*.jsonl")) if logs_dir.exists() else []

    if not jsonl_files:
        st.info("No local JSONL log files found.")
    else:
        for jf in jsonl_files:
            with st.expander(f"📄 {jf.name}"):
                try:
                    lines = jf.read_text(encoding="utf-8").splitlines()[-100:]
                    st.code("\n".join(lines), language="json")
                except Exception as exc:
                    st.error(f"Could not read: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Settings
# ─────────────────────────────────────────────────────────────────────────────
with tab_settings:
    st.subheader("Knowledge Source Visibility")
    st.caption("Toggle which knowledge sources are available to end users.")

    try:
        from core.settings_store import get_enabled_sources, set_enabled_sources
        enabled = get_enabled_sources()

        col_co, col_dxb = st.columns(2)
        with col_co:
            co_on = st.toggle("🏢 Company Policy", value="company" in enabled, key="toggle_company")
        with col_dxb:
            dxb_on = st.toggle("🇦🇪 Dubai HR Policy", value="dubai_hr" in enabled, key="toggle_dubai")

        if st.button("💾 Save Settings", type="primary"):
            new_enabled: list[str] = []
            if co_on:
                new_enabled.append("company")
            if dxb_on:
                new_enabled.append("dubai_hr")
            if not new_enabled:
                st.warning("At least one source must remain enabled.")
            else:
                set_enabled_sources(new_enabled)
                st.success(f"Saved: {new_enabled}")

    except ImportError:
        st.warning("`core.settings_store` not found — source toggle unavailable.")
    except Exception as exc:
        st.error(f"Settings error: {exc}")

    st.divider()
    st.subheader("FAISS Index Management")

    col_idx1, col_idx2 = st.columns(2)
    with col_idx1:
        if st.button("🗑️ Clear Company Index", use_container_width=True):
            import shutil
            from config import get_settings
            s = get_settings()
            if s.db_dir.exists():
                shutil.rmtree(s.db_dir)
                st.success("Company FAISS index cleared — will rebuild on next query.")
            else:
                st.info("No company index found.")
    with col_idx2:
        if st.button("🗑️ Clear Dubai Index", use_container_width=True):
            import shutil
            from config import get_settings
            s = get_settings()
            if s.dubai_db_dir.exists():
                shutil.rmtree(s.dubai_db_dir)
                st.success("Dubai FAISS index cleared — will rebuild on next query.")
            else:
                st.info("No Dubai index found.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Debug
# ─────────────────────────────────────────────────────────────────────────────
with tab_debug:
    st.subheader("Runtime Diagnostics")

    if st.button("🔍 Run Diagnostics", type="primary"):
        results: list[tuple[str, str, str]] = []  # (check, status, detail)

        # Python version
        results.append(("Python", "✅", sys.version.split()[0]))

        # Streamlit version
        results.append(("Streamlit", "✅", st.__version__))

        # Secrets
        for sec_key in ("GROQ_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "ADMIN_PASSWORD"):
            val = _get_secret(sec_key)
            if val:
                results.append((f"Secret: {sec_key}", "✅", f"{val[:6]}…"))
            else:
                results.append((f"Secret: {sec_key}", "⚠️", "not set"))

        # Supabase client
        try:
            from core.db_logger import _get_client, get_logging_mode
            client = _get_client()
            mode = get_logging_mode()
            results.append(("Supabase client", "✅" if client else "⚠️", mode))
        except Exception as exc:
            results.append(("Supabase client", "❌", str(exc)))

        # fastembed / embeddings
        try:
            from langchain_community.embeddings import FastEmbedEmbeddings
            results.append(("FastEmbedEmbeddings import", "✅", "ok"))
        except Exception as exc:
            results.append(("FastEmbedEmbeddings import", "❌", str(exc)))

        # Config
        try:
            from config import get_settings
            s = get_settings()
            results.append(("Config", "✅", f"docs={s.docs_dir} db={s.db_dir}"))
        except Exception as exc:
            results.append(("Config", "❌", str(exc)))

        # FAISS index files
        try:
            from config import get_settings
            s = get_settings()
            co_exists = (s.db_dir / "index.faiss").exists()
            dxb_exists = (s.dubai_db_dir / "index.faiss").exists()
            results.append(("Company FAISS index", "✅" if co_exists else "⚠️", str(co_exists)))
            results.append(("Dubai FAISS index", "✅" if dxb_exists else "⚠️", str(dxb_exists)))
        except Exception as exc:
            results.append(("FAISS index check", "❌", str(exc)))

        # Render table
        import pandas as pd
        df = pd.DataFrame(results, columns=["Check", "Status", "Detail"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Session State")
    if st.button("👁️ Show Session State"):
        safe_state = {k: v for k, v in st.session_state.items() if "password" not in k.lower()}
        st.json(safe_state)

    st.divider()
    st.subheader("Environment Variables")
    if st.button("👁️ Show Env Vars (safe subset)"):
        safe_keys = ["STREAMLIT_SERVER_PORT", "HOME", "PATH", "PYTHONPATH", "HOSTNAME"]
        env_vals = {k: os.environ.get(k, "(not set)") for k in safe_keys}
        st.json(env_vals)
