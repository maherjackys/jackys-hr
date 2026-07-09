"""Feature Flags tab — render_feature_flags_tab()"""
from __future__ import annotations
import streamlit as st


def render_feature_flags_tab() -> None:
    from core.rbac import has_permission
    from core.feature_flags import (
        list_feature_flags, set_feature_flag, delete_feature_flag, is_valid_flag_key,
    )
    from core.db_logger import log_admin_action

    _actor = st.session_state.get("admin_username", "")
    _can_edit = has_permission("features.edit")

    st.subheader("🚩 Feature Flags")
    st.caption(
        "Toggle application features without redeployment.  "
        "Changes take effect within 30 seconds (cache TTL)."
    )

    # ── Search + Add ──────────────────────────────────────────────────────────
    _col_search, _col_add = st.columns([3, 1])
    with _col_search:
        _ff_search = st.text_input(
            "Search flags", key="ff_search",
            placeholder="Filter by key or description…",
            label_visibility="collapsed",
        )
    with _col_add:
        if _can_edit and st.button("➕ Add Flag", use_container_width=True, key="ff_add_btn"):
            st.session_state["ff_show_add"] = not st.session_state.get("ff_show_add", False)

    # ── Add new flag form ─────────────────────────────────────────────────────
    if _can_edit and st.session_state.get("ff_show_add"):
        with st.expander("New Feature Flag", expanded=True):
            with st.form("ff_new_form", clear_on_submit=True):
                _nk = st.text_input("Key (lowercase, underscore)", key="ff_new_key",
                                     placeholder="e.g. new_feature_xyz")
                _nd = st.text_input("Description", key="ff_new_desc")
                _ne = st.checkbox("Enabled by default", value=True, key="ff_new_enabled")
                _sub = st.form_submit_button("Create Flag", type="primary")
            if _sub:
                if not _nk:
                    st.error("Key is required.")
                elif not is_valid_flag_key(_nk):
                    st.error("Key must start with a letter and contain only lowercase letters, digits, underscore.")
                else:
                    _err = set_feature_flag(_nk, _ne, _nd, actor=_actor)
                    if _err:
                        st.error(f"Failed: {_err}")
                    else:
                        log_admin_action("create_feature_flag", _nk,
                                         f"enabled={_ne}", actor=_actor)
                        st.success(f"Flag `{_nk}` created.")
                        st.session_state["ff_show_add"] = False
                        st.rerun()

    st.divider()

    # ── Flag list ─────────────────────────────────────────────────────────────
    _flags = list_feature_flags()
    if _ff_search.strip():
        _q = _ff_search.lower()
        _flags = [f for f in _flags
                  if _q in f.get("key", "").lower() or _q in f.get("description", "").lower()]

    if not _flags:
        st.info("No feature flags found." if not _ff_search.strip() else "No flags match your search.")
        return

    _updated_at_label = "Last updated"

    # Column headers
    _h1, _h2, _h3, _h4, _h5 = st.columns([2, 4, 1, 2, 1])
    _h1.markdown("**Key**")
    _h2.markdown("**Description**")
    _h3.markdown("**State**")
    _h4.markdown(_updated_at_label)
    _h5.markdown("**Actions**")
    st.markdown("---")

    for _flag in _flags:
        _fk       = _flag.get("key", "")
        _fdesc    = _flag.get("description", "")
        _fenabled = bool(_flag.get("enabled", False))
        _fup_at   = str(_flag.get("updated_at") or "—")[:16]
        _fup_by   = _flag.get("updated_by") or "—"

        _c1, _c2, _c3, _c4, _c5 = st.columns([2, 4, 1, 2, 1])

        with _c1:
            st.code(_fk, language=None)

        with _c2:
            st.caption(_fdesc or "—")

        with _c3:
            _badge_cls = "adm-badge-green" if _fenabled else "adm-badge-red"
            _badge_txt = "ON" if _fenabled else "OFF"
            st.markdown(
                f'<span class="adm-badge {_badge_cls}">{_badge_txt}</span>',
                unsafe_allow_html=True,
            )

        with _c4:
            st.caption(f"{_fup_at}  by {_fup_by}")

        with _c5:
            if _can_edit:
                if st.button("✏️", key=f"ff_edit_{_fk}", help="Edit"):
                    st.session_state[f"ff_editing_{_fk}"] = True

        # ── Inline edit ───────────────────────────────────────────────────────
        if _can_edit and st.session_state.get(f"ff_editing_{_fk}"):
            with st.container():
                st.markdown(f"**Edit: `{_fk}`**")
                with st.form(f"ff_edit_form_{_fk}", clear_on_submit=False):
                    _ed_desc = st.text_input("Description", value=_fdesc, key=f"ff_ed_desc_{_fk}")
                    _ed_en   = st.toggle("Enabled", value=_fenabled, key=f"ff_ed_en_{_fk}")
                    _ed_c1, _ed_c2, _ed_c3 = st.columns([2, 2, 2])
                    with _ed_c1:
                        _save = st.form_submit_button("💾 Save", type="primary", use_container_width=True)
                    with _ed_c2:
                        _cancel = st.form_submit_button("Cancel", use_container_width=True)
                    with _ed_c3:
                        _delete = st.form_submit_button("🗑️ Delete", use_container_width=True)

                if _cancel:
                    st.session_state.pop(f"ff_editing_{_fk}", None)
                    st.rerun()

                if _save:
                    _confirm_key = f"ff_confirm_save_{_fk}"
                    # Show confirm if enabling/disabling changed
                    if _ed_en != _fenabled:
                        st.session_state[_confirm_key] = {
                            "desc": _ed_desc, "enabled": _ed_en,
                        }
                    else:
                        _err = set_feature_flag(_fk, _ed_en, _ed_desc, actor=_actor)
                        if _err:
                            st.error(f"Failed: {_err}")
                        else:
                            log_admin_action("update_feature_flag", _fk,
                                             f"enabled={_ed_en}", actor=_actor)
                            st.success(f"Flag `{_fk}` updated.")
                            st.session_state.pop(f"ff_editing_{_fk}", None)
                            st.rerun()

                if st.session_state.get(f"ff_confirm_save_{_fk}"):
                    _pending = st.session_state[f"ff_confirm_save_{_fk}"]
                    _verb = "ENABLE" if _pending["enabled"] else "DISABLE"
                    st.warning(f"Confirm: **{_verb}** flag `{_fk}`?")
                    _yc, _nc = st.columns(2)
                    with _yc:
                        if st.button("Yes, confirm", key=f"ff_yes_{_fk}", type="primary"):
                            _err = set_feature_flag(_fk, _pending["enabled"],
                                                    _pending["desc"], actor=_actor)
                            if _err:
                                st.error(f"Failed: {_err}")
                            else:
                                log_admin_action("update_feature_flag", _fk,
                                                 f"enabled={_pending['enabled']}", actor=_actor)
                                st.success(f"Flag `{_fk}` set to **{_verb}**.")
                            st.session_state.pop(f"ff_confirm_save_{_fk}", None)
                            st.session_state.pop(f"ff_editing_{_fk}", None)
                            st.rerun()
                    with _nc:
                        if st.button("Cancel", key=f"ff_no_{_fk}"):
                            st.session_state.pop(f"ff_confirm_save_{_fk}", None)
                            st.rerun()

                if _delete:
                    st.session_state[f"ff_confirm_del_{_fk}"] = True

                if st.session_state.get(f"ff_confirm_del_{_fk}"):
                    st.error(f"Permanently delete flag `{_fk}`? This cannot be undone.")
                    _dy, _dn = st.columns(2)
                    with _dy:
                        if st.button("Delete", key=f"ff_del_yes_{_fk}", type="primary"):
                            _derr = delete_feature_flag(_fk)
                            if _derr:
                                st.error(_derr)
                            else:
                                log_admin_action("delete_feature_flag", _fk, actor=_actor)
                                st.success(f"Flag `{_fk}` deleted.")
                            st.session_state.pop(f"ff_confirm_del_{_fk}", None)
                            st.session_state.pop(f"ff_editing_{_fk}", None)
                            st.rerun()
                    with _dn:
                        if st.button("Cancel", key=f"ff_del_no_{_fk}"):
                            st.session_state.pop(f"ff_confirm_del_{_fk}", None)
                            st.rerun()

        st.markdown("---")

    st.caption(f"{len(_flags)} flag(s) shown.  Cache TTL: 30 s.")
