"""Notifications tab — render_notifications_tab()"""
from __future__ import annotations
import streamlit as st


_TYPE_BADGE = {
    "info":     ("adm-badge-blue",   "ℹ️ Info"),
    "warning":  ("adm-badge-yellow", "⚠️ Warning"),
    "error":    ("adm-badge-red",    "❌ Error"),
    "security": ("adm-badge-red",    "🔒 Security"),
}
_PRIORITY_LABEL = {1: "Low", 2: "Medium", 3: "🔴 High"}


def render_notifications_tab() -> None:
    from core.rbac import has_permission
    from core.notifications import (
        list_notifications, mark_read, mark_all_read,
        delete_notification, clear_all_read, get_unread_count,
        create_notification,
    )

    if not has_permission("notifications.view"):
        st.error("🚫 Permission denied: notifications.view required.")
        return

    _actor    = st.session_state.get("admin_username", "")
    _can_mgr  = st.session_state.get("admin_role") in ("super_admin", "admin")

    st.subheader("🔔 Notification Center")

    # ── Controls row ──────────────────────────────────────────────────────────
    _ctrl_c1, _ctrl_c2, _ctrl_c3, _ctrl_c4 = st.columns([2, 2, 2, 2])
    with _ctrl_c1:
        _unread_only = st.checkbox("Unread only", key="notif_unread_only")
    with _ctrl_c2:
        _type_filter = st.selectbox(
            "Type", options=["all", "info", "warning", "error", "security"],
            key="notif_type_filter", label_visibility="collapsed",
        )
    with _ctrl_c3:
        _notif_limit = st.number_input("Limit", 10, 200, 50, 10, key="notif_limit",
                                        label_visibility="collapsed")
    with _ctrl_c4:
        st.button("🔄 Refresh", key="notif_refresh", use_container_width=True)

    # ── Bulk actions ──────────────────────────────────────────────────────────
    if _can_mgr:
        _bulk_c1, _bulk_c2 = st.columns(2)
        with _bulk_c1:
            if st.button("✅ Mark All Read", use_container_width=True, key="notif_mark_all"):
                _merr = mark_all_read()
                if _merr:
                    st.error(_merr)
                else:
                    st.success("All notifications marked as read.")
                    st.rerun()
        with _bulk_c2:
            if st.button("🗑️ Clear All Read", use_container_width=True, key="notif_clear_all"):
                st.session_state["notif_confirm_clear"] = True

        if st.session_state.get("notif_confirm_clear"):
            st.warning("Delete all **read** notifications? This cannot be undone.")
            _cc1, _cc2 = st.columns(2)
            with _cc1:
                if st.button("Yes, delete", key="notif_clear_yes", type="primary"):
                    _cerr = clear_all_read()
                    if _cerr:
                        st.error(_cerr)
                    else:
                        st.success("Read notifications cleared.")
                    st.session_state.pop("notif_confirm_clear", None)
                    st.rerun()
            with _cc2:
                if st.button("Cancel", key="notif_clear_no"):
                    st.session_state.pop("notif_confirm_clear", None)
                    st.rerun()

    st.divider()

    # ── Notification list ─────────────────────────────────────────────────────
    _tf = _type_filter if _type_filter != "all" else None
    _rows, _err = list_notifications(
        unread_only=_unread_only,
        type_filter=_tf,
        limit=int(_notif_limit),
    )

    if _err:
        st.error(f"Error loading notifications: {_err}")
        st.info("Ensure migration 007 has been run in Supabase.")
        return

    _unread_cnt = get_unread_count()
    if _unread_cnt > 0:
        st.markdown(
            f'<span class="adm-badge adm-badge-red">{_unread_cnt} unread</span>',
            unsafe_allow_html=True,
        )

    if not _rows:
        if _unread_only:
            st.success("✅ No unread notifications.")
        else:
            st.info("No notifications found.")
        return

    for _n in _rows:
        _nid    = _n["id"]
        _ntype  = _n.get("type", "info")
        _ntitle = _n.get("title", "—")
        _nmsg   = _n.get("message", "")
        _nread  = _n.get("is_read", False)
        _nprio  = _n.get("priority", 1)
        _nts    = str(_n.get("created_at", ""))[:16]

        _badge_cls, _badge_txt = _TYPE_BADGE.get(_ntype, ("adm-badge-gray", _ntype))
        _bg = "" if _nread else "background:var(--bg-input,#f9fafb);padding:.5rem .75rem;border-radius:6px;"

        with st.container():
            st.markdown(
                f'<div class="adm-activity-row" style="{_bg}">'
                f'<span class="adm-ts">{_nts}</span>'
                f'<span class="adm-badge {_badge_cls}">{_badge_txt}</span>'
                f'&nbsp; {"🔵 " if not _nread else ""}'
                f'<strong>{_ntitle}</strong>'
                f'&nbsp; <small>({_PRIORITY_LABEL.get(_nprio, "?")})</small>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if _nmsg:
                st.caption(f"  {_nmsg}")

            _nc1, _nc2, _nc3 = st.columns([2, 2, 8])
            with _nc1:
                if not _nread and st.button("✓ Read", key=f"notif_read_{_nid}", use_container_width=True):
                    mark_read(_nid)
                    st.rerun()
            with _nc2:
                if _can_mgr and st.button("🗑️", key=f"notif_del_{_nid}", help="Delete",
                                           use_container_width=True):
                    delete_notification(_nid)
                    st.rerun()

        st.markdown("---")

    st.caption(f"{len(_rows)} notification(s) shown.")

    # ── Test notification (super_admin only) ──────────────────────────────────
    if _can_mgr:
        with st.expander("🧪 Create Test Notification"):
            with st.form("notif_test_form", clear_on_submit=True):
                _tn_title = st.text_input("Title", value="Test Notification")
                _tn_msg   = st.text_area("Message", value="This is a test notification from the admin dashboard.")
                _tn_type  = st.selectbox("Type", ["info", "warning", "error", "security"])
                _tn_prio  = st.selectbox("Priority", [1, 2, 3], format_func=lambda p: _PRIORITY_LABEL.get(p, str(p)))
                _tn_sub   = st.form_submit_button("Create", type="primary")
            if _tn_sub:
                _terr = create_notification(_tn_title, _tn_msg, type_=_tn_type, priority=_tn_prio)
                if _terr:
                    st.error(_terr)
                else:
                    st.success("Test notification created.")
                    st.rerun()
