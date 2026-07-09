"""Email Templates tab — render_email_templates_tab()"""
from __future__ import annotations
import streamlit as st


def render_email_templates_tab() -> None:
    from core.rbac import has_permission
    from core.email_templates import (
        TEMPLATE_NAMES, get_template, save_template, restore_default, render_preview,
    )
    from core.db_logger import log_admin_action

    _actor    = st.session_state.get("admin_username", "")
    _can_edit = has_permission("templates.edit")

    st.subheader("📧 Email Templates")
    st.caption(
        "Manage notification email templates.  "
        "Templates are stored in `app_settings` and used when sending emails to admins.  \n"
        "⚠️ Actual email sending requires SMTP / email-service configuration outside this dashboard."
    )

    # ── Template selector ─────────────────────────────────────────────────────
    _label_map = {
        "welcome":              "Welcome Email",
        "password_reset":       "Password Reset",
        "account_disabled":     "Account Disabled",
        "password_changed":     "Password Changed",
        "general_notification": "General Notification",
    }
    _sel_name = st.selectbox(
        "Select template",
        options=TEMPLATE_NAMES,
        format_func=lambda n: _label_map.get(n, n),
        key="tmpl_sel",
    )

    _tmpl = get_template(_sel_name)

    _updated_info = ""
    if _tmpl.get("updated_at"):
        _updated_info = (
            f"Last saved: **{str(_tmpl['updated_at'])[:16]}** "
            f"by {_tmpl.get('updated_by') or 'unknown'}"
        )
    else:
        _updated_info = "Using built-in default (not yet saved to database)"
    st.caption(_updated_info)

    # ── Variables reference ───────────────────────────────────────────────────
    if _tmpl.get("variables"):
        st.markdown(
            "**Available variables:** "
            + "  ·  ".join(f"`{v}`" for v in _tmpl["variables"])
        )

    st.divider()

    _tab_edit, _tab_preview = st.tabs(["✏️ Edit", "👁️ Preview"])

    # ── Edit tab ──────────────────────────────────────────────────────────────
    with _tab_edit:
        if not _can_edit:
            st.info("You have view-only access to email templates.")
            st.text_input("Subject", value=_tmpl.get("subject", ""), disabled=True, key="tmpl_sub_ro")
            st.text_area("Body", value=_tmpl.get("body", ""), height=300, disabled=True, key="tmpl_body_ro")
        else:
            with st.form(f"tmpl_form_{_sel_name}", clear_on_submit=False):
                _new_subject = st.text_input(
                    "Subject line",
                    value=_tmpl.get("subject", ""),
                    key=f"tmpl_sub_{_sel_name}",
                )
                _new_body = st.text_area(
                    "Body (plain text, use {{variable}} placeholders)",
                    value=_tmpl.get("body", ""),
                    height=300,
                    key=f"tmpl_body_{_sel_name}",
                )
                _fc1, _fc2, _fc3 = st.columns([2, 2, 2])
                with _fc1:
                    _save_btn = st.form_submit_button(
                        "💾 Save Template", type="primary", use_container_width=True,
                    )
                with _fc2:
                    _restore_btn = st.form_submit_button(
                        "🔄 Restore Default", use_container_width=True,
                    )

            if _save_btn:
                if not _new_subject.strip():
                    st.error("Subject cannot be empty.")
                elif not _new_body.strip():
                    st.error("Body cannot be empty.")
                else:
                    _err = save_template(_sel_name, _new_subject, _new_body, actor=_actor)
                    if _err:
                        st.error(f"Save failed: {_err}")
                    else:
                        log_admin_action("save_email_template", _sel_name, actor=_actor)
                        st.success(f"Template **{_label_map.get(_sel_name, _sel_name)}** saved.")
                        st.rerun()

            if _restore_btn:
                if not st.session_state.get(f"tmpl_confirm_restore_{_sel_name}"):
                    st.session_state[f"tmpl_confirm_restore_{_sel_name}"] = True
                    st.rerun()

            if st.session_state.get(f"tmpl_confirm_restore_{_sel_name}"):
                st.warning(
                    f"Restore **{_label_map.get(_sel_name, _sel_name)}** to built-in default? "
                    "This will overwrite any custom changes."
                )
                _rc1, _rc2 = st.columns(2)
                with _rc1:
                    if st.button("Yes, restore", key=f"tmpl_restore_yes_{_sel_name}", type="primary"):
                        _rerr = restore_default(_sel_name, actor=_actor)
                        if _rerr:
                            st.error(_rerr)
                        else:
                            log_admin_action("restore_email_template_default", _sel_name, actor=_actor)
                            st.success("Template restored to default.")
                        st.session_state.pop(f"tmpl_confirm_restore_{_sel_name}", None)
                        st.rerun()
                with _rc2:
                    if st.button("Cancel", key=f"tmpl_restore_no_{_sel_name}"):
                        st.session_state.pop(f"tmpl_confirm_restore_{_sel_name}", None)
                        st.rerun()

    # ── Preview tab ───────────────────────────────────────────────────────────
    with _tab_preview:
        st.markdown("#### Preview (with sample values)")
        _preview_subject = _tmpl.get("subject", "")
        _preview_body    = render_preview(_tmpl)

        st.markdown(f"**Subject:** {_preview_subject}")
        st.divider()
        st.text(_preview_body)
        st.divider()
        st.caption(
            "This preview uses sample values. "
            "Real emails substitute actual values at send time."
        )
