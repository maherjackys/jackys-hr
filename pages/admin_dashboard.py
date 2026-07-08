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
import html as _html
import os
import re
import shutil
import sys
from pathlib import Path

import streamlit as st

_SESSION_COOKIE        = "admin_session"
_SESSION_TTL_DAYS      = 1
_SESSION_TTL_DAYS_LONG = 30

# ── RBAC level map (kept for user hierarchy checks — who can manage whom) ─────
_RLEVEL = {"super_admin": 4, "admin": 3, "moderator": 2, "user": 1}


# ── Cookie helpers ─────────────────────────────────────────────────────────────

def _read_session_cookie() -> str:
    try:
        return st.context.cookies.get(_SESSION_COOKIE, "")
    except Exception:
        return ""


def _write_session_cookie(token: str, remember: bool = False) -> None:
    """Write session cookie via inline JS — avoids extra_streamlit_components deprecation."""
    days = _SESSION_TTL_DAYS_LONG if remember else _SESSION_TTL_DAYS
    st.markdown(
        f"""<script>
(function(){{
  var d=new Date();
  d.setTime(d.getTime()+({days}*24*60*60*1000));
  document.cookie="{_SESSION_COOKIE}={token};expires="+d.toUTCString()+";path=/;SameSite=Lax";
}})();
</script>""",
        unsafe_allow_html=True,
    )


def _delete_session_cookie() -> None:
    """Expire the session cookie immediately via inline JS."""
    st.markdown(
        f"""<script>
document.cookie="{_SESSION_COOKIE}=;expires=Thu, 01 Jan 1970 00:00:00 UTC;path=/;SameSite=Lax";
</script>""",
        unsafe_allow_html=True,
    )


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


# ── Admin language state ───────────────────────────────────────────────────────
if "adm_lang" not in st.session_state:
    st.session_state.adm_lang = "en"
_adm_lang = st.session_state.adm_lang
_is_ar    = (_adm_lang == "ar")

# ── UI string translations ─────────────────────────────────────────────────────
_UI_AR: dict[str, str] = {
    "Query Logs":              "سجلات الاستعلامات",
    "Manage Documents":        "إدارة المستندات",
    "Add / Manage Sources":    "إضافة المصادر وإدارتها",
    "Settings":                "الإعدادات",
    "User Management":         "إدارة المستخدمين",
    "Roles & Permissions":     "الأدوار والصلاحيات",
    "Account":                 "الحساب",
    "Debug":                   "التشخيص",
    "Overview":                "نظرة عامة",
    "Analytics":               "التحليلات",
    "Audit Trail":             "سجل التدقيق",
    "Security":                "الأمان",
    "Feature Flags":           "ميزات النظام",
    "System Health":           "صحة النظام",
    "Email Templates":         "قوالب البريد الإلكتروني",
    "API Keys":                "مفاتيح API",
    "Notifications":           "الإشعارات",
    "Search query text":       "ابحث في النصوص",
    "Create Source":           "إنشاء مصدر",
    "Delete Source":           "حذف مصدر",
    "Password Protection":     "حماية بكلمة مرور",
    "Login mode":              "طريقة الدخول",
    "Sign in":                 "تسجيل الدخول",
    "Forgot password":         "نسيت كلمة المرور",
}

def _t(key: str) -> str:
    """Return Arabic translation if language is Arabic, else the key itself."""
    return _UI_AR.get(key, key) if _is_ar else key


# ── Nav translations ───────────────────────────────────────────────────────────
_NAV_AR: dict[str, str] = {
    "overview":      "🏠 نظرة عامة",
    "analytics":     "📊 التحليلات",
    "logs":          "📋 السجلات",
    "audit":         "🔍 سجل التدقيق",
    "security":      "🛡️ الأمان",
    "docs":          "📁 المستندات",
    "add":           "🗄️ المصادر",
    "settings":      "⚙️ الإعدادات",
    "users":         "👥 المستخدمون",
    "roles":         "🔐 الأدوار",
    "features":      "🚩 ميزات النظام",
    "syshealth":     "💻 صحة النظام",
    "emailtmpls":    "📧 قوالب البريد",
    "apikeys":       "🔑 مفاتيح API",
    "notifications": "🔔 الإشعارات",
    "account":       "🔑 الحساب",
    "debug":         "🐛 التشخيص",
}

# ── Navigation (sidebar) ──────────────────────────────────────────────────────

from core.rbac import has_permission as _hp  # noqa: E402

_TABS_DEF = [
    ("🏠 Overview",        "overview",     "dashboard.view"),
    ("📊 Analytics",       "analytics",    "dashboard.analytics"),
    ("📋 Logs",            "logs",         "dashboard.logs"),
    ("🔍 Audit Trail",     "audit",        "audit.view"),
    ("🛡️ Security",       "security",     "security.view"),
    ("📁 Documents",       "docs",         "documents.view"),
    ("🗄️ Sources",        "add",          "sources.view"),
    ("⚙️ Settings",       "settings",     "settings.view"),
    ("👥 Users",           "users",        "users.view"),
    ("🔐 Roles",           "roles",        "roles.view"),
    ("🚩 Feature Flags",   "features",     "features.view"),
    ("💻 System Health",   "syshealth",    "system.health"),
    ("📧 Email Templates", "emailtmpls",   "templates.view"),
    ("🔑 API Keys",        "apikeys",      "api_keys.view"),
    ("🔔 Notifications",   "notifications","notifications.view"),
    ("🔑 Account",         "account",      None),
    ("🐛 Debug",           "debug",        "dashboard.debug"),
]

_vis_defs   = [(lbl, key, perm) for lbl, key, perm in _TABS_DEF
               if perm is None or _hp(perm)]
# Use Arabic labels when language is Arabic
_nav_labels = [(_NAV_AR.get(key, lbl) if _is_ar else lbl) for lbl, key, _ in _vis_defs]
_nav_keys   = [key for _, key, _ in _vis_defs]

with st.sidebar:
    _logged_user = st.session_state.get("admin_username", "admin")
    _logged_role = st.session_state.get("admin_role", "admin")
    _ROLE_BADGE  = {"super_admin": "🔴", "admin": "🟠", "moderator": "🟡", "user": "🟢"}

    # ── Language + Theme toggles ───────────────────────────────────────────────
    _sb_c1, _sb_c2 = st.columns(2)
    with _sb_c1:
        _lang_icon = "🇸🇦 AR" if not _is_ar else "🇬🇧 EN"
        if st.button(_lang_icon, key="adm_lang_btn", use_container_width=True,
                     help="تبديل اللغة / Switch language"):
            st.session_state.adm_lang = "en" if _is_ar else "ar"
            st.rerun()
    with _sb_c2:
        _adm_theme_tmp = st.session_state.get("adm_theme", "light")
        _sb_theme_icon = "☀️" if _adm_theme_tmp == "dark" else "🌙"
        if st.button(_sb_theme_icon, key="adm_theme_btn_sb", use_container_width=True,
                     help="تبديل الوضع / Toggle theme"):
            st.session_state.adm_theme = "light" if _adm_theme_tmp == "dark" else "dark"
            st.rerun()
    st.divider()

    # ── User info ─────────────────────────────────────────────────────────────
    _signin_txt = "مسجل الدخول بـ" if _is_ar else "Signed in as"
    st.caption(
        f"{_signin_txt} **{_logged_user}**  \n"
        f"{_ROLE_BADGE.get(_logged_role, '⚪')} `{_logged_role}`"
    )
    # Notification badge
    try:
        from core.notifications import get_unread_count as _get_unread
        _unread_n = _get_unread()
        if _unread_n > 0:
            _notif_txt = f"🔔 {_unread_n} إشعار غير مقروء" if _is_ar else f'🔔 {_unread_n} unread notification{"s" if _unread_n != 1 else ""}'
            st.markdown(
                f'<span class="adm-badge adm-badge-red" style="margin:.2rem 0;display:inline-block">'
                f'{_notif_txt}</span>',
                unsafe_allow_html=True,
            )
    except Exception:
        pass
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
    _logout_txt = "🚪 تسجيل الخروج" if _is_ar else "🚪 Logout"
    if st.button(_logout_txt, use_container_width=True, key="logout_btn"):
        from core.auth import invalidate_session
        invalidate_session(st.session_state.get("admin_session_token", ""))
        _delete_session_cookie()
        st.session_state.clear()
        st.rerun()


# ── Admin theme state ─────────────────────────────────────────────────────────
if "adm_theme" not in st.session_state:
    st.session_state.adm_theme = "light"
_adm_theme = st.session_state.adm_theme

# ── Cairo font + shared design tokens ─────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# ── Admin CSS — unified with main app tokens ──────────────────────────────────
_ADM_LIGHT = """
:root {
  --adm-bg:       #F0F2F5;
  --adm-surface:  #FFFFFF;
  --adm-sf2:      #F7F8FA;
  --adm-border:   #D1D5DB;
  --adm-ink:      #111827;
  --adm-ink2:     #374151;
  --adm-ink3:     #6B7280;
  --adm-brand:    #C0392B;
  --adm-brand-l:  #E74C3C;
  --adm-sh:       0 1px 6px rgba(0,0,0,.08);
  --adm-sh2:      0 4px 20px rgba(0,0,0,.12);
  --adm-sidebar:  #1F2937;
  --adm-sidebar-ink: #F9FAFB;
  --adm-sidebar-ink2: #D1D5DB;
  --adm-sidebar-border: #374151;
  --adm-sidebar-hover: rgba(255,255,255,.07);
  --adm-sidebar-active: rgba(192,57,43,.18);
}
"""
_ADM_DARK = """
:root {
  --adm-bg:       #0D1117;
  --adm-surface:  #161B22;
  --adm-sf2:      #1C2128;
  --adm-border:   #30363D;
  --adm-ink:      #E6EDF3;
  --adm-ink2:     #8B949E;
  --adm-ink3:     #7D8590;
  --adm-brand:    #FF7060;
  --adm-brand-l:  #FF9080;
  --adm-sh:       0 1px 4px rgba(0,0,0,.3);
  --adm-sh2:      0 4px 16px rgba(0,0,0,.5);
}
"""
_adm_token_css = _ADM_DARK if _adm_theme == "dark" else _ADM_LIGHT

st.markdown(f"""
<style>
{_adm_token_css}

/* ── Global ── */
html, body, [class*="css"] {{
  font-family: 'Cairo','Inter',sans-serif !important;
  -webkit-font-smoothing: antialiased;
}}
[data-testid="stApp"],
[data-testid="stMain"],
.main {{
  background-color: var(--adm-bg) !important;
  color: var(--adm-ink) !important;
}}
.main .block-container {{ max-width: 960px !important; padding-top:.5rem !important; }}

/* ── Sidebar — always dark ── */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {{
  background: var(--adm-sidebar, #1F2937) !important;
  border-right: 1px solid var(--adm-sidebar-border, #374151) !important;
}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] .stMarkdown p {{
  color: var(--adm-sidebar-ink2, #D1D5DB) !important;
  -webkit-text-fill-color: var(--adm-sidebar-ink2, #D1D5DB) !important;
}}
[data-testid="stSidebar"] strong {{
  color: var(--adm-sidebar-ink, #F9FAFB) !important;
  -webkit-text-fill-color: var(--adm-sidebar-ink, #F9FAFB) !important;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
  background: var(--adm-sidebar-hover, rgba(255,255,255,.07)) !important;
  border-radius: 6px;
}}
[data-testid="stSidebar"] hr {{ border-color: var(--adm-sidebar-border, #374151) !important; opacity:.5; }}

/* ── Sidebar collapse/expand toggle — always visible ── */
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] {{
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  background: #374151 !important;
  color: #F9FAFB !important;
  border-radius: 0 8px 8px 0 !important;
  z-index: 9999 !important;
}}
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="stSidebarCollapseButton"] svg {{
  stroke: #F9FAFB !important;
  fill: #F9FAFB !important;
}}

/* ── Typography ── */
h1,h2,h3,h4 {{ color: var(--adm-ink) !important; font-family:'Cairo','Inter',sans-serif !important; }}
p, li {{ color: var(--adm-ink2) !important; }}

/* ── Buttons ── */
[data-testid="stBaseButton-primary"] {{
  background: var(--adm-brand) !important;
  border: none !important;
  border-radius: 10px !important;
  font-family: 'Cairo','Inter',sans-serif !important;
  font-weight: 600 !important;
  color: #fff !important;
  -webkit-text-fill-color: #fff !important;
}}
[data-testid="stBaseButton-primary"]:hover {{ background: var(--adm-brand-l) !important; }}
[data-testid="stBaseButton-secondary"] {{
  background: var(--adm-surface) !important;
  border: 1.5px solid var(--adm-border) !important;
  border-radius: 10px !important;
  font-family: 'Cairo','Inter',sans-serif !important;
  color: var(--adm-ink2) !important;
  -webkit-text-fill-color: var(--adm-ink2) !important;
}}
[data-testid="stBaseButton-secondary"]:hover {{
  border-color: var(--adm-brand) !important;
  color: var(--adm-ink) !important;
  -webkit-text-fill-color: var(--adm-ink) !important;
}}

/* ── Inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] select {{
  background: var(--adm-surface) !important;
  color: var(--adm-ink) !important;
  border-color: var(--adm-border) !important;
  border-radius: 8px !important;
  font-family: 'Cairo','Inter',sans-serif !important;
}}

/* ── Expanders ── */
[data-testid="stExpander"] {{
  background: var(--adm-surface) !important;
  border-color: var(--adm-border) !important;
}}

/* ── Alerts ── */
[data-testid="stAlert"] {{
  background: var(--adm-sf2) !important;
  border-color: var(--adm-border) !important;
  color: var(--adm-ink) !important;
}}

/* ── Metrics ── */
[data-testid="stMetric"] {{ color: var(--adm-ink) !important; }}
[data-testid="stMetricValue"] {{ color: var(--adm-ink) !important; -webkit-text-fill-color: var(--adm-ink) !important; }}
[data-testid="stMetricLabel"] {{ color: var(--adm-ink2) !important; -webkit-text-fill-color: var(--adm-ink2) !important; }}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {{ background: var(--adm-surface) !important; }}

/* ── Hide Streamlit chrome ── */
[data-testid="stToolbar"],
[data-testid="manage-app-button"],
[data-testid="stAppDeployButton"],
[data-testid="stActionButton"],
[data-testid="stActionButtonIcon"],
.stDeployButton, .stAppDeployButton,
footer, #MainMenu,
[class*="deployButton"],
[class*="manageApp"] {{ display:none !important; visibility:hidden !important; }}

/* stHeader: transparent shell — do NOT display:none it (sidebar toggle lives inside) */
[data-testid="stHeader"] {{
  background: transparent !important;
  border-bottom: none !important;
  box-shadow: none !important;
  min-height: 0 !important;
  padding: 0 !important;
  overflow: visible !important;
  z-index: 9000 !important;
}}
/* Hide only the toolbar/app-menu children, NOT the sidebar toggle wrapper */
[data-testid="stHeader"] [data-testid="stToolbar"],
[data-testid="stHeader"] [data-testid="stHeaderActionElements"],
[data-testid="stHeader"] [data-testid="stAppViewBlockContainer"],
[data-testid="stHeader"] .stAppToolbar {{
  display: none !important;
}}

/* ── Main content card-feel ── */
.main .block-container {{
  background: var(--adm-bg) !important;
}}
[data-testid="stMetric"] {{
  background: var(--adm-surface) !important;
  border: 1px solid var(--adm-border) !important;
  border-radius: 12px !important;
  padding: .75rem 1rem !important;
  box-shadow: var(--adm-sh) !important;
}}
[data-testid="stMetricValue"] {{
  color: var(--adm-ink) !important;
  -webkit-text-fill-color: var(--adm-ink) !important;
  font-size: 1.9rem !important;
  font-weight: 800 !important;
}}
[data-testid="stMetricLabel"] {{
  color: var(--adm-ink3) !important;
  -webkit-text-fill-color: var(--adm-ink3) !important;
  font-size: .72rem !important;
  text-transform: uppercase !important;
  letter-spacing: .06em !important;
  font-weight: 700 !important;
}}

/* ── Sidebar control buttons (lang + theme) — dark sidebar base ── */
.st-key-adm_lang_btn button,
.st-key-adm_theme_btn button,
.st-key-adm_theme_btn_sb button {{
  background: rgba(255,255,255,.08) !important;
  border: 1.5px solid rgba(255,255,255,.18) !important;
  border-radius: 999px !important;
  color: #D1D5DB !important;
  -webkit-text-fill-color: #D1D5DB !important;
  font-size: .82rem !important;
  padding: .25rem .6rem !important;
  height: 2rem !important;
  box-shadow: none !important;
  font-family: 'Cairo','Inter',sans-serif !important;
}}
.st-key-adm_lang_btn button:hover,
.st-key-adm_theme_btn button:hover,
.st-key-adm_theme_btn_sb button:hover {{
  background: rgba(255,255,255,.15) !important;
  border-color: var(--adm-brand) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}}

/* ── Sidebar logout button ── */
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
  background: rgba(255,255,255,.06) !important;
  border: 1.5px solid rgba(255,255,255,.15) !important;
  color: #D1D5DB !important;
  -webkit-text-fill-color: #D1D5DB !important;
  border-radius: 10px !important;
}}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {{
  background: rgba(192,57,43,.25) !important;
  border-color: var(--adm-brand) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}}

/* ── KPI cards ── */
.adm-kpi {{
  background: var(--adm-surface);
  border: 1px solid var(--adm-border);
  border-radius: 12px;
  padding: 1rem 1.25rem;
  box-shadow: var(--adm-sh);
  flex: 1; min-width: 130px;
}}
.adm-metric-row {{ display:flex; gap:1rem; flex-wrap:wrap; margin:1rem 0; }}
.adm-kpi-label {{ font-size:.7rem; color:var(--adm-ink3); text-transform:uppercase; letter-spacing:.07em; font-weight:700; }}
.adm-kpi-value {{ font-size:1.8rem; font-weight:800; color:var(--adm-ink); line-height:1.15; }}
.adm-kpi-sub   {{ font-size:.75rem; color:var(--adm-ink3); margin-top:.15rem; }}

/* ── Badges ── */
.adm-badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:.73rem; font-weight:600; }}
.adm-badge-green  {{ background:#dcfce7; color:#166534; }}
.adm-badge-red    {{ background:#fee2e2; color:#991b1b; }}
.adm-badge-yellow {{ background:#fef9c3; color:#854d0e; }}
.adm-badge-blue   {{ background:#dbeafe; color:#1e40af; }}
.adm-badge-gray   {{ background:#f3f4f6; color:#374151; }}

/* Dark badge overrides */
{''.join([
  '.adm-badge-green{background:#0d4429!important;color:#56d364!important;}',
  '.adm-badge-red{background:#4d1a1a!important;color:#f97171!important;}',
  '.adm-badge-yellow{background:#4d3800!important;color:#e3b341!important;}',
  '.adm-badge-blue{background:#0d2a4d!important;color:#79b8ff!important;}',
  '.adm-badge-gray{background:#21262d!important;color:#c9d1d9!important;}',
]) if _adm_theme == 'dark' else ''}

/* ── Activity rows ── */
.adm-activity-row {{
  display:flex; align-items:flex-start; gap:.6rem;
  padding:.5rem .75rem; border-radius:8px; margin:.2rem 0;
  border-left:3px solid var(--adm-border);
  transition: background .15s;
}}
.adm-activity-row:hover {{ background:var(--adm-sf2); }}
.adm-ts {{ font-size:.7rem; color:var(--adm-ink3); white-space:nowrap; min-width:110px; }}
.adm-log-unanswered {{ border-left-color:#f59e0b; }}
.adm-log-feedback   {{ border-left-color:#3b82f6; }}
.adm-log-admin      {{ border-left-color:#8b5cf6; }}
.adm-log-error      {{ border-left-color:#ef4444; }}
.adm-section-header {{ font-size:1.05rem; font-weight:700; margin:1.2rem 0 .45rem; color:var(--adm-ink); }}
.adm-source-health  {{ display:flex; gap:.5rem; align-items:center; padding:.35rem 0; }}
</style>
""", unsafe_allow_html=True)

# Apply dark mode to Streamlit native components too
if _adm_theme == "dark":
    from ui.styles import inject_dark_mode as _adm_dark
    _adm_dark()

# Apply RTL when Arabic
if _is_ar:
    st.markdown("""
<style>
html, body, [data-testid="stApp"], .main, .block-container,
[data-testid="stSidebar"] { direction: rtl !important; text-align: right !important; }
[data-testid="stSidebar"] { border-right: none !important; border-left: 1px solid var(--adm-border) !important; }
.adm-activity-row { flex-direction: row-reverse; border-left: none !important; border-right: 3px solid var(--adm-border); }
.adm-log-unanswered { border-right-color:#f59e0b !important; border-left:none !important; }
.adm-log-feedback   { border-right-color:#3b82f6 !important; border-left:none !important; }
.adm-log-admin      { border-right-color:#8b5cf6 !important; border-left:none !important; }
.adm-log-error      { border-right-color:#ef4444 !important; border-left:none !important; }
[data-testid="stRadio"] label { text-align: right !important; }
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea { direction: rtl; text-align: right; }
</style>
""", unsafe_allow_html=True)


def _actor() -> str:
    """Return the currently logged-in admin's username for audit logging."""
    return st.session_state.get("admin_username", "")


# ── Main admin UI ──────────────────────────────────────────────────────────────
_dash_title = "لوحة تحكم المدير" if _is_ar else "Admin Dashboard"
_dash_sub   = "مساعد سياسات الموارد البشرية · لوحة التحكم" if _is_ar else "HR Policy Assistant · Control Panel"

st.markdown(f"""
<div style="display:flex;align-items:center;gap:.75rem;margin-bottom:1.25rem;
            {'flex-direction:row-reverse' if _is_ar else ''}">
  <div style="width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#C0392B,#E74C3C);
       display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(192,57,43,.3)">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2"
         stroke-linecap="round"><rect x="3" y="3" width="7" height="7" rx="1"/>
      <rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>
      <rect x="14" y="14" width="7" height="7" rx="1"/></svg>
  </div>
  <div style="{'text-align:right' if _is_ar else ''}">
    <h2 style="margin:0;font-size:1.35rem;font-weight:800;color:var(--adm-ink)">{_dash_title}</h2>
    <p style="margin:0;font-size:.75rem;color:var(--adm-ink3)">{_dash_sub}</p>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Logs
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "logs":
    with st.container():
        if not _hp("dashboard.logs"):
            _show_403("dashboard.logs")
        else:
            st.subheader("Query Logs")

            # ── Filters ────────────────────────────────────────────────────────
            _lf_c1, _lf_c2, _lf_c3 = st.columns([2, 1, 1])
            with _lf_c1:
                _log_search = st.text_input("🔍 Search query text", key="log_search",
                                             placeholder="Filter by keyword…", label_visibility="collapsed")
            with _lf_c2:
                _log_type_filter = st.selectbox(
                    "Log type",
                    options=["all", "unanswered", "feedback", "admin_action"],
                    key="log_type_filter",
                    label_visibility="collapsed",
                )
            with _lf_c3:
                _log_limit = st.number_input("Max rows", min_value=10, max_value=1000,
                                              value=200, step=10, key="log_limit",
                                              label_visibility="collapsed")

            _lf_d1, _lf_d2, _lf_d3, _lf_d4 = st.columns([2, 2, 1, 1])
            with _lf_d1:
                _log_date_from = st.date_input("From date", value=None, key="log_date_from",
                                                label_visibility="collapsed")
            with _lf_d2:
                _log_date_to = st.date_input("To date", value=None, key="log_date_to",
                                              label_visibility="collapsed")
            with _lf_d3:
                _auto_refresh = st.toggle("Auto-refresh", key="log_auto_refresh")
            with _lf_d4:
                _fetch_btn = st.button("🔄 Fetch", type="primary",
                                        use_container_width=True, key="log_fetch_btn")

            _should_fetch = _fetch_btn or _auto_refresh
            if _should_fetch:
                from core.db_logger import fetch_logs as _fl
                _ltype = _log_type_filter if _log_type_filter != "all" else None
                with st.spinner("Fetching logs…"):
                    _rows, _err = _fl(
                        log_type=_ltype,
                        limit=int(_log_limit),
                        date_from=_log_date_from or None,
                        date_to=_log_date_to or None,
                        search=_log_search.strip() or None,
                    )
                if _err:
                    st.error(f"Error: {_err}")
                elif not _rows:
                    st.info("No rows match your filters.")
                else:
                    import pandas as pd
                    import json as _json_logs
                    _df_logs = pd.DataFrame(_rows)
                    st.success(f"Fetched **{len(_df_logs)}** rows.")

                    # ── Type color badges ───────────────────────────────────────
                    _type_cls = {
                        "unanswered": "adm-badge-yellow",
                        "feedback":   "adm-badge-blue",
                        "admin_action": "adm-badge-blue",
                    }

                    st.dataframe(
                        _df_logs,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "ts": st.column_config.DatetimeColumn("Timestamp", format="YYYY-MM-DD HH:mm:ss"),
                            "log_type": st.column_config.TextColumn("Type"),
                            "query": st.column_config.TextColumn("Query / Action"),
                            "source": st.column_config.TextColumn("Source"),
                            "score": st.column_config.NumberColumn("Score", format="%.3f"),
                            "vote": st.column_config.TextColumn("Vote"),
                        },
                    )

                    # ── Export ─────────────────────────────────────────────────
                    _exp_c1, _exp_c2 = st.columns(2)
                    with _exp_c1:
                        _csv_l = _df_logs.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "⬇️ CSV", data=_csv_l,
                            file_name=f"logs_{datetime.date.today()}.csv",
                            mime="text/csv", key="log_dl_csv",
                        )
                    with _exp_c2:
                        _json_l = _json_logs.dumps(_rows, default=str, indent=2).encode("utf-8")
                        st.download_button(
                            "⬇️ JSON", data=_json_l,
                            file_name=f"logs_{datetime.date.today()}.json",
                            mime="application/json", key="log_dl_json",
                        )

                if _auto_refresh:
                    st.rerun()

            st.divider()
            st.subheader("Local Fallback Logs")
            _logs_dir_path = Path(__file__).resolve().parent.parent / "logs"
            _jsonl_files = sorted(_logs_dir_path.glob("*.jsonl")) if _logs_dir_path.exists() else []
            if not _jsonl_files:
                st.info("No local JSONL log files found.")
            else:
                for _jf in _jsonl_files:
                    with st.expander(f"📄 {_jf.name}"):
                        try:
                            _lines = _jf.read_text(encoding="utf-8").splitlines()[-100:]
                            st.code("\n".join(_lines), language="json")
                        except Exception as _exc:
                            st.error(f"Could not read: {_exc}")


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
                                    log_admin_action("upload", selected_source, safe, actor=_actor())
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
                                    log_admin_action("rebuild", selected_source, actor=_actor())
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
                                    log_admin_action("delete", selected_source, _f.name, actor=_actor())
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
                        log_admin_action("rebuild", selected_source, actor=_actor())
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
                                log_admin_action("add_source", new_key, new_display, actor=_actor())
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
                                                    actor=_actor(),
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
            # ── Password Protection ────────────────────────────────────────────
            st.subheader("🔐 Password Protection")
            st.caption(
                "Controls whether the employee app requires a password (APP_PASSWORD secret) "
                "before users can access the chat interface. "
                "Disable to allow open access without a password prompt."
            )
            try:
                from core.settings_store import (
                    get_password_protection_enabled,
                    set_password_protection_enabled,
                )
                _pw_on = get_password_protection_enabled()
                _pw_new = st.toggle(
                    "Enable Password Protection",
                    value=_pw_on,
                    key="toggle_pw_protection",
                    disabled=not _hp("settings.edit"),
                    help="When ON, employees must enter APP_PASSWORD to open the chat app.",
                )
                if _hp("settings.edit"):
                    if st.button("💾 Save Password Setting", key="save_pw_btn"):
                        _pw_err = set_password_protection_enabled(_pw_new)
                        if _pw_err:
                            st.error(f"Error: {_pw_err}")
                        else:
                            _label = "enabled" if _pw_new else "disabled"
                            st.success(f"Password protection {_label}.")
                else:
                    st.caption("⚠️ You have view-only access to settings.")
            except Exception as _pw_exc:
                st.error(f"Password protection settings error: {_pw_exc}")

            st.divider()

            # ── Source Visibility ─────────────────────────────────────────────
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

            st.divider()

            # ── Social Media Links ────────────────────────────────────────────
            st.subheader("🌐 Social Media Links")
            st.caption(
                "Set the organization's social media profile URLs. "
                "Leave a field empty to hide that icon in the employee app footer."
            )
            try:
                from core.settings_store import get_social_links, set_social_links
                _SOCIAL_META_ADM = {
                    "linkedin":  ("LinkedIn",   "https://linkedin.com/company/…"),
                    "twitter":   ("X (Twitter)","https://x.com/…"),
                    "instagram": ("Instagram",  "https://instagram.com/…"),
                    "whatsapp":  ("WhatsApp",   "https://wa.me/971501234567"),
                    "facebook":  ("Facebook",   "https://facebook.com/…"),
                    "youtube":   ("YouTube",    "https://youtube.com/@…"),
                }
                _cur_social = get_social_links()
                _new_social: dict[str, str] = {}
                _sc1, _sc2 = st.columns(2)
                for _i, (_plat, (_label, _ph)) in enumerate(_SOCIAL_META_ADM.items()):
                    _col = _sc1 if _i % 2 == 0 else _sc2
                    with _col:
                        _new_social[_plat] = st.text_input(
                            _label,
                            value=_cur_social.get(_plat, ""),
                            placeholder=_ph,
                            key=f"social_{_plat}",
                            disabled=not _hp("settings.edit"),
                        )
                if _hp("settings.edit"):
                    if st.button("💾 Save Social Links", type="primary", key="save_social_btn"):
                        _soc_err = set_social_links(_new_social)
                        if _soc_err:
                            st.error(f"Error: {_soc_err}")
                        else:
                            st.success("✅ Social media links saved.")
                else:
                    st.caption("⚠️ You have view-only access to settings.")
            except Exception as _soc_exc:
                st.error(f"Social links error: {_soc_exc}")


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

            # ── Quick actions row ──────────────────────────────────────────────
            _um_qa1, _um_qa2 = st.columns(2)
            with _um_qa1:
                if st.button("⬇️ Export Users CSV", use_container_width=True, key="um_export_csv"):
                    import pandas as pd
                    _exp_df = pd.DataFrame([
                        {k: v for k, v in u.items() if k != "password_hash"}
                        for u in _all_users
                    ])
                    _exp_csv = _exp_df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "Download CSV", data=_exp_csv,
                        file_name=f"users_{datetime.date.today()}.csv",
                        mime="text/csv", key="um_dl_csv",
                    )
            with _um_qa2:
                if _hp("users.view_sessions") and st.button(
                    "📋 View Login History", use_container_width=True, key="um_login_hist_btn"
                ):
                    st.session_state["um_show_login_hist"] = not st.session_state.get("um_show_login_hist", False)

            if st.session_state.get("um_show_login_hist") and _hp("users.view_sessions"):
                with st.expander("Login History", expanded=True):
                    _lh_filter = st.text_input("Username (blank = all)", key="um_lh_user_input")
                    if st.button("Load", key="um_lh_load"):
                        from core.db_logger import fetch_login_history as _flh_um
                        _lh_data, _lh_err = _flh_um(
                            username=_lh_filter.strip() or None, limit=100
                        )
                        if _lh_err:
                            st.error(f"Error: {_lh_err}")
                        elif not _lh_data:
                            st.info("No login history found. Run migration 005 first.")
                        else:
                            import pandas as pd
                            _df_lh = pd.DataFrame(_lh_data)
                            if "success" in _df_lh.columns:
                                _df_lh["status"] = _df_lh["success"].map(
                                    {True: "✅ Success", False: "❌ Failed"}
                                )
                            st.dataframe(
                                _df_lh[["username", "status", "created_at"]]
                                if "status" in _df_lh.columns else _df_lh,
                                use_container_width=True, hide_index=True,
                            )
                            _s_cnt = int(_df_lh.get("success", pd.Series([], dtype=bool)).sum()) if "success" in _df_lh else 0
                            _f_cnt = len(_df_lh) - _s_cnt
                            _lhc1, _lhc2 = st.columns(2)
                            _lhc1.metric("✅ Successful", _s_cnt)
                            _lhc2.metric("❌ Failed", _f_cnt)

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
                                _log_um("create_user", _cu_uname, _cu_role, actor=_actor())
                                st.success(
                                    f"User **{_cu_uname}** created with role `{_cu_role}`."
                                )
                                st.rerun()

            st.divider()

            # ── Bulk Actions ──────────────────────────────────────────────────
            _can_bulk = _hp("users.disable") or _hp("users.delete") or _hp("users.assign_roles")
            if _can_bulk:
                with st.expander("☑️ Bulk User Actions"):
                    st.caption("Select users then choose an action to apply to all selected.")
                    _bulk_all_users = [
                        u for u in _all_users
                        if u["username"] != _cur_user
                        and _can_manage(_cur_role, u.get("role", "user"))
                    ]
                    _bulk_unames = [u["username"] for u in _bulk_all_users]
                    _bulk_sel = st.multiselect(
                        "Select users", options=_bulk_unames,
                        key="um_bulk_sel", placeholder="Choose users…",
                    )
                    _bulk_action = st.selectbox(
                        "Action",
                        options=["— choose —", "Enable", "Disable", "Force Logout", "Delete", "Assign Role"],
                        key="um_bulk_action",
                        label_visibility="collapsed",
                    )
                    _bulk_role_target = None
                    if _bulk_action == "Assign Role" and _hp("users.assign_roles"):
                        _bulk_role_opts = (
                            list(_VALID_ROLES) if _cur_role == "super_admin"
                            else [r for r in _VALID_ROLES if r not in ("super_admin", "admin")]
                        )
                        _bulk_role_target = st.selectbox("Target role", _bulk_role_opts, key="um_bulk_role")

                    _bulk_submit = st.button(
                        "▶ Apply to Selected", type="primary", key="um_bulk_apply",
                        disabled=(not _bulk_sel or _bulk_action == "— choose —"),
                    )

                    if _bulk_submit and _bulk_sel and _bulk_action != "— choose —":
                        st.session_state["um_bulk_confirm"] = {
                            "users": _bulk_sel, "action": _bulk_action,
                            "role": _bulk_role_target,
                        }

                    if st.session_state.get("um_bulk_confirm"):
                        _bcp = st.session_state["um_bulk_confirm"]
                        _bc_n = len(_bcp["users"])
                        st.warning(
                            f"Apply **{_bcp['action']}** to **{_bc_n}** user(s)?  \n"
                            + ("Target role: `" + str(_bcp["role"]) + "`  \n" if _bcp["role"] else "")
                            + "This action will be audit logged."
                        )
                        _bcy, _bcn = st.columns(2)
                        with _bcy:
                            if st.button("Yes, apply", key="um_bulk_yes", type="primary"):
                                _bulk_errors = []
                                for _bun in _bcp["users"]:
                                    try:
                                        _ba = _bcp["action"]
                                        if _ba == "Enable":
                                            if _hp("users.enable"):
                                                _err = _update_admin_user(_bun, is_active=True)
                                                if not _err:
                                                    _log_um("enable_user", _bun, actor=_actor())
                                        elif _ba == "Disable":
                                            if _hp("users.disable"):
                                                _err = _update_admin_user(_bun, is_active=False)
                                                _force_logout_user(_bun)
                                                if not _err:
                                                    _log_um("disable_user", _bun, actor=_actor())
                                        elif _ba == "Force Logout":
                                            if _hp("users.force_logout"):
                                                _force_logout_user(_bun)
                                                _log_um("force_logout_user", _bun, actor=_actor())
                                                _err = None
                                        elif _ba == "Delete":
                                            if _hp("users.delete"):
                                                _err = _delete_admin_user(_bun)
                                                if not _err:
                                                    _log_um("delete_user", _bun, actor=_actor())
                                        elif _ba == "Assign Role":
                                            if _hp("users.assign_roles") and _bcp["role"]:
                                                _err = _update_admin_user(_bun, role=_bcp["role"])
                                                if not _err:
                                                    _log_um("assign_role", _bun,
                                                            _bcp["role"], actor=_actor())
                                        else:
                                            _err = None
                                        if _err:
                                            _bulk_errors.append(f"{_bun}: {_err}")
                                    except Exception as _be:
                                        _bulk_errors.append(f"{_bun}: {_be}")
                                if _bulk_errors:
                                    st.error("Some actions failed:\n" + "\n".join(_bulk_errors))
                                else:
                                    st.success(
                                        f"**{_bcp['action']}** applied to {len(_bcp['users'])} user(s)."
                                    )
                                st.session_state.pop("um_bulk_confirm", None)
                                st.rerun()
                        with _bcn:
                            if st.button("Cancel", key="um_bulk_no"):
                                st.session_state.pop("um_bulk_confirm", None)
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
                            _log_um("edit_user", _un, f"role={_ed_role}", actor=_actor())
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
                                        _un, actor=_actor())
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
                                _log_um("reset_password", _un, actor=_actor())
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
                                _log_um("delete_user", _un, actor=_actor())
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
                            f"{len(_new_perms_set)} permissions",
                            actor=_actor())
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
                                actor=_actor(),
                            )
                            _grp.clear()
                            if _sel_role == _actor_role:
                                st.session_state.user_permissions = frozenset(_def_perms)
                            st.success(
                                f"✅ Permissions for **{_role_labels.get(_sel_role, _sel_role)}** "
                                f"reset to defaults ({_def_count} permissions)."
                            )
                            st.rerun()

            # ── Clone Role ────────────────────────────────────────────────────
            if _can_edit and not _is_sa:
                st.divider()
                st.markdown("#### Clone Permissions to Another Role")
                st.caption(
                    "Copy all permissions from the selected role into another role, "
                    "overwriting its current permissions."
                )
                _clone_targets = [r for r in _role_names if r != _sel_role and r != "super_admin"]
                if _clone_targets:
                    _clone_to = st.selectbox(
                        "Clone INTO role",
                        options=_clone_targets,
                        format_func=lambda r: _role_labels.get(r, r),
                        key="roles_clone_target",
                    )
                    if st.button(f"📋 Clone → {_role_labels.get(_clone_to, _clone_to)}",
                                 key="roles_clone_btn", type="primary"):
                        _clone_perms = list(_current_rp)
                        _cerr = _set_role_perms(_clone_to, _clone_perms, _actor_role)
                        if _cerr:
                            st.error(f"Clone failed: {_cerr}")
                        else:
                            from core.db_logger import log_admin_action as _log_cl
                            _log_cl("clone_permissions",
                                    f"{_sel_role}→{_clone_to}",
                                    f"{len(_clone_perms)} permissions",
                                    actor=_actor())
                            _grp.clear()
                            st.success(
                                f"Permissions from **{_role_labels.get(_sel_role, _sel_role)}** "
                                f"cloned to **{_role_labels.get(_clone_to, _clone_to)}** "
                                f"({len(_clone_perms)} permissions)."
                            )
                            st.rerun()

            # ── Compare Roles ──────────────────────────────────────────────────
            st.divider()
            st.markdown("#### Compare Two Roles")
            _cmp_c1, _cmp_c2 = st.columns(2)
            with _cmp_c1:
                _cmp_role_a = st.selectbox(
                    "Role A", options=_role_names,
                    format_func=lambda r: _role_labels.get(r, r),
                    key="cmp_role_a", index=0,
                )
            with _cmp_c2:
                _cmp_role_b = st.selectbox(
                    "Role B", options=_role_names,
                    format_func=lambda r: _role_labels.get(r, r),
                    key="cmp_role_b",
                    index=min(1, len(_role_names) - 1),
                )
            if st.button("🔍 Compare", key="cmp_roles_btn"):
                _perms_a = frozenset(_ALL_PERM_KEYS) if _cmp_role_a == "super_admin" else _grp(_cmp_role_a)
                _perms_b = frozenset(_ALL_PERM_KEYS) if _cmp_role_b == "super_admin" else _grp(_cmp_role_b)
                _la = _role_labels.get(_cmp_role_a, _cmp_role_a)
                _lb = _role_labels.get(_cmp_role_b, _cmp_role_b)
                _hdr_c1, _hdr_c2, _hdr_c3 = st.columns([3, 1, 1])
                _hdr_c1.markdown("**Permission**")
                _hdr_c2.markdown(f"**{_la}**")
                _hdr_c3.markdown(f"**{_lb}**")
                st.divider()
                for _cp in sorted(_all_perms, key=lambda p: (p["category"], p["sort_order"])):
                    _ck = _cp["key"]
                    _ccat = _cp.get("category", "")
                    _cc1, _cc2, _cc3 = st.columns([3, 1, 1])
                    _cc1.caption(f"*{_ccat}* · {_cp['label']}")
                    _cc2.markdown("✅" if _ck in _perms_a else "—")
                    _cc3.markdown("✅" if _ck in _perms_b else "—")


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
                                log_admin_action("rebuild", _bsrc, actor=_actor())
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


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Overview
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "overview":
    if not _hp("dashboard.view"):
        _show_403("dashboard.view")
    else:
        st.subheader("System Overview")

        # ── Metrics ───────────────────────────────────────────────────────────
        try:
            from core.auth import get_all_users as _gau_ov
            from core.settings_store import get_enabled_sources as _ges_ov
            from core.db_logger import fetch_logs as _fl_ov
            from config import get_settings as _gs_ov
            import pandas as _pd_ov

            _users_ov  = _gau_ov()
            _active_ov = sum(1 for u in _users_ov if u.get("is_active", True))
            _srcs_ov   = _ges_ov()
            _cfg_ov    = _gs_ov()

            _total_docs_ov = 0
            _src_doc_counts: dict[str, int] = {}
            for _src_ov in _srcs_ov:
                _ddir_ov = _cfg_ov.docs_dir_for(_src_ov)
                _cnt_ov  = len([f for f in _ddir_ov.iterdir()
                                  if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}]
                                ) if _ddir_ov.exists() else 0
                _src_doc_counts[_src_ov] = _cnt_ov
                _total_docs_ov += _cnt_ov

            # Logs from the last 24 hours
            _logs_ov, _ = _fl_ov(limit=500)
            _df_ov = _pd_ov.DataFrame(_logs_ov) if _logs_ov else _pd_ov.DataFrame()
            _queries_today  = 0
            _failed_logins_ov = 0
            if not _df_ov.empty and "ts" in _df_ov.columns:
                _df_ov["_dt"] = _pd_ov.to_datetime(_df_ov["ts"], utc=True, errors="coerce")
                _cutoff = _pd_ov.Timestamp.now(tz="UTC") - _pd_ov.Timedelta(hours=24)
                _recent_ov = _df_ov[_df_ov["_dt"] >= _cutoff]
                _queries_today = int(len(_recent_ov[
                    _recent_ov.get("log_type", _pd_ov.Series(dtype=str)) != "admin_action"
                ])) if "log_type" in _recent_ov.columns else len(_recent_ov)

            # KPI cards
            _kpi_data = [
                ("Total Users",    len(_users_ov),          f"{_active_ov} active",   "adm-badge-green"),
                ("Disabled Users", len(_users_ov)-_active_ov, "accounts locked",      "adm-badge-red"),
                ("Sources",        len(_srcs_ov),           "knowledge bases",         "adm-badge-blue"),
                ("Documents",      _total_docs_ov,          "across all sources",      "adm-badge-blue"),
                ("Queries 24 h",   _queries_today,          "last 24 hours",           "adm-badge-yellow"),
            ]
            _kpi_cols = st.columns(len(_kpi_data))
            for _ki, (_klbl, _kval, _ksub, _kbadge) in enumerate(_kpi_data):
                with _kpi_cols[_ki]:
                    st.metric(_klbl, _kval, delta=None)

        except Exception as _exc_ov:
            st.warning(f"Could not load metrics: {_exc_ov}")

        st.divider()

        # ── Source health + Recent activity ────────────────────────────────────
        _ov_left, _ov_right = st.columns([3, 2])

        with _ov_left:
            st.markdown("**Recent Activity**")
            try:
                from core.db_logger import fetch_logs as _fl2_ov
                _recent_acts, _ = _fl2_ov(log_type="admin_action", limit=10)
                if _recent_acts:
                    for _ra in _recent_acts:
                        _ts_ra    = str(_ra.get("ts", ""))[:16]
                        _qr       = _html.escape(str(_ra.get("query", "") or ""))
                        _src_ra   = _html.escape(str(_ra.get("source", "") or ""))
                        _actor_ra = _html.escape(str(_ra.get("answer_preview", "") or ""))
                        _who      = f"by <strong>{_actor_ra}</strong>" if _actor_ra else ""
                        st.markdown(
                            f'<div class="adm-activity-row adm-log-admin">'
                            f'<span class="adm-ts">{_ts_ra}</span>'
                            f'<span>{_qr}</span>&nbsp;{_who}'
                            f'{"&nbsp;<em>" + _src_ra + "</em>" if _src_ra else ""}'
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("No admin actions recorded yet.")
            except Exception as _exc2_ov:
                st.caption(f"Activity unavailable: {_exc2_ov}")

        with _ov_right:
            st.markdown("**Source Health**")
            try:
                for _src_ov2 in _srcs_ov:
                    _idir_ov = _cfg_ov.db_dir_for(_src_ov2)
                    _ddir_ov2 = _cfg_ov.docs_dir_for(_src_ov2)
                    _em_ov, _det_ov = _index_status(_idir_ov, _ddir_ov2)
                    _dc_ov = _src_doc_counts.get(_src_ov2, 0)
                    st.markdown(
                        f'{_em_ov} **{_src_ov2}** &nbsp; '
                        f'<span class="adm-badge adm-badge-gray">{_dc_ov} docs</span>',
                        unsafe_allow_html=True,
                    )
            except Exception:
                st.caption("Status unavailable")

        st.divider()

        # ── Quick Actions ──────────────────────────────────────────────────────
        st.markdown("**Quick Actions**")
        _qa_cols = st.columns(5)
        _qa_items = [
            ("📋 Logs",      "logs"),
            ("👥 Users",     "users"),
            ("📁 Documents", "docs"),
            ("🔐 Roles",     "roles"),
            ("🛡️ Security", "security"),
        ]
        for _qai, (_qa_lbl, _qa_key) in enumerate(_qa_items):
            with _qa_cols[_qai]:
                if st.button(_qa_lbl, use_container_width=True, key=f"qa_{_qa_key}"):
                    st.session_state["admin_nav_key"] = _qa_key
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Analytics
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "analytics":
    if not _hp("dashboard.analytics"):
        _show_403("dashboard.analytics")
    else:
        st.subheader("Analytics")

        try:
            import pandas as _pd_an
            from core.db_logger import fetch_logs as _fl_an

            _an_c1, _an_c2 = st.columns([2, 1])
            with _an_c1:
                _an_date_from = st.date_input(
                    "From", value=datetime.date.today() - datetime.timedelta(days=30),
                    key="an_date_from",
                )
            with _an_c2:
                _an_limit = st.number_input("Max rows", 100, 2000, 500, 100, key="an_limit")

            if st.button("📊 Load Analytics", type="primary", key="an_load_btn"):
                with st.spinner("Loading analytics data…"):
                    _an_rows, _an_err = _fl_an(
                        limit=int(_an_limit),
                        date_from=_an_date_from,
                    )

                if _an_err:
                    st.error(f"Cannot load data: {_an_err}")
                elif not _an_rows:
                    st.info("No data in this date range.")
                else:
                    _df_an = _pd_an.DataFrame(_an_rows)

                    if "ts" in _df_an.columns:
                        _df_an["ts_dt"] = _pd_an.to_datetime(_df_an["ts"], errors="coerce", utc=True)
                        _df_an["date"]  = _df_an["ts_dt"].dt.date

                    # ── Summary metrics ───────────────────────────────────────
                    _an_tot   = len(_df_an)
                    _an_unans = len(_df_an[_df_an["log_type"] == "unanswered"]) if "log_type" in _df_an.columns else 0
                    _an_fb    = len(_df_an[_df_an["log_type"] == "feedback"]) if "log_type" in _df_an.columns else 0
                    _an_adm   = len(_df_an[_df_an["log_type"] == "admin_action"]) if "log_type" in _df_an.columns else 0

                    _an_m1, _an_m2, _an_m3, _an_m4 = st.columns(4)
                    _an_m1.metric("Total Events",       _an_tot)
                    _an_m2.metric("Unanswered Queries", _an_unans)
                    _an_m3.metric("Feedback Events",    _an_fb)
                    _an_m4.metric("Admin Actions",      _an_adm)

                    st.divider()

                    # ── Charts row 1 ──────────────────────────────────────────
                    _ch_c1, _ch_c2 = st.columns(2)

                    with _ch_c1:
                        st.markdown("##### Events by Type")
                        if "log_type" in _df_an.columns:
                            _type_counts = _df_an["log_type"].value_counts()
                            st.bar_chart(_type_counts)

                    with _ch_c2:
                        st.markdown("##### Events by Source")
                        if "source" in _df_an.columns:
                            _src_counts = _df_an["source"].dropna().value_counts()
                            if not _src_counts.empty:
                                st.bar_chart(_src_counts)
                            else:
                                st.info("No source data.")

                    # ── Daily trend ───────────────────────────────────────────
                    st.markdown("##### Daily Activity Trend")
                    if "date" in _df_an.columns:
                        _daily_an = _df_an.groupby("date").size().rename("events")
                        _all_dates_an = _pd_an.date_range(
                            _an_date_from, datetime.date.today()
                        ).date
                        _daily_an = _daily_an.reindex(_all_dates_an, fill_value=0)
                        st.area_chart(_daily_an)

                    # ── Feedback satisfaction ─────────────────────────────────
                    if "vote" in _df_an.columns:
                        _fb_an = _df_an[_df_an.get("log_type", "") == "feedback"] if "log_type" in _df_an.columns else _pd_an.DataFrame()
                        if not _fb_an.empty:
                            st.divider()
                            st.markdown("##### User Satisfaction (Feedback)")
                            _vc_an = _fb_an["vote"].value_counts()
                            _up_an   = int(_vc_an.get("up", 0))
                            _down_an = int(_vc_an.get("down", 0))
                            _tot_fb_an = _up_an + _down_an
                            _sat_an = f"{100*_up_an//_tot_fb_an}%" if _tot_fb_an else "N/A"
                            _fb_c1, _fb_c2, _fb_c3 = st.columns(3)
                            _fb_c1.metric("👍 Positive",  _up_an)
                            _fb_c2.metric("👎 Negative",  _down_an)
                            _fb_c3.metric("Satisfaction", _sat_an)

                    # ── Download ───────────────────────────────────────────────
                    st.divider()
                    import json as _json_an
                    _an_dl_c1, _an_dl_c2 = st.columns(2)
                    with _an_dl_c1:
                        st.download_button(
                            "⬇️ Export CSV",
                            data=_df_an.to_csv(index=False).encode("utf-8"),
                            file_name=f"analytics_{datetime.date.today()}.csv",
                            mime="text/csv", key="an_dl_csv",
                        )
                    with _an_dl_c2:
                        st.download_button(
                            "⬇️ Export JSON",
                            data=_json_an.dumps(_an_rows, default=str).encode("utf-8"),
                            file_name=f"analytics_{datetime.date.today()}.json",
                            mime="application/json", key="an_dl_json",
                        )

        except Exception as _exc_an:
            st.error(f"Analytics error: {_exc_an}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Audit Trail
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "audit":
    if not _hp("audit.view"):
        _show_403("audit.view")
    else:
        st.subheader("Audit Trail")
        st.caption(
            "All admin actions — who changed what and when.  "
            "Stored in the `logs` table with `log_type = admin_action`."
        )

        # ── Filters ───────────────────────────────────────────────────────────
        _au_c1, _au_c2, _au_c3 = st.columns([3, 2, 2])
        with _au_c1:
            _au_search = st.text_input("🔍 Search actions", key="audit_search",
                                        placeholder="Keyword…", label_visibility="collapsed")
        with _au_c2:
            _au_from = st.date_input("From date", value=None, key="audit_from",
                                      label_visibility="collapsed")
        with _au_c3:
            _au_to = st.date_input("To date", value=None, key="audit_to",
                                    label_visibility="collapsed")

        _au_limit = st.number_input("Max rows", 10, 1000, 200, 10, key="audit_limit")

        if st.button("🔄 Load Audit Trail", type="primary", key="audit_load_btn"):
            try:
                import pandas as _pd_au
                import json as _json_au
                from core.db_logger import fetch_logs as _fl_au
                _au_rows, _au_err = _fl_au(
                    log_type="admin_action",
                    limit=int(_au_limit),
                    date_from=_au_from or None,
                    date_to=_au_to or None,
                    search=_au_search.strip() or None,
                )
                if _au_err:
                    st.error(f"Error: {_au_err}")
                elif not _au_rows:
                    st.info("No audit records match your filters.")
                else:
                    _df_au = _pd_au.DataFrame(_au_rows)
                    st.success(f"**{len(_df_au)}** audit records found.")

                    # Rename answer_preview → actor for display (migration 005 adds real column)
                    _display_cols = {}
                    if "ts" in _df_au.columns:
                        _display_cols["ts"] = "Timestamp"
                    if "answer_preview" in _df_au.columns:
                        _df_au = _df_au.rename(columns={"answer_preview": "actor"})
                    if "actor" in _df_au.columns:
                        _display_cols["actor"] = "Actor"
                    if "query" in _df_au.columns:
                        _display_cols["query"] = "Action"
                    if "source" in _df_au.columns:
                        _display_cols["source"] = "Resource"

                    _show_df = _df_au[[c for c in _display_cols if c in _df_au.columns]].rename(columns=_display_cols)
                    st.dataframe(
                        _show_df,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Timestamp": st.column_config.DatetimeColumn("Timestamp", format="YYYY-MM-DD HH:mm:ss"),
                        },
                    )

                    # ── Export ─────────────────────────────────────────────────
                    _au_dl_c1, _au_dl_c2 = st.columns(2)
                    with _au_dl_c1:
                        st.download_button(
                            "⬇️ Export CSV",
                            data=_df_au.to_csv(index=False).encode("utf-8"),
                            file_name=f"audit_{datetime.date.today()}.csv",
                            mime="text/csv", key="audit_dl_csv",
                        )
                    with _au_dl_c2:
                        st.download_button(
                            "⬇️ Export JSON",
                            data=_json_au.dumps(_au_rows, default=str, indent=2).encode("utf-8"),
                            file_name=f"audit_{datetime.date.today()}.json",
                            mime="application/json", key="audit_dl_json",
                        )
            except Exception as _exc_au:
                st.error(f"Audit error: {_exc_au}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Security Center
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "security":
    if not _hp("security.view"):
        _show_403("security.view")
    else:
        st.subheader("Security Center")

        _sec_t1, _sec_t2, _sec_t3 = st.tabs(["🔑 Active Sessions", "📋 Login History", "🔒 Account Lockouts"])

        # ── Active Sessions ────────────────────────────────────────────────────
        with _sec_t1:
            st.markdown("#### All Active Admin Sessions")
            st.caption("Sessions that have not yet expired. Refresh to update.")

            if st.button("🔄 Refresh Sessions", key="sec_refresh_sess"):
                try:
                    from core.db_logger import _get_client as _sec_db
                    _sc = _sec_db()
                    if _sc is None:
                        st.warning("Supabase unavailable — cannot list sessions.")
                    else:
                        _now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        _sess_resp = (
                            _sc.table("admin_sessions")
                            .select("id,username,created_at,expires_at")
                            .gt("expires_at", _now_utc)
                            .order("created_at", desc=True)
                            .limit(200)
                            .execute()
                        )
                        _sess_rows = _sess_resp.data or []
                        if not _sess_rows:
                            st.info("No active sessions found.")
                        else:
                            import pandas as _pd_sec
                            _df_sess = _pd_sec.DataFrame(_sess_rows)
                            # Mask token to first 8 chars
                            if "id" in _df_sess.columns:
                                _df_sess["token"] = _df_sess["id"].str[:8] + "…"
                            _df_sess_show = _df_sess[["username", "created_at", "expires_at", "token"]
                                                      if "token" in _df_sess.columns
                                                      else ["username", "created_at", "expires_at"]]
                            st.success(f"**{len(_sess_rows)}** active session(s).")
                            st.dataframe(_df_sess_show, use_container_width=True, hide_index=True)

                            # ── Force logout (super_admin only) ─────────────────
                            if st.session_state.get("admin_role") == "super_admin" and _hp("users.force_logout"):
                                st.divider()
                                st.markdown("#### Force Logout")
                                _my_user = st.session_state.get("admin_username", "")
                                _other_users = sorted(set(
                                    s["username"] for s in _sess_rows if s.get("username") != _my_user
                                ))
                                if _other_users:
                                    _flu_target = st.selectbox("Select user to log out",
                                                                _other_users, key="sec_flu_target")
                                    if st.button(f"🚫 Force Logout {_flu_target}",
                                                  type="primary", key="sec_flu_btn"):
                                        from core.auth import force_logout_user as _flu_fn
                                        from core.db_logger import log_admin_action as _log_flu
                                        _flu_err = _flu_fn(_flu_target)
                                        if _flu_err:
                                            st.error(_flu_err)
                                        else:
                                            _log_flu("force_logout", _flu_target, actor=_actor())
                                            st.success(f"All sessions for **{_flu_target}** revoked.")
                                            st.rerun()
                                else:
                                    st.info("No other users have active sessions.")
                except Exception as _exc_sec:
                    st.error(f"Session error: {_exc_sec}")

        # ── Login History ──────────────────────────────────────────────────────
        with _sec_t2:
            st.markdown("#### Login Attempt History")
            st.caption("Records every login attempt (success + failure). Requires migration 005.")

            _lh_c1, _lh_c2, _lh_c3 = st.columns([2, 1, 1])
            with _lh_c1:
                _lh_user_sel = ""
                if _hp("users.view"):
                    _lh_user_sel = st.text_input("Username (blank = all)", key="sec_lh_user")
                else:
                    _lh_user_sel = st.session_state.get("admin_username", "")
                    st.caption(f"Showing history for: **{_lh_user_sel}**")
            with _lh_c2:
                _lh_outcome = st.selectbox("Outcome", ["all", "success", "failed"],
                                            key="sec_lh_outcome")
            with _lh_c3:
                _lh_limit = st.number_input("Limit", 10, 500, 100, 10, key="sec_lh_limit")

            if st.button("🔄 Load History", key="sec_lh_load"):
                try:
                    import pandas as _pd_lh
                    from core.db_logger import fetch_login_history as _flh_sec
                    _lh_rows, _lh_err = _flh_sec(
                        username=_lh_user_sel.strip() or None,
                        limit=int(_lh_limit),
                    )
                    if _lh_err:
                        st.error(f"Error: {_lh_err}")
                    elif not _lh_rows:
                        st.info("No login history found. Ensure migration 005 has been run.")
                    else:
                        _df_lh_sec = _pd_lh.DataFrame(_lh_rows)
                        if "success" in _df_lh_sec.columns:
                            _df_lh_sec["status"] = _df_lh_sec["success"].map(
                                {True: "✅ Success", False: "❌ Failed"}
                            )
                            if _lh_outcome == "success":
                                _df_lh_sec = _df_lh_sec[_df_lh_sec["success"] == True]  # noqa: E712
                            elif _lh_outcome == "failed":
                                _df_lh_sec = _df_lh_sec[_df_lh_sec["success"] == False]  # noqa: E712

                        _s_sec = int(_df_lh_sec["success"].sum()) if "success" in _df_lh_sec.columns else 0
                        _f_sec = len(_df_lh_sec) - _s_sec
                        _lh_m1, _lh_m2, _lh_m3 = st.columns(3)
                        _lh_m1.metric("Total Attempts", len(_df_lh_sec))
                        _lh_m2.metric("✅ Successful",   _s_sec)
                        _lh_m3.metric("❌ Failed",       _f_sec)

                        _show_lh_cols = ["username", "status", "created_at"] if "status" in _df_lh_sec.columns else _df_lh_sec.columns.tolist()
                        st.dataframe(
                            _df_lh_sec[_show_lh_cols],
                            use_container_width=True, hide_index=True,
                            column_config={
                                "created_at": st.column_config.DatetimeColumn("Time", format="YYYY-MM-DD HH:mm:ss"),
                            },
                        )
                except Exception as _exc_lh:
                    st.error(f"Login history error: {_exc_lh}")

        # ── Account Lockouts ───────────────────────────────────────────────────
        with _sec_t3:
            st.markdown("#### In-Process Login Rate Limiting")
            st.caption(
                "Shows accounts currently tracked for failed login attempts "
                "(in-process only — resets when the Streamlit server restarts)."
            )
            if st.session_state.get("admin_role") in ("super_admin", "admin"):
                try:
                    from core.auth import _login_failures as _lf_dict, _LOCKOUT_WINDOW_SECS, _MAX_LOGIN_ATTEMPTS
                    import time as _time_sec
                    _now_sec = _time_sec.monotonic()
                    _active_fails = {
                        _u: [t for t in _ts if _now_sec - t < _LOCKOUT_WINDOW_SECS]
                        for _u, _ts in _lf_dict.items()
                    }
                    _active_fails = {u: ts for u, ts in _active_fails.items() if ts}
                    if not _active_fails:
                        st.success("No accounts have recent failed login attempts.")
                    else:
                        st.warning(f"{len(_active_fails)} account(s) have recent failed attempts.")
                        for _u_lk, _ts_lk in _active_fails.items():
                            _cnt_lk = len(_ts_lk)
                            _locked_lk = _cnt_lk >= _MAX_LOGIN_ATTEMPTS
                            _badge_lk = "🔴 LOCKED" if _locked_lk else f"⚠️ {_cnt_lk} failures"
                            st.markdown(f"- **{_u_lk}**: {_badge_lk}")
                except Exception as _exc_lk:
                    st.info(f"Lockout data unavailable: {_exc_lk}")
            else:
                st.info("Lockout monitoring requires Admin or Super Admin role.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Feature Flags
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "features":
    from admin_tabs.feature_flags import render_feature_flags_tab
    render_feature_flags_tab()


# ─────────────────────────────────────────────────────────────────────────────
# TAB: System Health
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "syshealth":
    from admin_tabs.system_health import render_system_health_tab
    render_system_health_tab()


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Email Templates
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "emailtmpls":
    from admin_tabs.email_templates import render_email_templates_tab
    render_email_templates_tab()


# ─────────────────────────────────────────────────────────────────────────────
# TAB: API Keys
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "apikeys":
    from admin_tabs.api_keys import render_api_keys_tab
    render_api_keys_tab()


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Notifications
# ─────────────────────────────────────────────────────────────────────────────
if _sel_nav == "notifications":
    from admin_tabs.notifications import render_notifications_tab
    render_notifications_tab()
