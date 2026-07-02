"""
Admin Dashboard — HR Policy Assistant
Displays Supabase logs (unanswered queries + feedback votes).
Protected by ADMIN_PASSWORD secret. Not linked from the main app.
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

# ── Brand font ────────────────────────────────────────────────────────────────
st.markdown(
    '<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">',
    unsafe_allow_html=True,
)
st.markdown("""
<style>
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; }
.admin-header { color: #C0392B; font-size: 1.6rem; font-weight: 700; margin-bottom: 0; }
.admin-sub    { color: #888; font-size: 0.9rem; margin-top: 0; margin-bottom: 1.5rem; }
.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── Password gate ─────────────────────────────────────────────────────────────
def _check_password() -> bool:
    try:
        correct = st.secrets.get("ADMIN_PASSWORD", "")
    except Exception:
        correct = ""

    if not correct:
        st.error("⛔ ADMIN_PASSWORD is not configured in Streamlit secrets.")
        st.stop()

    if st.session_state.get("admin_authed"):
        return True

    with st.form("admin_login"):
        st.markdown("### 🔒 Admin Login")
        pwd = st.text_input("Password", type="password", placeholder="Enter admin password")
        submitted = st.form_submit_button("Login")
        if submitted:
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

# ── Load data ─────────────────────────────────────────────────────────────────
from core.db_logger import fetch_logs

@st.cache_data(ttl=60)
def _load(log_type: str | None, limit: int) -> list[dict]:
    return fetch_logs(log_type=log_type, limit=limit)

all_rows      = _load(None, 500)
unanswered    = [r for r in all_rows if r.get("log_type") == "unanswered"]
feedback_rows = [r for r in all_rows if r.get("log_type") == "feedback"]

col_refresh = st.columns([6, 1])[1]
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── KPI row ───────────────────────────────────────────────────────────────────
thumbs_up   = sum(1 for r in feedback_rows if r.get("vote") == "thumbs_up")
thumbs_down = sum(1 for r in feedback_rows if r.get("vote") == "thumbs_down")
pct_up      = round(100 * thumbs_up / len(feedback_rows)) if feedback_rows else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("❓ Unanswered / غير مجابة", len(unanswered))
k2.metric("💬 Feedback votes / تقييمات", len(feedback_rows))
k3.metric("👍 Thumbs-up / إيجابية", f"{pct_up}%")
k4.metric("👎 Thumbs-down / سلبية", f"{100 - pct_up}%" if feedback_rows else "—")

st.divider()


# ── CSV helper ────────────────────────────────────────────────────────────────
def _to_csv(rows: list[dict]) -> bytes:
    """Return UTF-8 with BOM so Arabic opens correctly in Excel."""
    if not rows:
        return "﻿".encode("utf-8")
    import csv
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_unans, tab_fb = st.tabs(["❓ الأسئلة غير المجابة", "💬 التقييمات"])

# ── Tab 1: Unanswered ─────────────────────────────────────────────────────────
with tab_unans:
    src_filter = st.selectbox(
        "Source / المصدر",
        ["all", "company", "dubai_hr"],
        key="unans_src",
    )
    filtered_u = (
        unanswered if src_filter == "all"
        else [r for r in unanswered if r.get("source") == src_filter]
    )

    st.caption(f"{len(filtered_u)} rows")

    if filtered_u:
        import pandas as pd
        df_u = pd.DataFrame(filtered_u)[["created_at", "source", "question"]].rename(columns={
            "created_at": "Timestamp",
            "source":     "Source",
            "question":   "Question",
        })
        st.dataframe(df_u, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Download CSV",
            data=_to_csv(filtered_u),
            file_name="unanswered_queries.csv",
            mime="text/csv",
            key="dl_unans",
        )
    else:
        st.info("No unanswered queries found for this filter.")

# ── Tab 2: Feedback ───────────────────────────────────────────────────────────
with tab_fb:
    vote_filter = st.selectbox(
        "Vote / التقييم",
        ["all", "thumbs_up 👍", "thumbs_down 👎"],
        key="fb_vote",
    )
    vote_map = {"thumbs_up 👍": "thumbs_up", "thumbs_down 👎": "thumbs_down"}
    filtered_f = (
        feedback_rows if vote_filter == "all"
        else [r for r in feedback_rows if r.get("vote") == vote_map.get(vote_filter)]
    )

    st.caption(f"{len(filtered_f)} rows")

    if filtered_f:
        import pandas as pd
        df_f = pd.DataFrame(filtered_f)[
            ["created_at", "source", "question", "answer_preview", "best_score", "vote"]
        ].rename(columns={
            "created_at":     "Timestamp",
            "source":         "Source",
            "question":       "Question",
            "answer_preview": "Answer preview",
            "best_score":     "Score",
            "vote":           "Vote",
        })
        # Render emoji vote
        df_f["Vote"] = df_f["Vote"].map({"thumbs_up": "👍", "thumbs_down": "👎"}).fillna(df_f["Vote"])
        st.dataframe(df_f, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Download CSV",
            data=_to_csv(filtered_f),
            file_name="feedback_votes.csv",
            mime="text/csv",
            key="dl_fb",
        )
    else:
        st.info("No feedback entries found for this filter.")
