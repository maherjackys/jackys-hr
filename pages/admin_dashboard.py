"""
Admin Dashboard — HR Policy Assistant
Protected by ADMIN_PASSWORD. Not linked from the main app.
Data loads on-demand (button click) — page always opens instantly.
"""
from __future__ import annotations

import io
import logging

import streamlit as st

logger = logging.getLogger(__name__)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Admin Dashboard | لوحة الإدارة",
    page_icon="📊",
    layout="wide",
)

st.markdown("""<style>
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; }
.admin-header { color: #C0392B; font-size: 1.6rem; font-weight: 700; margin-bottom: 0; }
.admin-sub    { color: #888;    font-size: 0.9rem;  margin-top: 0;  margin-bottom: 1.5rem; }
.block-container { padding-top: 2rem; }
</style>""", unsafe_allow_html=True)

# ── Password gate ─────────────────────────────────────────────────────────────
def _check_password() -> bool:
    try:
        correct = st.secrets.get("ADMIN_PASSWORD", "")
    except Exception:
        correct = ""

    if not correct:
        st.error("⛔ ADMIN_PASSWORD not configured in Streamlit secrets.")
        st.stop()

    if st.session_state.get("admin_authed"):
        return True

    with st.form("admin_login"):
        st.markdown("### 🔒 Admin Login")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if pwd == correct:
                st.session_state["admin_authed"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False


if not _check_password():
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="admin-header">📊 Admin Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="admin-sub">HR Policy Assistant — Supabase Logs</p>', unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_logs, tab_settings = st.tabs(["📋 Logs", "⚙️ Settings"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — LOGS (on-demand load)
# ══════════════════════════════════════════════════════════════════════════════
with tab_logs:
    col_a, col_b = st.columns([3, 1])
    with col_a:
        src_filter  = st.selectbox("Source", ["all", "company", "dubai_hr"], key="src_f")
        vote_filter = st.selectbox("Vote",   ["all", "thumbs_up 👍", "thumbs_down 👎"], key="vote_f")
    with col_b:
        st.write("")
        st.write("")
        load_btn = st.button("🔄 Load / Refresh", use_container_width=True, type="primary")

    if load_btn or st.session_state.get("_logs_loaded"):
        st.session_state["_logs_loaded"] = True
        try:
            from core.db_logger import fetch_logs, get_logging_mode
            all_rows, fetch_error = fetch_logs(log_type=None, limit=500)
        except Exception as exc:
            all_rows, fetch_error = [], str(exc)

        if fetch_error:
            st.error(f"⚠️ {fetch_error}")

        unanswered    = [r for r in all_rows if r.get("log_type") == "unanswered"]
        feedback_rows = [r for r in all_rows if r.get("log_type") == "feedback"]

        # ── KPI row ───────────────────────────────────────────────────────────
        thumbs_up   = sum(1 for r in feedback_rows if r.get("vote") == "thumbs_up")
        thumbs_down = sum(1 for r in feedback_rows if r.get("vote") == "thumbs_down")
        pct_up = round(100 * thumbs_up / len(feedback_rows)) if feedback_rows else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("❓ Unanswered",   len(unanswered))
        k2.metric("💬 Feedback",     len(feedback_rows))
        k3.metric("👍 Positive",     f"{pct_up}%")
        k4.metric("👎 Negative",     f"{100 - pct_up}%" if feedback_rows else "—")

        st.divider()

        # ── Filter & show ─────────────────────────────────────────────────────
        vote_map = {"thumbs_up 👍": "thumbs_up", "thumbs_down 👎": "thumbs_down"}

        if src_filter == "all":
            display_rows = all_rows
        else:
            display_rows = [r for r in all_rows if r.get("source") == src_filter]

        if vote_filter != "all":
            display_rows = [r for r in display_rows if r.get("vote") == vote_map.get(vote_filter)]

        st.caption(f"{len(display_rows)} row(s)")

        if display_rows:
            import pandas as pd
            df = pd.DataFrame(display_rows)
            # Keep only useful columns that exist
            cols = [c for c in ["ts", "log_type", "source", "question", "answer_preview", "best_score", "vote"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)

            # CSV export (UTF-8 BOM so Arabic opens in Excel)
            csv_bytes = ("﻿" + df[cols].to_csv(index=False)).encode("utf-8")
            st.download_button("⬇️ Download CSV", data=csv_bytes,
                               file_name="hr_logs.csv", mime="text/csv")
        else:
            st.info("No rows match the current filter.")
    else:
        st.info("Press **Load / Refresh** to fetch logs from Supabase.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
with tab_settings:
    st.subheader("Source Visibility / ظهور المصادر")
    st.caption("Enable or disable each knowledge source.")

    try:
        from core.settings_store import get_enabled_sources, set_enabled_sources, _ALL_SOURCES

        _SOURCE_LABELS = {
            "company":  "🏢  Company Policy / سياسة الشركة",
            "dubai_hr": "🏙️  Dubai HR Law / قانون العمل دبي",
        }
        current_enabled = get_enabled_sources()
        new_selection: list[str] = []

        for src in _ALL_SOURCES:
            checked = st.toggle(_SOURCE_LABELS.get(src, src),
                                value=(src in current_enabled),
                                key=f"toggle_{src}")
            if checked:
                new_selection.append(src)

        st.write("")
        if st.button("💾 Save", type="primary"):
            err = set_enabled_sources(new_selection)
            if err:
                st.error(err)
            else:
                st.success("Saved! Changes apply within 60 seconds.")

    except Exception as exc:
        st.error(f"Settings unavailable: {exc}")
