"""
Admin Dashboard — persistent-session, password-gated control panel.

Auth architecture:
  - st.context.cookies reads the "admin_session" cookie from HTTP request headers
    on every render (native Streamlit ≥ 1.37, no delay).
  - extra-streamlit-components CookieManager sets / deletes the cookie via a
    hidden JS iframe (write-only — no timing-read dependency).
  - Session tokens (64-hex, 256-bit) live in admin_sessions Supabase table.
  - Passwords stored as bcrypt hashes in admin_users; plain ADMIN_PASSWORD
    secret auto-migrates on first login.

RBAC:
  super_admin (4) → admin (3) → moderator (2) → user (1)
  Nav items are hidden for roles without the matching permission.
  Every privileged action enforces the matching permission server-side.
  Permissions stored in role_permissions Supabase table (migration 003).

Navigation (sidebar radio — only the selected section renders):
  Nav items are shown/hidden by permission; only selected section's Python runs.
  📋 Logs              (dashboard.logs)
  📁 Manage Docs       (documents.view)
  ➕ Add Source        (sources.view)
  ⚙️ Settings         (settings.view)
  👥 Users             (users.view)
  🔐 Roles             (roles.view)
  🔑 Account           (always visible)
  🐛 Debug             (dashboard.debug)
"""
from __future__ import annotations

import datetime
import os
import re
import shutil
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

_SESSION_COOKIE        = "admin_session"
_SESSION_TTL_DAYS      = 1   # default (no remember me)
_SESSION_TTL_DAYS_LONG = 30  # remember me

# ── RBAC level map (kept for user hierarchy checks — who can manage whom) ─────
_RLEVEL = {"super_admin": 4, "admin": 3, "moderator": 2, "user": 1}


# ── Cookie helpers ─────────────────────────────────────────────────────────────

def _read_session_cookie() -> str:
    try:
        return st.context.cookies.get(_SESSION_COOKIE, "")
    except Exception:
        return ""


def _write_session_cookie(token: str, remember: bool = False) -> None:
    if _cookie_writer is None:
        return
    try:
        days    = _SESSION_TTL_DAYS_LONG if remember else _SESSION_TTL_DAYS
        expires = datetime.datetime.now() + datetime.timedelta(days=days)
        _cookie_writer.set(_SESSION_COOKIE, token, expires_at=expires)
    except Exception as exc:
        st.warning(f"Could not persist session cookie: {exc}", icon="⚠️")


def _delete_session_cookie() -> None:
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
    if not docs_dir.exists():
        return "❌", f"Docs folder missing: {docs_dir.resolve()}"
    supported = [f for f in docs_dir.iterdir()
                 if f.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}]
    if not supported:
        return "⚠️", f"No supported documents in {docs_dir.resolve()}"
    if not (db_dir / "index.faiss").exists():
        return "⚠️", f"Index not built yet — {len(supported)} doc(s) ready."
    return "✅", f"{(db_dir / 'index.faiss').resolve()} ({len(supported)} docs)"


def _show_403(perm: str = "") -> None:
    """Render a 403 block. Call inside a tab when permission check fails."""
    _cur = st.session_state.get("admin_role", "unknown")
    _detail = f"Permission required: `{perm}`.  " if perm else ""
    st.error(
        f"🚫 **403 Access Denied**\n\n"
        f"{_detail}Your current role: **{_cur}**."
    )


# ── Session restoration ────────────────────────────────────────────────────────

_cookie_token = _read_session_cookie()

if _cookie_token and not st.session_state.get("admin_authed"):
    from core.auth import verify_session as _vs, get_user_role as _gur
    from core.rbac import load_session_permissions as _lsp
    _restored_user = _vs(_cookie_token)
    if _restored_user:
        _restored_role = _gur(_restored_user)
        st.session_state.admin_authed        = True
        st.session_state.admin_username      = _restored_user
        st.session_state.admin_session_token = _cookie_token
        st.session_state.admin_role          = _restored_role
        st.session_state.user_permissions    = _lsp(_restored_role)
    else:
        _delete_session_cookie()

# Backfill permissions for sessions that predate the RBAC rollout.
# Without this, any active session from before migration 003 would have
# user_permissions absent → _hp() always False → all tabs hidden.
if st.session_state.get("admin_authed") and "user_permissions" not in st.session_state:
    from core.auth import get_user_role as _gur_bf
    from core.rbac import load_session_permissions as _lsp_bf
    _bf_role = st.session_state.get("admin_role") or _gur_bf(
        st.session_state.get("admin_username", "admin")
    )
    st.session_state.admin_role        = _bf_role
    st.session_state.user_permissions  = _lsp_bf(_bf_role)


# ── Auth gate — login / forgot-password ────────────────────────────────────────

def _show_login() -> None:
    from core.auth import check_login, create_session, bootstrap_admin_user, get_user_role
    from core.rbac import load_session_permissions as _lsp2

    bootstrap_admin_user()

    st.title("🔐 Admin Login")
    mode = st.radio("Login mode", ["Sign in", "Forgot password"], horizontal=True,
                    key="auth_mode", label_visibility="collapsed")

    if mode == "Sign in":
        with st.form("login_form", clear_on_submit=False):
            uname     = st.text_input("Username", value="admin", key="login_uname")
            pwd       = st.text_input("Password", type="password", key="login_pwd")
            remember  = st.checkbox("Remember me for 30 days", value=True,
                                    key="login_remember")
            submitted = st.form_submit_button("Login", type="primary",
                                              use_container_width=True)

        if submitted:
            if not pwd:
                st.error("Please enter your password.")
            else:
                ok, err = check_login(pwd, uname)
                if ok:
                    ttl   = 30 * 24 if remember else 24   # hours
                    token = create_session(uname, ttl_hours=ttl)
                    role  = get_user_role(uname)
                    st.session_state.admin_authed        = True
                    st.session_state.admin_username      = uname
                    st.session_state.admin_session_token = token
                    st.session_state.admin_role          = role
                    st.session_state.user_permissions    = _lsp2(role)
                    _write_session_cookie(token, remember=remember)
                    st.rerun()
                else:
                    st.error(err)
    else:
        _show_forgot_password()


def _show_forgot_password() -> None:
    from core.auth import update_password, validate_new_password
    import secrets as _sec

    reset_code_correct = _get_secret("ADMIN_RESET_CODE")
    if not reset_code_correct:
        st.info(
            "Password reset is not configured.  "
            "Add an `ADMIN_RESET_CODE` secret to enable it."
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
        submitted  = st.form_submit_button("Reset Password", type="primary",
                                           use_container_width=True)

    if submitted:
        if not _sec.compare_digest(reset_code.encode(), reset_code_correct.encode()):
            st.error("Incorrect recovery code.")
            return
        err = validate_new_password(new_pw, confirm_pw)
        if err:
            st.error(err)
            return
        db_err = update_password(uname, new_pw)
        if db_err:
            st.error(f"Failed to save: {db_err}")
        else:
            st.success("Password updated. Please sign in with your new password.")


if not st.session_state.get("admin_authed"):
    _show_login()
    st.stop()


# ── Navigation (sidebar) ──────────────────────────────────────────────────────

from core.rbac import has_permission as _hp  # noqa: E402

_TABS_DEF = [
    ("📋 Logs",        "logs",     "dashboard.logs"),
    ("📁 Manage Docs", "docs",     "documents.view"),
    ("➕ Add Source",  "add",      "sources.view"),
    ("⚙️ Settings",   "settings", "settings.view"),
    ("👥 Users",       "users",    "users.view"),
    ("🔐 Roles",       "roles",    "roles.view"),
    ("🔑 Account",     "account",  None),
    ("🐛 Debug",       "debug",    "dashboard.debug"),
]

_vis_defs   = [(lbl, key, perm) for lbl, key, perm in _TABS_DEF
               if perm is None or _hp(perm)]
_nav_labels = [lbl for lbl, _, _ in _vis_defs]
_nav_keys   = [key for _, key, _ in _vis_defs]

with st.sidebar:
    _logged_user = st.session_state.get("admin_username", "admin")
    _logged_role = st.session_state.get("admin_role", "admin")
    _ROLE_BADGE  = {"super_admin": "🔴", "admin": "🟠", "moderator": "🟡", "user": "🟢"}
    st.caption(
        f"Signed in as **{_logged_user}**  \n"
        f"{_ROLE_BADGE.get(_logged_role, '⚪')} `{_logged_role}`"
    )
    st.divider()
    if _nav_labels:
        _prev        = st.session_state.get("admin_nav_key", _nav_keys[0])
        _default_idx = _nav_keys.index(_prev) if _prev in _nav_keys else 0
        _sel_nav_lbl = st.radio(
            "Navigation",
            options=_nav_labels,
            index=_default_idx,
            key="admin_nav",
            label_visibility="collapsed",
        )
        _sel_nav = _nav_keys[_nav_labels.index(_sel_nav_lbl)]
        st.session_state["admin_nav_key"] = _sel_nav
    else:
        _sel_nav = ""
    st.divider()
    if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
        from core.auth import invalidate_session
        invalidate_session(st.session_state.get("admin_session_token", ""))
        _delete_session_cookie()
        st.session_state.clear()
        st.rerun()


# ── Main admin UI ──────────────────────────────────────────────────────────────
st.title("📊 Admin Dashboard")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Logs
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "logs":
    with st.container():
        if not _hp("dashboard.logs"):
            _show_403("dashboard.logs")
        else:
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
                fetch_btn = st.button("🔄 Fetch Logs", type="primary",
                                      use_container_width=True)

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
if _sel_nav == "docs":
    with st.container():
        if not _hp("documents.view"):
            _show_403("documents.view")
        else:
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

            # ── Upload ──────────────────────────────────────────────────────
            if _hp("documents.create"):
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
                        st.warning(
                            f"These files already exist and will be **overwritten**: "
                            f"{', '.join(_conflicts)}"
                        )
                        if st.button("✅ Confirm overwrite", key=f"confirm_ow_{selected_source}"):
                            st.session_state[f"overwrite_ok_{selected_source}"] = True
                            st.rerun()
                    else:
                        if st.button("💾 Save Files", type="primary",
                                     key=f"save_files_{selected_source}"):
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

                            if _hp("documents.rebuild"):
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
                        if _hp("documents.delete"):
                            if st.button("🗑️", key=f"del_{selected_source}_{_f.name}",
                                         help="Delete"):
                                st.session_state[f"confirm_del_{selected_source}_{_f.name}"] = True

                    if _hp("documents.delete") and st.session_state.get(
                        f"confirm_del_{selected_source}_{_f.name}"
                    ):
                        st.warning(f"Delete `{_f.name}`?")
                        col_y, col_n = st.columns(2)
                        with col_y:
                            if st.button("Yes, delete",
                                         key=f"yes_del_{selected_source}_{_f.name}",
                                         type="primary"):
                                from core.db_logger import log_admin_action
                                try:
                                    _f.unlink()
                                    log_admin_action("delete", selected_source, _f.name)
                                    st.session_state.pop(
                                        f"confirm_del_{selected_source}_{_f.name}", None
                                    )
                                    st.success(f"Deleted `{_f.name}`.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Delete failed: {exc}")
                        with col_n:
                            if st.button("Cancel", key=f"no_del_{selected_source}_{_f.name}"):
                                st.session_state.pop(
                                    f"confirm_del_{selected_source}_{_f.name}", None
                                )
                                st.rerun()

            st.divider()
            if _hp("documents.rebuild"):
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
if _sel_nav == "add":
    with st.container():
        if not _hp("sources.view"):
            _show_403("sources.view")
        else:
            # ── Add Source ────────────────────────────────────────────────────
            if _hp("sources.add"):
                st.subheader("Add New Knowledge Source")
                st.caption("Creates a new source: docs folder → upload → index → register in Supabase.")

                new_key     = st.text_input(
                    "Source key (slug)", placeholder="e.g. labour_law_ksa",
                    help="Lowercase letters, digits, underscores. Starts with a letter.",
                    key="new_source_key",
                )
                new_display = st.text_input("Display name", placeholder="e.g. Saudi Labour Law",
                                            key="new_source_display")

                from core.settings_store import is_valid_source_key
                if new_key:
                    if is_valid_source_key(new_key):
                        st.success(f"✅ Key `{new_key}` is valid.")
                    else:
                        st.error("Invalid key — lowercase letters, digits, underscores only; "
                                 "must start with a letter.")

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
                                st.info("It will appear after the 60-second settings cache expires.")
                                st.cache_data.clear()
                                st.cache_resource.clear()
                                for k in ("new_source_key", "new_source_display"):
                                    st.session_state.pop(k, None)
                                st.rerun()

            # ── Delete Source ─────────────────────────────────────────────────
            if _hp("sources.delete"):
                st.divider()
                st.subheader("🗑️ Delete Source")
                st.caption(
                    "Permanently remove a knowledge source, its documents folder, its FAISS index, "
                    "and its Supabase entry. **Cannot be undone.**"
                )

                try:
                    from core.settings_store import get_enabled_sources as _ges_del
                    _del_sources = _ges_del()
                except Exception:
                    _del_sources = []

                if not _del_sources:
                    st.info("No sources registered yet.")
                else:
                    _del_src = st.selectbox(
                        "Source to delete",
                        options=_del_sources,
                        key="del_src_select",
                        format_func=lambda k: f"{k}  ({k.replace('_', ' ').title()})",
                    )

                    from config import get_settings as _gs_del
                    _cfg_del   = _gs_del()
                    _del_docs  = _cfg_del.docs_dir_for(_del_src)
                    _del_index = _cfg_del.db_dir_for(_del_src)

                    _doc_files_del: list[Path] = []
                    if _del_docs.exists():
                        _doc_files_del = [
                            f for f in _del_docs.iterdir()
                            if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}
                        ]
                    _idx_exists = (_del_index / "index.faiss").exists()

                    st.markdown(
                        f"**What will be permanently deleted for `{_del_src}`:**\n"
                        f"- 📁 Docs folder: `{_del_docs.resolve()}`\n"
                        f"  - {len(_doc_files_del)} document(s): "
                        f"{', '.join(f.name for f in _doc_files_del) or '*(none)*'}\n"
                        f"- 🗄️ FAISS dir: `{_del_index.resolve()}` "
                        f"{'*(exists)*' if _idx_exists else '*(not present)*'}\n"
                        f"- 🔗 Supabase `enabled_sources` entry",
                    )

                    _remaining = [s for s in _del_sources if s != _del_src]
                    if not _remaining:
                        st.error(
                            "⛔ Cannot delete — this is the **only** source. "
                            "Add another source first."
                        )
                    else:
                        st.markdown(
                            "<style>.danger-btn button{background:#c0392b!important;"
                            "color:#fff!important;border-color:#c0392b!important;}</style>",
                            unsafe_allow_html=True,
                        )
                        _show_confirm = st.session_state.get("del_confirm_open") == _del_src

                        col_del_btn, _ = st.columns([1, 3])
                        with col_del_btn:
                            with st.container(key="danger-btn"):
                                if st.button(
                                    f"🗑️ Delete `{_del_src}`",
                                    key="del_src_open_btn",
                                    type="primary",
                                    use_container_width=True,
                                ):
                                    st.session_state["del_confirm_open"] = _del_src
                                    st.session_state.pop("del_confirm_done", None)
                                    st.rerun()

                        if _show_confirm:
                            st.warning(
                                f"⚠️ You are about to **permanently delete** `{_del_src}` "
                                f"and all its data.",
                                icon="🚨",
                            )

                            with st.form("del_src_confirm_form", clear_on_submit=True):
                                st.markdown("**Step 1 of 2** — Type the source key to confirm:")
                                _typed_key = st.text_input(
                                    f"Type `{_del_src}` to confirm",
                                    key="del_confirm_key_input",
                                    placeholder=_del_src,
                                )
                                st.markdown("**Step 2 of 2** — Re-enter your admin password:")
                                _confirm_pwd = st.text_input(
                                    "Admin password",
                                    type="password",
                                    key="del_confirm_pwd_input",
                                )
                                col_yes, col_cancel = st.columns(2)
                                with col_yes:
                                    _confirmed = st.form_submit_button(
                                        "🗑️ Confirm — Delete Source",
                                        type="primary",
                                        use_container_width=True,
                                    )
                                with col_cancel:
                                    _cancelled = st.form_submit_button(
                                        "Cancel", use_container_width=True,
                                    )

                            if _cancelled:
                                st.session_state.pop("del_confirm_open", None)
                                st.rerun()

                            if _confirmed:
                                if _typed_key != _del_src:
                                    st.error(
                                        f"Key mismatch: typed `{_typed_key}` "
                                        f"but source key is `{_del_src}`. Aborted."
                                    )
                                else:
                                    from core.auth import check_login as _ck_del
                                    _ok_del, _err_del = _ck_del(
                                        _confirm_pwd,
                                        st.session_state.get("admin_username", "admin"),
                                    )
                                    if not _ok_del:
                                        st.error("Incorrect admin password. Deletion aborted.")
                                    else:
                                        _del_errors: list[str] = []
                                        _del_log_parts: list[str] = []

                                        with st.spinner(f"Deleting `{_del_src}`…"):
                                            try:
                                                if _del_docs.exists():
                                                    _del_log_parts.append(
                                                        f"docs_folder={_del_docs.name} "
                                                        f"({len(_doc_files_del)} files)"
                                                    )
                                                    shutil.rmtree(_del_docs)
                                                else:
                                                    _del_log_parts.append("docs_folder=missing")
                                            except Exception as _exc:
                                                _del_errors.append(f"Docs folder: {_exc}")

                                            try:
                                                if _del_index.exists():
                                                    _del_log_parts.append(
                                                        f"faiss_dir={_del_index.name}"
                                                    )
                                                    shutil.rmtree(_del_index)
                                                else:
                                                    _del_log_parts.append("faiss_dir=missing")
                                            except Exception as _exc:
                                                _del_errors.append(f"FAISS dir: {_exc}")

                                            try:
                                                from core.settings_store import set_enabled_sources
                                                _sb_err = set_enabled_sources(_remaining)
                                                if _sb_err:
                                                    _del_errors.append(f"Supabase: {_sb_err}")
                                                else:
                                                    _del_log_parts.append("supabase_entry=removed")
                                            except Exception as _exc:
                                                _del_errors.append(f"Supabase: {_exc}")

                                            try:
                                                from core.db_logger import log_admin_action
                                                log_admin_action(
                                                    "delete_source",
                                                    _del_src,
                                                    "; ".join(_del_log_parts),
                                                )
                                            except Exception:
                                                pass

                                        if _del_errors:
                                            st.error(
                                                "Deletion completed with errors:\n"
                                                + "\n".join(f"- {e}" for e in _del_errors)
                                            )
                                        else:
                                            st.success(
                                                f"✅ Source `{_del_src}` deleted. "
                                                f"Remaining: {_remaining}"
                                            )

                                        st.cache_data.clear()
                                        st.cache_resource.clear()
                                        st.session_state.pop("del_confirm_open", None)
                                        st.rerun()

            if not _hp("sources.add") and not _hp("sources.delete"):
                st.info("You have view-only access to sources.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Settings
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "settings":
    with st.container():
        if not _hp("settings.view"):
            _show_403("settings.view")
        else:
            st.subheader("Source Visibility")
            st.caption("Toggle which knowledge sources end users can select.")

            try:
                from core.settings_store import get_enabled_sources, set_enabled_sources
                _all_src = get_enabled_sources()

                _new_enabled: list[str] = []
                for _src in _all_src:
                    _icon = "🏢" if _src == "company" else "🇦🇪" if _src == "dubai_hr" else "📋"
                    if st.toggle(f"{_icon} {_src.replace('_', ' ').title()}",
                                 value=True, key=f"toggle_{_src}",
                                 disabled=not _hp("settings.edit")):
                        _new_enabled.append(_src)

                if _hp("settings.edit"):
                    if st.button("💾 Save Settings", type="primary", key="save_settings_btn"):
                        if not _new_enabled:
                            st.warning("At least one source must remain enabled.")
                        else:
                            _err = set_enabled_sources(_new_enabled)
                            if _err:
                                st.error(f"Error: {_err}")
                            else:
                                st.success(f"Saved: {_new_enabled}")
                else:
                    st.button("💾 Save Settings", disabled=True, key="save_settings_disabled")
                    st.caption("⚠️ You have view-only access to settings.")

            except Exception as exc:
                st.error(f"Settings error: {exc}")

            if _hp("settings.edit"):
                st.divider()
                st.subheader("FAISS Index Management")

                try:
                    from core.settings_store import get_enabled_sources as _ges3
                    from config import get_settings as _gs3
                    _cfg3  = _gs3()
                    _srcs3 = _ges3()
                    _idx_cols = st.columns(min(len(_srcs3), 3))
                    for _ci, _src3 in enumerate(_srcs3):
                        with _idx_cols[_ci % 3]:
                            _confirm_key = f"confirm_clear_{_src3}"
                            if not st.session_state.get(_confirm_key):
                                if st.button(f"🗑️ Clear {_src3}", key=f"clear_idx_{_src3}",
                                             use_container_width=True):
                                    st.session_state[_confirm_key] = True
                                    st.rerun()
                            else:
                                st.warning(f"Delete the **{_src3}** FAISS index? This cannot be undone.")
                                _col_y, _col_n = st.columns(2)
                                with _col_y:
                                    if st.button("Yes, delete", key=f"clear_idx_yes_{_src3}",
                                                 type="primary", use_container_width=True):
                                        _d = _cfg3.db_dir_for(_src3)
                                        if _d.exists():
                                            shutil.rmtree(_d)
                                            st.success(f"{_src3} index cleared.")
                                        else:
                                            st.info(f"No index for {_src3}.")
                                        st.session_state.pop(_confirm_key, None)
                                        st.rerun()
                                with _col_n:
                                    if st.button("Cancel", key=f"clear_idx_no_{_src3}",
                                                 use_container_width=True):
                                        st.session_state.pop(_confirm_key, None)
                                        st.rerun()
                except Exception as exc:
                    st.error(f"Index management error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Users
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "users":
    with st.container():
        from core.auth import (
            VALID_ROLES as _VALID_ROLES,
            can_manage_user as _can_manage,
            get_all_users as _get_all_users,
            create_admin_user as _create_admin_user,
            update_admin_user as _update_admin_user,
            delete_admin_user as _delete_admin_user,
            force_logout_user as _force_logout_user,
            update_password as _upd_pw,
            validate_new_password as _val_pw,
        )
        from core.db_logger import log_admin_action as _log_um

        _cur_role = st.session_state.get("admin_role") or "user"
        _cur_user = st.session_state.get("admin_username", "admin")

        if not _hp("users.view"):
            _show_403("users.view")
        else:
            # ── Stats ─────────────────────────────────────────────────────────
            _all_users = _get_all_users()
            _total     = len(_all_users)
            _active    = sum(1 for u in _all_users if u.get("is_active", True))
            _by_role: dict[str, int] = {}
            for _u0 in _all_users:
                _r0 = _u0.get("role", "admin")
                _by_role[_r0] = _by_role.get(_r0, 0) + 1
            _role_summary = "  ·  ".join(f"{r}:{n}" for r, n in _by_role.items()) or "—"

            _sm1, _sm2, _sm3, _sm4 = st.columns(4)
            _sm1.metric("Total Users", _total)
            _sm2.metric("Active", _active)
            _sm3.metric("Disabled", _total - _active)
            _sm4.metric("By Role", _role_summary)

            st.divider()

            # ── Create User ───────────────────────────────────────────────────
            if _hp("users.create"):
                with st.expander("➕ Create New User"):
                    with st.form("create_user_form", clear_on_submit=True):
                        _cu_uname   = st.text_input("Username", key="cu_uname")
                        _cu_display = st.text_input("Display Name (optional)", key="cu_display")
                        _cu_email   = st.text_input("Email (optional)", key="cu_email")
                        _cu_pw      = st.text_input("Password", type="password", key="cu_pw")
                        _cu_pw2     = st.text_input("Confirm Password", type="password",
                                                    key="cu_pw2")
                        _cu_role_opts = (
                            list(_VALID_ROLES) if _cur_role == "super_admin"
                            else [r for r in _VALID_ROLES
                                  if r not in ("super_admin", "admin")]
                        )
                        if _hp("users.assign_roles"):
                            _cu_role = st.selectbox("Role", options=_cu_role_opts, key="cu_role")
                        else:
                            _cu_role = _cu_role_opts[-1] if _cu_role_opts else "user"
                            st.text_input("Role", value=_cu_role, disabled=True, key="cu_role_ro")
                        _cu_sub = st.form_submit_button("Create User", type="primary",
                                                         use_container_width=True)

                    if _cu_sub:
                        _pw_err = _val_pw(_cu_pw, _cu_pw2)
                        if not _cu_uname:
                            st.error("Username is required.")
                        elif _pw_err:
                            st.error(_pw_err)
                        else:
                            _cerr = _create_admin_user(_cu_uname, _cu_pw, _cu_role,
                                                       _cu_email, _cu_display)
                            if _cerr:
                                st.error(f"Failed: {_cerr}")
                            else:
                                _log_um("create_user", _cu_uname, _cu_role)
                                st.success(
                                    f"User **{_cu_uname}** created with role `{_cu_role}`."
                                )
                                st.rerun()

            st.divider()

            # ── User List ─────────────────────────────────────────────────────
            st.subheader("User List")

            _col_srch, _col_rfilt = st.columns([3, 1])
            with _col_srch:
                _usr_search = st.text_input(
                    "Search", key="um_search",
                    placeholder="Search username or email…",
                    label_visibility="collapsed",
                )
            with _col_rfilt:
                _role_filt = st.selectbox(
                    "Role", options=["all"] + list(_VALID_ROLES),
                    key="um_role_filter", label_visibility="collapsed",
                )

            _filtered_users = _all_users
            if _usr_search:
                _q = _usr_search.lower()
                _filtered_users = [
                    u for u in _filtered_users
                    if _q in u.get("username", "").lower()
                    or _q in (u.get("email") or "").lower()
                    or _q in (u.get("display_name") or "").lower()
                ]
            if _role_filt != "all":
                _filtered_users = [u for u in _filtered_users if u.get("role") == _role_filt]

            if not _filtered_users:
                st.info("No users found.")

            _role_badge = {
                "super_admin": "🔴 super_admin",
                "admin":       "🟠 admin",
                "moderator":   "🟡 moderator",
                "user":        "🟢 user",
            }

            for _usr in _filtered_users:
                _un     = _usr["username"]
                _ur     = _usr.get("role", "admin")
                _ua     = _usr.get("is_active", True)
                _uemail = _usr.get("email") or ""
                _udisp  = _usr.get("display_name") or ""
                _ull    = str(_usr.get("last_login_at") or "Never")[:19]
                _is_self   = (_un == _cur_user)
                _hier_ok   = _can_manage(_cur_role, _ur) and not _is_self

                # Permission flags for individual actions
                _perm_edit   = _hp("users.edit")          and _hier_ok
                _perm_toggle = (_hp("users.disable") or _hp("users.enable")) and _hier_ok
                _perm_reset  = _hp("users.reset_password") and _hier_ok
                _perm_delete = _hp("users.delete")         and _hier_ok
                _manageable  = any([_perm_edit, _perm_toggle, _perm_reset, _perm_delete])

                with st.container():
                    _lc, _rc = st.columns([3, 2])
                    with _lc:
                        _badge  = _role_badge.get(_ur, f"⚪ {_ur}")
                        _status = "✅" if _ua else "🚫 disabled"
                        st.markdown(f"**{_un}** &nbsp; {_badge} &nbsp; {_status}")
                        _meta = "  ·  ".join(filter(None, [_udisp, _uemail]))
                        if _meta:
                            st.caption(_meta)
                        st.caption(f"Last login: {_ull}")
                    with _rc:
                        if _manageable:
                            _bc1, _bc2, _bc3, _bc4 = st.columns(4)
                            if _perm_edit:
                                with _bc1:
                                    if st.button("✏️", key=f"um_edit_{_un}", help="Edit"):
                                        st.session_state[f"um_action_{_un}"] = "edit"
                            if _perm_toggle:
                                with _bc2:
                                    _thelp = "Disable" if _ua else "Enable"
                                    _ticon = "🚫" if _ua else "✅"
                                    if st.button(_ticon, key=f"um_toggle_{_un}", help=_thelp):
                                        st.session_state[f"um_action_{_un}"] = "toggle"
                            if _perm_reset:
                                with _bc3:
                                    if st.button("🔑", key=f"um_resetpw_{_un}",
                                                 help="Reset Password"):
                                        st.session_state[f"um_action_{_un}"] = "reset_pw"
                            if _perm_delete:
                                with _bc4:
                                    if st.button("🗑️", key=f"um_del_{_un}", help="Delete"):
                                        st.session_state[f"um_action_{_un}"] = "delete"
                        elif _is_self:
                            st.caption("*(you — use Account tab)*")
                        else:
                            st.caption("—")

                _action = st.session_state.get(f"um_action_{_un}")

                if _action == "edit" and _perm_edit:
                    with st.form(f"um_edit_form_{_un}", clear_on_submit=False):
                        _ed_disp  = st.text_input("Display Name", value=_udisp,
                                                  key=f"ed_disp_{_un}")
                        _ed_email = st.text_input("Email", value=_uemail,
                                                  key=f"ed_email_{_un}")
                        if _hp("users.assign_roles"):
                            _ed_role_opts = (
                                list(_VALID_ROLES) if _cur_role == "super_admin"
                                else [r for r in _VALID_ROLES
                                      if r not in ("super_admin", "admin")]
                            )
                            _ed_role_idx = (
                                _ed_role_opts.index(_ur) if _ur in _ed_role_opts else 0
                            )
                            _ed_role = st.selectbox("Role", options=_ed_role_opts,
                                                    index=_ed_role_idx, key=f"ed_role_{_un}")
                        else:
                            _ed_role = _ur
                            st.text_input("Role", value=_ur, disabled=True,
                                          key=f"ed_role_ro_{_un}")
                        _ed_save, _ed_cancel = st.columns(2)
                        with _ed_save:
                            _ed_sub  = st.form_submit_button("Save", type="primary",
                                                              use_container_width=True)
                        with _ed_cancel:
                            _ed_canc = st.form_submit_button("Cancel",
                                                              use_container_width=True)

                    if _ed_canc:
                        st.session_state.pop(f"um_action_{_un}", None)
                        st.rerun()
                    if _ed_sub:
                        _err = _update_admin_user(
                            _un, role=_ed_role,
                            email=_ed_email, display_name=_ed_disp,
                        )
                        if _err:
                            st.error(f"Update failed: {_err}")
                        else:
                            _log_um("edit_user", _un, f"role={_ed_role}")
                            st.session_state.pop(f"um_action_{_un}", None)
                            st.success(f"User **{_un}** updated.")
                            st.rerun()

                elif _action == "toggle" and _perm_toggle:
                    _new_active = not _ua
                    _verb = "Enable" if _new_active else "Disable"
                    st.warning(f"{_verb} user **{_un}**?")
                    _tcy, _tcn = st.columns(2)
                    with _tcy:
                        if st.button("Confirm", key=f"um_tconf_{_un}", type="primary"):
                            _err = _update_admin_user(_un, is_active=_new_active)
                            if not _new_active:
                                _force_logout_user(_un)
                            if _err:
                                st.error(f"Failed: {_err}")
                            else:
                                _log_um("disable_user" if not _new_active else "enable_user",
                                        _un)
                                st.session_state.pop(f"um_action_{_un}", None)
                                st.rerun()
                    with _tcn:
                        if st.button("Cancel", key=f"um_tcanc_{_un}"):
                            st.session_state.pop(f"um_action_{_un}", None)
                            st.rerun()

                elif _action == "reset_pw" and _perm_reset:
                    with st.form(f"um_resetpw_form_{_un}", clear_on_submit=True):
                        _rp1 = st.text_input("New Password", type="password",
                                             key=f"rp1_{_un}")
                        _rp2 = st.text_input("Confirm", type="password",
                                             key=f"rp2_{_un}")
                        _rp_save, _rp_cancel = st.columns(2)
                        with _rp_save:
                            _rp_sub  = st.form_submit_button("Set Password", type="primary",
                                                              use_container_width=True)
                        with _rp_cancel:
                            _rp_canc = st.form_submit_button("Cancel",
                                                              use_container_width=True)

                    if _rp_canc:
                        st.session_state.pop(f"um_action_{_un}", None)
                        st.rerun()
                    if _rp_sub:
                        _err = _val_pw(_rp1, _rp2)
                        if _err:
                            st.error(_err)
                        else:
                            _dberr = _upd_pw(_un, _rp1)
                            if _dberr:
                                st.error(f"Failed: {_dberr}")
                            else:
                                _log_um("reset_password", _un)
                                st.session_state.pop(f"um_action_{_un}", None)
                                st.success(f"Password reset for **{_un}**.")
                                st.rerun()

                elif _action == "delete" and _perm_delete:
                    st.error(
                        f"⚠️ Permanently delete **{_un}**? "
                        "All their sessions will also be removed."
                    )
                    _dcy, _dcn = st.columns(2)
                    with _dcy:
                        if st.button("Delete", key=f"um_dconf_{_un}", type="primary"):
                            _err = _delete_admin_user(_un)
                            if _err:
                                st.error(f"Failed: {_err}")
                            else:
                                _log_um("delete_user", _un)
                                st.session_state.pop(f"um_action_{_un}", None)
                                st.success(f"User **{_un}** deleted.")
                                st.rerun()
                    with _dcn:
                        if st.button("Cancel", key=f"um_dcanc_{_un}"):
                            st.session_state.pop(f"um_action_{_un}", None)
                            st.rerun()

                st.divider()

            st.caption(
                "ℹ️ If role/is_active columns are missing, run "
                "`migrations/001_user_management.sql` in Supabase SQL Editor first."
            )


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Roles & Permissions
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "roles":
    with st.container():
        if not _hp("roles.view"):
            _show_403("roles.view")
        else:
            from core.rbac import (
                _ALL_PERM_KEYS,
                DEFAULT_ROLE_PERMISSIONS as _DEFAULT_PERMS,
                get_all_permissions as _get_all_perms,
                get_roles as _get_roles,
                set_role_permissions as _set_role_perms,
                get_role_permissions as _grp,
            )

            _actor_role = st.session_state.get("admin_role", "user")
            _can_edit   = _hp("roles.edit")

            st.subheader("🔐 Roles & Permissions")
            st.caption(
                "Configure which permissions each role has.  "
                "Only **Super Admin** can save changes."
            )

            _roles_data = _get_roles()
            _all_perms  = _get_all_perms()

            # Role selector
            _role_names  = [r["name"] for r in _roles_data]
            _role_labels = {r["name"]: r["label"] for r in _roles_data}

            _sel_role = st.selectbox(
                "Select role to configure",
                options=_role_names,
                format_func=lambda r: _role_labels.get(r, r),
                key="roles_tab_selected",
            )

            _is_sa          = _sel_role == "super_admin"
            _form_editable  = _can_edit and not _is_sa
            _current_rp     = frozenset(_ALL_PERM_KEYS) if _is_sa else _grp(_sel_role)

            if _is_sa:
                st.info(
                    "🔴 Super Admin has **all permissions** by definition.  "
                    "These cannot be modified."
                )

            # Group permissions by category
            _cats_map: dict[str, list] = {}
            for _p in _all_perms:
                _cats_map.setdefault(_p["category"], []).append(_p)

            _new_perms_set: set[str] = set()

            with st.form(f"perms_form_{_sel_role}", clear_on_submit=False):
                for _cat_name, _cat_perms in _cats_map.items():
                    st.markdown(f"**{_cat_name}**")
                    _pcols = st.columns(3)
                    for _pi, _p in enumerate(_cat_perms):
                        with _pcols[_pi % 3]:
                            _checked = st.checkbox(
                                _p["label"],
                                value=_p["key"] in _current_rp,
                                key=f"pf_{_sel_role}_{_p['key']}",
                                disabled=not _form_editable,
                            )
                            if _checked:
                                _new_perms_set.add(_p["key"])
                    st.divider()

                _pf_save = st.form_submit_button(
                    "💾 Save Permissions",
                    type="primary",
                    use_container_width=True,
                    disabled=not _form_editable,
                )

            if _pf_save and _form_editable:
                _perr = _set_role_perms(_sel_role, list(_new_perms_set), _actor_role)
                if _perr:
                    st.error(f"Failed: {_perr}")
                else:
                    from core.db_logger import log_admin_action as _log_rp
                    _log_rp("update_permissions", _sel_role,
                            f"{len(_new_perms_set)} permissions")
                    _grp.clear()
                    # Refresh current session's permissions if we modified our own role
                    if _sel_role == _actor_role:
                        st.session_state.user_permissions = frozenset(_new_perms_set)
                    st.success(
                        f"✅ Permissions for **{_role_labels.get(_sel_role, _sel_role)}** "
                        f"saved ({len(_new_perms_set)} permissions)."
                    )
                    st.rerun()

            if not _can_edit and not _is_sa:
                st.info("You have view-only access to role permissions.")

            # ── Reset to Default ──────────────────────────────────────────────
            if _can_edit and not _is_sa:
                st.divider()
                _def_perms = _DEFAULT_PERMS.get(_sel_role)
                if _def_perms is not None:
                    _def_count = len(_def_perms)
                    with st.form(f"reset_perms_form_{_sel_role}", clear_on_submit=True):
                        st.warning(
                            f"**Reset `{_role_labels.get(_sel_role, _sel_role)}` to default?**  \n"
                            f"This will overwrite any custom permissions and restore the "
                            f"built-in defaults ({_def_count} permissions)."
                        )
                        _confirm_reset = st.checkbox(
                            "Yes, overwrite current permissions with defaults",
                            key=f"confirm_reset_{_sel_role}",
                        )
                        _reset_btn = st.form_submit_button(
                            "🔄 Reset to Default",
                            disabled=not _confirm_reset,
                        )

                    if _reset_btn and _confirm_reset:
                        with st.spinner("Resetting permissions…"):
                            _rerr = _set_role_perms(
                                _sel_role, list(_def_perms), _actor_role
                            )
                        if _rerr:
                            st.error(f"Reset failed: {_rerr}")
                        else:
                            from core.db_logger import log_admin_action as _log_rst
                            _log_rst(
                                "reset_role_permissions",
                                _sel_role,
                                f"restored {_def_count} default permissions",
                            )
                            _grp.clear()
                            if _sel_role == _actor_role:
                                st.session_state.user_permissions = frozenset(_def_perms)
                            st.success(
                                f"✅ Permissions for **{_role_labels.get(_sel_role, _sel_role)}** "
                                f"reset to defaults ({_def_count} permissions)."
                            )
                            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Account
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "account":
    with st.container():
        st.subheader("Change Password")
        st.caption("Update the admin password stored in the database (bcrypt-hashed).")

        from core.auth import check_login as _check_login, update_password, validate_new_password

        _acct_user = st.session_state.get("admin_username", "admin")

        with st.form("change_pw_form", clear_on_submit=True):
            current_pw  = st.text_input("Current password", type="password", key="cp_current")
            new_pw_1    = st.text_input("New password (min 8 chars)", type="password",
                                        key="cp_new1")
            new_pw_2    = st.text_input("Confirm new password", type="password", key="cp_new2")
            save_pw_btn = st.form_submit_button("🔒 Save New Password", type="primary",
                                                use_container_width=True)

        if save_pw_btn:
            if not current_pw:
                st.error("Please enter your current password.")
            else:
                _ok, _err = _check_login(current_pw, _acct_user)
                if not _ok:
                    st.error(f"Current password incorrect: {_err}")
                else:
                    _val_err = validate_new_password(new_pw_1, new_pw_2)
                    if _val_err:
                        st.error(_val_err)
                    else:
                        _save_err = update_password(_acct_user, new_pw_1)
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
                        .eq("username", _acct_user)
                        .order("created_at", desc=True)
                        .execute()
                    )
                    if resp.data:
                        import pandas as pd
                        df = pd.DataFrame(resp.data)
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
                    c.table("admin_sessions").delete().eq(
                        "username", _acct_user
                    ).neq("id", _current).execute()
                    st.success("All other sessions revoked.")
            except Exception as exc:
                st.error(f"Error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Debug
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "debug":
    with st.container():
        if not _hp("dashboard.debug"):
            _show_403("dashboard.debug")
        else:
            st.subheader("Runtime Diagnostics")

            if st.button("🔍 Run Diagnostics", type="primary", key="run_diag_btn"):
                results: list[tuple[str, str, str]] = []

                results.append(("Python",    "✅", sys.version.split()[0]))
                results.append(("Streamlit", "✅", st.__version__))

                for sec_key in ("GROQ_API_KEY", "SUPABASE_URL", "SUPABASE_KEY",
                                "ADMIN_PASSWORD", "ADMIN_RESET_CODE"):
                    val = _get_secret(sec_key)
                    results.append((
                        f"Secret: {sec_key}",
                        "✅" if val else "⚠️",
                        "set" if val else "not set",
                    ))

                try:
                    from core.db_logger import _get_client, get_logging_mode
                    client = _get_client()
                    results.append(("Supabase client", "✅" if client else "⚠️",
                                    get_logging_mode()))
                except Exception as exc:
                    results.append(("Supabase client", "❌", str(exc)))

                try:
                    from core.auth import get_admin_user
                    u = get_admin_user("admin")
                    results.append((
                        "admin_users row",
                        "✅" if u else "⚠️",
                        "exists" if u else "missing — created on first login",
                    ))
                    if u:
                        results.append((
                            "admin role",
                            "✅",
                            u.get("role", "not set (run migration 001)"),
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
                        results.append((f"Index file: {_src}", _em, _det))
                    # Engine live status — inspect cached RAGEngine instances without
                    # importing app_main (which would re-execute top-level Streamlit calls)
                    try:
                        from core.rag_engine import RAGEngine as _RAGEng
                        _api = _get_secret("GROQ_API_KEY") or ""
                        if not _api:
                            results.append(("Engine status", "⚠️", "no GROQ_API_KEY — engines not checked"))
                        else:
                            for _src in _srcs:
                                # st.cache_resource stores under the function's hash key;
                                # we can read the index file + version as a proxy.
                                _idir = _s3.db_dir_for(_src)
                                _ver_f = _idir / "index_version.txt"
                                _idx_f = _idir / "index.faiss"
                                if not _idx_f.exists():
                                    results.append((f"Engine: {_src}", "⚠️", "no index on disk"))
                                elif _ver_f.exists():
                                    results.append((f"Engine: {_src}", "✅", f"index present, v{_ver_f.read_text().strip()}"))
                                else:
                                    results.append((f"Engine: {_src}", "✅", "index present (version unknown)"))
                    except Exception as _eexc:
                        results.append(("Engine status", "⚠️", "could not inspect"))
                except Exception as exc:
                    results.append(("Config / sources", "❌", str(exc)))

                try:
                    from core.rbac import get_role_permissions as _drp
                    _test_perms = _drp(st.session_state.get("admin_role", "user"))
                    results.append(("RBAC permissions loaded", "✅",
                                    f"{len(_test_perms)} permissions"))
                except Exception as exc:
                    results.append(("RBAC permissions", "❌", str(exc)))

                import pandas as pd
                df = pd.DataFrame(results, columns=["Check", "Status", "Detail"])
                st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("SQL Migration Status")
            st.caption("Run these in Supabase SQL Editor if not done yet.")

            _mig_base = Path(__file__).resolve().parent.parent / "migrations"
            for _mig_file in sorted(_mig_base.glob("*.sql")) if _mig_base.exists() else []:
                with st.expander(f"📄 {_mig_file.name}"):
                    try:
                        st.code(_mig_file.read_text(encoding="utf-8"), language="sql")
                    except Exception:
                        st.info("Migration file not found locally.")

            st.divider()
            st.subheader("Build Missing Indexes")
            try:
                from config import get_settings as _gs4
                from core.settings_store import get_enabled_sources as _ges4
                _s4    = _gs4()
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
                # Convert frozenset to list for JSON serialization
                safe_json = {
                    k: list(v) if isinstance(v, frozenset) else v
                    for k, v in safe.items()
                }
                st.json(safe_json)

            st.divider()
            st.subheader("Environment Variables")
            if st.button("👁️ Show Env Vars", key="show_env"):
                safe_keys = ["STREAMLIT_SERVER_PORT", "HOME", "PATH", "PYTHONPATH", "HOSTNAME"]
                st.json({k: os.environ.get(k, "(not set)") for k in safe_keys})
