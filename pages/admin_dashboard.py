"""
Admin Dashboard — HR Policy Assistant
Protected by ADMIN_PASSWORD secret. All data loads on-demand (button click).
Debug logging at every step so Cloud logs pinpoint any hang.
"""
from __future__ import annotations

# ── Very first line: confirm the script started ───────────────────────────────
import logging as _logging
_logging.basicConfig(
    level=_logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
_log = _logging.getLogger("admin_dashboard")
_log.info("ADMIN_TOP — page script entered")

# ── Standard imports only — NO langchain / fastembed / rag_engine ─────────────
import streamlit as st

_log.info("ADMIN_STEP_1 — streamlit imported OK")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Admin Dashboard | لوحة الإدارة",
    page_icon="📊",
    layout="wide",
)
_log.info("ADMIN_STEP_2 — page_config done")

st.markdown("""<style>
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; }
.admin-header { color: #C0392B; font-size: 1.6rem; font-weight: 700; margin-bottom: 0; }
.admin-sub    { color: #888;    font-size: 0.9rem;  margin-top: 0;  margin-bottom: 1.5rem; }
.block-container { padding-top: 2rem; }
</style>""", unsafe_allow_html=True)
_log.info("ADMIN_STEP_3 — CSS injected")

# ── Secret helpers (never raise, always return safe default) ──────────────────

def _get_secret(key: str, default: str = "") -> str:
    """Read from st.secrets, fall back to os.environ, then default."""
    import os
    try:
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


# ── Password gate ─────────────────────────────────────────────────────────────
_log.info("ADMIN_STEP_4 — entering password gate")

def _check_password() -> bool:
    correct = _get_secret("ADMIN_PASSWORD")
    if not correct:
        st.error(
            "⛔ **ADMIN_PASSWORD** is not configured in Streamlit Secrets.\n\n"
            "Go to **App settings → Secrets** and add:\n```toml\nADMIN_PASSWORD = \"your-password\"\n```"
        )
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
    _log.info("ADMIN_STEP_4b — not authenticated, showing login form")
    st.stop()

_log.info("ADMIN_STEP_5 — authenticated OK, rendering dashboard")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="admin-header">📊 Admin Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="admin-sub">HR Policy Assistant — Supabase Logs & Settings</p>', unsafe_allow_html=True)

_log.info("ADMIN_STEP_6 — header rendered, creating tabs")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_logs, tab_settings, tab_debug = st.tabs(["📋 Logs", "⚙️ Settings", "🔍 Debug"])

_log.info("ADMIN_STEP_7 — tabs created OK")

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
        _log.info("ADMIN_LOGS — fetching rows from Supabase")
        all_rows: list = []
        fetch_error: str | None = None
        try:
            from core.db_logger import fetch_logs, get_logging_mode
            all_rows, fetch_error = fetch_logs(log_type=None, limit=500)
            _log.info("ADMIN_LOGS — got %d rows (error=%s)", len(all_rows), fetch_error)
        except Exception as exc:
            fetch_error = f"{type(exc).__name__}: {exc}"
            _log.warning("ADMIN_LOGS — exception: %s", fetch_error)

        if fetch_error:
            st.error(f"⚠️ {fetch_error}")

        unanswered    = [r for r in all_rows if r.get("log_type") == "unanswered"]
        feedback_rows = [r for r in all_rows if r.get("log_type") == "feedback"]

        thumbs_up   = sum(1 for r in feedback_rows if r.get("vote") == "thumbs_up")
        thumbs_down = sum(1 for r in feedback_rows if r.get("vote") == "thumbs_down")
        pct_up = round(100 * thumbs_up / len(feedback_rows)) if feedback_rows else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("❓ Unanswered",   len(unanswered))
        k2.metric("💬 Feedback",     len(feedback_rows))
        k3.metric("👍 Positive",     f"{pct_up}%")
        k4.metric("👎 Negative",     f"{100 - pct_up}%" if feedback_rows else "—")

        st.divider()

        vote_map = {"thumbs_up 👍": "thumbs_up", "thumbs_down 👎": "thumbs_down"}
        display_rows = all_rows if src_filter == "all" else [r for r in all_rows if r.get("source") == src_filter]
        if vote_filter != "all":
            display_rows = [r for r in display_rows if r.get("vote") == vote_map.get(vote_filter)]

        st.caption(f"{len(display_rows)} row(s)")

        if display_rows:
            import pandas as pd
            df = pd.DataFrame(display_rows)
            cols = [c for c in ["ts", "log_type", "source", "question", "answer_preview", "best_score", "vote"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)
            csv_bytes = ("﻿" + df[cols].to_csv(index=False)).encode("utf-8")
            st.download_button("⬇️ Download CSV", data=csv_bytes, file_name="hr_logs.csv", mime="text/csv")
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

    if st.button("📂 Load current settings", key="load_settings"):
        st.session_state["_settings_loaded"] = True

    if st.session_state.get("_settings_loaded"):
        _log.info("ADMIN_SETTINGS — loading from Supabase")
        try:
            from core.settings_store import get_enabled_sources, set_enabled_sources, _ALL_SOURCES

            _SOURCE_LABELS = {
                "company":  "🏢  Company Policy / سياسة الشركة",
                "dubai_hr": "🏙️  Dubai HR Law / قانون العمل دبي",
            }
            current_enabled = get_enabled_sources()
            new_selection: list[str] = []

            for src in _ALL_SOURCES:
                checked = st.toggle(
                    _SOURCE_LABELS.get(src, src),
                    value=(src in current_enabled),
                    key=f"toggle_{src}",
                )
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
            _log.warning("ADMIN_SETTINGS — exception: %s", exc)
    else:
        st.info("Press **Load current settings** to fetch from Supabase.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — DEBUG (always visible, shows live environment info)
# ══════════════════════════════════════════════════════════════════════════════
with tab_debug:
    st.subheader("🔍 Live Environment Check")
    st.caption("Checks secrets, Supabase connectivity, and package versions. No data is modified.")

    import importlib, sys

    def _check(label: str, ok: bool, detail: str = "") -> None:
        icon = "✅" if ok else "❌"
        msg  = f"{icon} **{label}**"
        if detail:
            msg += f" — `{detail}`"
        st.markdown(msg)

    # Secrets
    _admin_pw  = bool(_get_secret("ADMIN_PASSWORD"))
    _groq_key  = bool(_get_secret("GROQ_API_KEY"))
    _supa_url  = _get_secret("SUPABASE_URL")
    _supa_key  = bool(_get_secret("SUPABASE_KEY"))

    st.markdown("#### Secrets")
    _check("ADMIN_PASSWORD", _admin_pw)
    _check("GROQ_API_KEY",   _groq_key)
    _check("SUPABASE_URL",   bool(_supa_url), _supa_url[:40] + "…" if _supa_url else "not set")
    _check("SUPABASE_KEY",   _supa_key)

    # Key packages
    st.markdown("#### Installed packages")
    for pkg in ("streamlit", "supabase", "fastembed", "faiss", "langchain_community", "groq"):
        try:
            mod = importlib.import_module(pkg.replace("-", "_"))
            ver = getattr(mod, "__version__", "?")
            _check(pkg, True, ver)
        except ImportError:
            _check(pkg, False, "not installed")

    # Python
    _check("Python", True, sys.version.split()[0])

    # Supabase ping (only when secrets are present)
    st.markdown("#### Supabase connectivity")
    if st.button("🔌 Ping Supabase", key="ping_supa"):
        if not (_supa_url and _supa_key):
            st.error("Secrets not configured — cannot ping.")
        else:
            with st.spinner("Pinging…"):
                try:
                    from core.db_logger import _get_client
                    c = _get_client()
                    if c is None:
                        st.error("_get_client() returned None — check secrets / timeout.")
                    else:
                        resp = c.table("logs").select("id").limit(1).execute()
                        st.success(f"✅ Supabase reachable — got {len(resp.data)} row(s) from `logs`.")
                except Exception as exc:
                    st.error(f"❌ {type(exc).__name__}: {exc}")
    else:
        st.info("Press **Ping Supabase** to test the connection.")

_log.info("ADMIN_BOTTOM — page script completed successfully")
