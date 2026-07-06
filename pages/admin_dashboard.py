"""
Admin Dashboard — persistent-session, password-gated control panel.

Auth architecture:
  - st.context.cookies reads the "admin_session" cookie from the HTTP
    request headers on every render (native Streamlit ≥ 1.37, no delay).
  - extra-streamlit-components CookieManager sets / deletes the cookie
    via a hidden JS iframe (write-only use — no timing-read dependency).
  - Session tokens (64-hex, 256-bit) live in admin_sessions Supabase table
    with a 24-hour TTL.
  - Passwords stored as bcrypt hashes in admin_users table; plain
    ADMIN_PASSWORD secret auto-migrates on first login.

Tabs (post-login):
  📋 Logs | 📁 Manage Docs | ➕ Add Source | ⚙️ Settings | 🔑 Account | 🐛 Debug
"""
from __future__ import annotations

import datetime
import os
import re
import sys
from pathlib import Path

import streamlit as st

# ── Cookie writer (write-only; reading done via st.context.cookies) ───────────
try:
    import extra_streamlit_components as stx
    _cookie_writer = stx.CookieManager(key="hr_admin_cookie_mgr_v1")
    _COOKIES_AVAILABLE = True
except Exception:
    _cookie_writer = None
    _COOKIES_AVAILABLE = False

_SESSION_COOKIE = "admin_session"
_SESSION_TTL_DAYS = 1


# ── Cookie helpers ─────────────────────────────────────────────────────────────

def _read_session_cookie() -> str:
    """Read the session token from the HTTP request (native, no delay)."""
    try:
        return st.context.cookies.get(_SESSION_COOKIE, "")
    except Exception:
        return ""


def _write_session_cookie(token: str) -> None:
    """Set the session cookie in the browser (JS-based, async)."""
    if _cookie_writer is None:
        return
    try:
        expires = datetime.datetime.now() + datetime.timedelta(days=_SESSION_TTL_DAYS)
        _cookie_writer.set(_SESSION_COOKIE, token, expires_at=expires)
    except Exception as exc:
        st.warning(f"Could not persist session cookie: {exc}", icon="⚠️")


def _delete_session_cookie() -> None:
    """Delete the session cookie from the browser (JS-based, async)."""
    if _cookie_writer is None:
        return
    try:
        _cookie_writer.delete(_SESSION_COOKIE)
    except Exception:
        pass


# ── Misc helpers ───────────────────────────────────────────────────────────────

def _get_secret(key: str, default: str = "") -> str:
    try:
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w\s\-.]", "_", name)
    return name[:200]


def _index_status(db_dir: Path, docs_dir: Path) -> tuple[str, str]:
    """Return (emoji, explanation) for a source's FAISS index state."""
    if not docs_dir.exists():
        return "❌", f"Docs folder missing: {docs_dir.resolve()}"
    supported = [f for f in docs_dir.iterdir()
                 if f.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}]
    if not supported:
        return "⚠️", f"No supported documents in {docs_dir.resolve()}"
    if not (db_dir / "index.faiss").exists():
        return "⚠️", f"Index not built yet — {len(supported)} doc(s) ready. Use 'Build' below."
    return "✅", f"{(db_dir / 'index.faiss').resolve()} ({len(supported)} source docs)"


# ── Session restoration ────────────────────────────────────────────────────────
# Runs on EVERY script execution (before any widget is rendered).
# st.context.cookies is populated from HTTP request headers — no async delay.

_cookie_token = _read_session_cookie()

if _cookie_token and not st.session_state.get("admin_authed"):
    from core.auth import verify_session as _vs
    _restored_user = _vs(_cookie_token)
    if _restored_user:
        st.session_state.admin_authed       = True
        st.session_state.admin_username     = _restored_user
        st.session_state.admin_session_token = _cookie_token
    else:
        # Token expired / revoked in DB — remove stale cookie
        _delete_session_cookie()


# ── Auth gate — login / forgot-password screens ───────────────────────────────

def _show_login() -> None:
    """Render login form.  Sets session_state + cookie on success."""
    from core.auth import check_login, create_session, bootstrap_admin_user

    bootstrap_admin_user()   # create DB row from secret if first time

    st.title("🔐 Admin Login")
    mode = st.radio("", ["Sign in", "Forgot password"], horizontal=True, key="auth_mode",
                    label_visibility="collapsed")

    if mode == "Sign in":
        with st.form("login_form", clear_on_submit=False):
            uname = st.text_input("Username", value="admin", key="login_uname")
            pwd   = st.text_input("Password", type="password", key="login_pwd")
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)

        if submitted:
            if not pwd:
                st.error("Please enter your password.")
            else:
                ok, err = check_login(pwd, uname)
                if ok:
                    token = create_session(uname)
                    st.session_state.admin_authed        = True
                    st.session_state.admin_username      = uname
                    st.session_state.admin_session_token = token
                    _write_session_cookie(token)
                    st.rerun()
                else:
                    st.error(err)

    else:  # Forgot password
        _show_forgot_password()


def _show_forgot_password() -> None:
    """Reset password using the ADMIN_RESET_CODE secret.

    The recovery code is a separate secret from ADMIN_PASSWORD.  Set it in
    Streamlit secrets as  ADMIN_RESET_CODE = "some-random-string".
    If not configured, the feature is disabled.
    """
    from core.auth import update_password, validate_new_password

    reset_code_correct = _get_secret("ADMIN_RESET_CODE")
    if not reset_code_correct:
        st.info(
            "Password reset is not configured.  "
            "Add an `ADMIN_RESET_CODE` secret in your Streamlit secrets to enable it."
        )
        return

    st.subheader("Reset Password")
    st.caption("Enter the recovery code from your Streamlit secrets, then choose a new password.")

    with st.form("forgot_pw_form", clear_on_submit=False):
        uname      = st.text_input("Username", value="admin", key="fp_uname")
        reset_code = st.text_input("Recovery code", type="password", key="fp_code",
                                   placeholder="Value of ADMIN_RESET_CODE secret")
        new_pw     = st.text_input("New password", type="password", key="fp_new")
        confirm_pw = st.text_input("Confirm new password", type="password", key="fp_confirm")
        submitted  = st.form_submit_button("Reset Password", type="primary", use_container_width=True)

    if submitted:
        # Validate recovery code (constant-time)
        import secrets as _sec
        if not _sec.compare_digest(reset_code.encode(), reset_code_correct.encode()):
            st.error("Incorrect recovery code.")
            return

        # Validate new password
        from core.auth import validate_new_password
        err = validate_new_password(new_pw, confirm_pw)
        if err:
            st.error(err)
            return

        db_err = update_password(uname, new_pw)
        if db_err:
            st.error(f"Failed to save: {db_err}")
        else:
            st.success("Password updated successfully.  Please sign in with your new password.")


if not st.session_state.get("admin_authed"):
    _show_login()
    st.stop()


# ── Logout (shown in the sidebar / top of page) ────────────────────────────────

with st.sidebar:
    _logged_user = st.session_state.get("admin_username", "admin")
    st.caption(f"Signed in as **{_logged_user}**")
    if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
        from core.auth import invalidate_session
        _tok = st.session_state.get("admin_session_token", "")
        invalidate_session(_tok)
        _delete_session_cookie()
        st.session_state.clear()
        st.rerun()


# ── Main admin UI ─────────────────────────────────────────────────────────────
st.title("📊 Admin Dashboard")

tab_logs, tab_docs, tab_add, tab_settings, tab_account, tab_debug = st.tabs([
    "📋 Logs", "📁 Manage Docs", "➕ Add Source",
    "⚙️ Settings", "🔑 Account", "🐛 Debug",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Logs
# ─────────────────────────────────────────────────────────────────────────────
with tab_logs:
    st.subheader("Query Logs")

    col_filter, col_limit, col_btn = st.columns([2, 1, 1])
    with col_filter:
        log_type_filter = st.selectbox(
            "Log type",
            options=["all", "unanswered", "feedback", "admin_action"],
            key="log_type_filter",
        )
    with col_limit:
        log_limit = st.number_input("Max rows", min_value=10, max_value=1000,
                                    value=200, step=10, key="log_limit")
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
                "⬇️ Download CSV", data=csv,
                file_name=f"logs_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

    st.divider()
    st.subheader("Local Fallback Logs")
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
# TAB: Manage Docs
# ─────────────────────────────────────────────────────────────────────────────
with tab_docs:
    st.subheader("Manage Policy Documents")

    try:
        from core.settings_store import get_enabled_sources
        _all_sources = get_enabled_sources()
    except Exception:
        _all_sources = ["company", "dubai_hr"]

    from config import get_settings as _get_settings
    _s = _get_settings()

    selected_source = st.selectbox(
        "Knowledge source", options=_all_sources, key="manage_docs_source",
    )

    _docs_dir = _s.docs_dir_for(selected_source)
    _db_dir   = _s.db_dir_for(selected_source)
    _docs_dir.mkdir(parents=True, exist_ok=True)

    # ── Upload ─────────────────────────────────────────────────────────────────
    st.markdown("#### Upload Files")
    uploaded = st.file_uploader(
        "Select policy files (PDF, DOCX, TXT, MD)",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key=f"uploader_{selected_source}",
    )

    if uploaded:
        _existing  = {f.name for f in _docs_dir.iterdir() if f.is_file()}
        _conflicts = [f.name for f in uploaded if f.name in _existing]

        if _conflicts and not st.session_state.get(f"overwrite_ok_{selected_source}"):
            st.warning(f"These files already exist and will be **overwritten**: {', '.join(_conflicts)}")
            if st.button("✅ Confirm overwrite", key=f"confirm_ow_{selected_source}"):
                st.session_state[f"overwrite_ok_{selected_source}"] = True
                st.rerun()
        else:
            if st.button("💾 Save Files", type="primary", key=f"save_files_{selected_source}"):
                from core.db_logger import log_admin_action
                saved, failed = [], []
                for uf in uploaded:
                    safe = _safe_filename(uf.name)
                    try:
                        (_docs_dir / safe).write_bytes(uf.read())
                        log_admin_action("upload", selected_source, safe)
                        saved.append(safe)
                    except Exception as exc:
                        failed.append(f"{safe}: {exc}")

                if saved:
                    st.success(f"Saved {len(saved)} file(s): {', '.join(saved)}")
                if failed:
                    st.error("Failed: " + "; ".join(failed))

                st.session_state.pop(f"overwrite_ok_{selected_source}", None)

                from core.rag_engine import build_source_index
                with st.spinner("Rebuilding index…"):
                    ok, msg = build_source_index(_s, selected_source)
                if ok:
                    st.success(f"Index rebuilt: {msg}")
                    log_admin_action("rebuild", selected_source)
                else:
                    st.error(f"Index rebuild failed: {msg}")
                st.cache_resource.clear()
                st.rerun()

    # ── Existing files ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Existing Files")

    _doc_files = sorted([
        f for f in _docs_dir.iterdir()
        if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}
    ]) if _docs_dir.exists() else []

    if not _doc_files:
        st.info(f"No documents in `{_docs_dir.name}/`.")
    else:
        st.caption(f"{len(_doc_files)} file(s) in `{_docs_dir.resolve()}`")
        for _f in _doc_files:
            col_name, col_size, col_del = st.columns([5, 1, 1])
            with col_name:
                st.markdown(f"📄 `{_f.name}`")
            with col_size:
                st.caption(f"{_f.stat().st_size // 1024} KB")
            with col_del:
                if st.button("🗑️", key=f"del_{selected_source}_{_f.name}", help="Delete"):
                    st.session_state[f"confirm_del_{selected_source}_{_f.name}"] = True

            if st.session_state.get(f"confirm_del_{selected_source}_{_f.name}"):
                st.warning(f"Delete `{_f.name}`?")
                col_y, col_n = st.columns(2)
                with col_y:
                    if st.button("Yes, delete", key=f"yes_del_{selected_source}_{_f.name}",
                                 type="primary"):
                        from core.db_logger import log_admin_action
                        try:
                            _f.unlink()
                            log_admin_action("delete", selected_source, _f.name)
                            st.session_state.pop(f"confirm_del_{selected_source}_{_f.name}", None)
                            st.success(f"Deleted `{_f.name}`.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Delete failed: {exc}")
                with col_n:
                    if st.button("Cancel", key=f"no_del_{selected_source}_{_f.name}"):
                        st.session_state.pop(f"confirm_del_{selected_source}_{_f.name}", None)
                        st.rerun()

    st.divider()
    if st.button("🔨 Rebuild Index Now", key=f"rebuild_{selected_source}",
                 use_container_width=True):
        from core.db_logger import log_admin_action
        from core.rag_engine import build_source_index
        with st.spinner("Building FAISS index…"):
            ok, msg = build_source_index(_s, selected_source)
        if ok:
            st.success(msg)
            log_admin_action("rebuild", selected_source)
            st.cache_resource.clear()
        else:
            st.error(msg)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Add Source
# ─────────────────────────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Add New Knowledge Source")
    st.caption("Creates a new source: docs folder → upload → index → register in Supabase.")

    new_key     = st.text_input("Source key (slug)", placeholder="e.g. labour_law_ksa",
                                help="Lowercase letters, digits, underscores. Starts with a letter.",
                                key="new_source_key")
    new_display = st.text_input("Display name", placeholder="e.g. Saudi Labour Law",
                                key="new_source_display")

    from core.settings_store import is_valid_source_key
    if new_key:
        if is_valid_source_key(new_key):
            st.success(f"✅ Key `{new_key}` is valid.")
        else:
            st.error("Invalid key — lowercase letters, digits, underscores only; must start with a letter.")

    new_files = st.file_uploader(
        "Initial documents (optional)",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key="new_source_files",
    )

    if st.button("➕ Create Source", type="primary", key="create_source_btn"):
        from config import get_settings as _gs2
        from core.settings_store import get_enabled_sources, register_source
        from core.db_logger import log_admin_action

        _s2 = _gs2()

        if not new_key:
            st.error("Please enter a source key.")
        elif not is_valid_source_key(new_key):
            st.error("Invalid source key format.")
        elif not new_display.strip():
            st.error("Please enter a display name.")
        else:
            existing = get_enabled_sources()
            if new_key in existing:
                st.warning(f"Source `{new_key}` is already registered.")
            else:
                _new_docs = _s2.docs_dir_for(new_key)
                _new_docs.mkdir(parents=True, exist_ok=True)

                _saved = []
                for uf in (new_files or []):
                    safe = _safe_filename(uf.name)
                    try:
                        (_new_docs / safe).write_bytes(uf.read())
                        _saved.append(safe)
                    except Exception as exc:
                        st.error(f"Failed to save {uf.name}: {exc}")

                if _saved:
                    from core.rag_engine import build_source_index
                    with st.spinner("Building index…"):
                        _ok, _msg = build_source_index(_s2, new_key)
                    if _ok:
                        st.success(f"Index built: {_msg}")
                    else:
                        st.warning(f"Index build failed (rebuild later): {_msg}")

                err = register_source(new_key)
                if err:
                    st.error(f"Failed to register: {err}")
                else:
                    log_admin_action("add_source", new_key, new_display)
                    st.success(f"Source `{new_key}` ({new_display}) created!")
                    st.info("It will appear in the main app after the 60-second settings cache expires.")
                    st.cache_data.clear()
                    st.cache_resource.clear()
                    for k in ("new_source_key", "new_source_display"):
                        st.session_state.pop(k, None)
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Settings
# ─────────────────────────────────────────────────────────────────────────────
with tab_settings:
    st.subheader("Source Visibility")
    st.caption("Toggle which knowledge sources end users can select.")

    try:
        from core.settings_store import get_enabled_sources, set_enabled_sources
        _all_src = get_enabled_sources()

        _new_enabled: list[str] = []
        for _src in _all_src:
            _icon = "🏢" if _src == "company" else "🇦🇪" if _src == "dubai_hr" else "📋"
            if st.toggle(f"{_icon} {_src.replace('_', ' ').title()}",
                         value=True, key=f"toggle_{_src}"):
                _new_enabled.append(_src)

        if st.button("💾 Save Settings", type="primary", key="save_settings_btn"):
            if not _new_enabled:
                st.warning("At least one source must remain enabled.")
            else:
                _err = set_enabled_sources(_new_enabled)
                if _err:
                    st.error(f"Error: {_err}")
                else:
                    st.success(f"Saved: {_new_enabled}")

    except Exception as exc:
        st.error(f"Settings error: {exc}")

    st.divider()
    st.subheader("FAISS Index Management")

    try:
        from core.settings_store import get_enabled_sources as _ges3
        from config import get_settings as _gs3
        _cfg3 = _gs3()
        _srcs3 = _ges3()
        _idx_cols = st.columns(min(len(_srcs3), 3))
        for _ci, _src3 in enumerate(_srcs3):
            with _idx_cols[_ci % 3]:
                if st.button(f"🗑️ Clear {_src3}", key=f"clear_idx_{_src3}",
                             use_container_width=True):
                    import shutil
                    _d = _cfg3.db_dir_for(_src3)
                    if _d.exists():
                        shutil.rmtree(_d)
                        st.success(f"{_src3} index cleared.")
                    else:
                        st.info(f"No index for {_src3}.")
    except Exception as exc:
        st.error(f"Index management error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Account  (change password)
# ─────────────────────────────────────────────────────────────────────────────
with tab_account:
    st.subheader("Change Password")
    st.caption("Update the admin password stored in the database (bcrypt-hashed).")

    from core.auth import check_login as _check_login, update_password, validate_new_password

    _logged_user = st.session_state.get("admin_username", "admin")

    with st.form("change_pw_form", clear_on_submit=True):
        current_pw  = st.text_input("Current password", type="password", key="cp_current")
        new_pw_1    = st.text_input("New password (min 8 chars)", type="password", key="cp_new1")
        new_pw_2    = st.text_input("Confirm new password", type="password", key="cp_new2")
        save_pw_btn = st.form_submit_button("🔒 Save New Password", type="primary",
                                            use_container_width=True)

    if save_pw_btn:
        if not current_pw:
            st.error("Please enter your current password.")
        else:
            _ok, _err = _check_login(current_pw, _logged_user)
            if not _ok:
                st.error(f"Current password incorrect: {_err}")
            else:
                _val_err = validate_new_password(new_pw_1, new_pw_2)
                if _val_err:
                    st.error(_val_err)
                else:
                    _save_err = update_password(_logged_user, new_pw_1)
                    if _save_err:
                        st.error(f"Failed to save: {_save_err}")
                    else:
                        st.success("Password updated successfully.")

    st.divider()
    st.subheader("Active Sessions")
    if st.button("🔍 Show My Sessions", key="show_sessions_btn"):
        try:
            from core.db_logger import _get_client
            c = _get_client()
            if c:
                resp = (
                    c.table("admin_sessions")
                    .select("id,username,created_at,expires_at")
                    .eq("username", _logged_user)
                    .order("created_at", desc=True)
                    .execute()
                )
                if resp.data:
                    import pandas as pd
                    df = pd.DataFrame(resp.data)
                    # Mask token — show only first 8 chars
                    df["id"] = df["id"].str[:8] + "…"
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("No active sessions found.")
            else:
                st.warning("Database not available.")
        except Exception as exc:
            st.error(f"Error: {exc}")

    if st.button("🚫 Revoke All Other Sessions", key="revoke_others_btn"):
        try:
            from core.db_logger import _get_client
            c = _get_client()
            if c:
                _current = st.session_state.get("admin_session_token", "")
                # Delete all sessions for this user except the current one
                c.table("admin_sessions").delete().eq(
                    "username", _logged_user
                ).neq("id", _current).execute()
                st.success("All other sessions revoked.")
        except Exception as exc:
            st.error(f"Error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Debug
# ─────────────────────────────────────────────────────────────────────────────
with tab_debug:
    st.subheader("Runtime Diagnostics")

    if st.button("🔍 Run Diagnostics", type="primary", key="run_diag_btn"):
        results: list[tuple[str, str, str]] = []

        results.append(("Python",     "✅", sys.version.split()[0]))
        results.append(("Streamlit",  "✅", st.__version__))

        for sec_key in ("GROQ_API_KEY", "SUPABASE_URL", "SUPABASE_KEY",
                        "ADMIN_PASSWORD", "ADMIN_RESET_CODE"):
            val = _get_secret(sec_key)
            results.append((
                f"Secret: {sec_key}",
                "✅" if val else "⚠️",
                f"{val[:6]}…" if val else "not set",
            ))

        try:
            from core.db_logger import _get_client, get_logging_mode
            client = _get_client()
            results.append(("Supabase client", "✅" if client else "⚠️", get_logging_mode()))
        except Exception as exc:
            results.append(("Supabase client", "❌", str(exc)))

        try:
            from core.auth import get_admin_user
            u = get_admin_user("admin")
            results.append((
                "admin_users row",
                "✅" if u else "⚠️",
                "exists" if u else "missing — will be created on first login",
            ))
        except Exception as exc:
            results.append(("admin_users row", "❌", str(exc)))

        try:
            import bcrypt
            results.append(("bcrypt", "✅", bcrypt.__version__))
        except Exception as exc:
            results.append(("bcrypt", "❌", str(exc)))

        try:
            from langchain_community.embeddings import FastEmbedEmbeddings  # noqa
            results.append(("FastEmbedEmbeddings", "✅", "ok"))
        except Exception as exc:
            results.append(("FastEmbedEmbeddings", "❌", str(exc)))

        try:
            from config import get_settings
            from core.settings_store import get_enabled_sources
            _s3   = get_settings()
            _srcs = get_enabled_sources()
            results.append(("BASE_DIR",        "✅", str(_s3.docs_dir.parent.resolve())))
            results.append(("Enabled sources", "✅", str(_srcs)))
            for _src in _srcs:
                _em, _det = _index_status(_s3.db_dir_for(_src), _s3.docs_dir_for(_src))
                results.append((f"Index: {_src}", _em, _det))
        except Exception as exc:
            results.append(("Config / sources", "❌", str(exc)))

        import pandas as pd
        df = pd.DataFrame(results, columns=["Check", "Status", "Detail"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Build Missing Indexes")
    try:
        from config import get_settings as _gs4
        from core.settings_store import get_enabled_sources as _ges4
        _s4   = _gs4()
        _srcs4 = _ges4()
        _bcols = st.columns(min(len(_srcs4), 3))
        for _bi, _bsrc in enumerate(_srcs4):
            with _bcols[_bi % 3]:
                if st.button(f"🔨 Build {_bsrc}", key=f"build_{_bsrc}",
                             use_container_width=True):
                    from core.db_logger import log_admin_action
                    from core.rag_engine import build_source_index
                    with st.spinner(f"Building {_bsrc}…"):
                        _bok, _bmsg = build_source_index(_s4, _bsrc)
                    if _bok:
                        st.success(_bmsg)
                        log_admin_action("rebuild", _bsrc)
                        st.cache_resource.clear()
                    else:
                        st.error(_bmsg)
    except Exception as exc:
        st.error(f"Build error: {exc}")

    st.divider()
    st.subheader("Session State")
    if st.button("👁️ Show Session State", key="show_session"):
        safe = {k: v for k, v in st.session_state.items()
                if "password" not in k.lower() and "token" not in k.lower()}
        st.json(safe)

    st.divider()
    st.subheader("Environment Variables")
    if st.button("👁️ Show Env Vars", key="show_env"):
        safe_keys = ["STREAMLIT_SERVER_PORT", "HOME", "PATH", "PYTHONPATH", "HOSTNAME"]
        st.json({k: os.environ.get(k, "(not set)") for k in safe_keys})
