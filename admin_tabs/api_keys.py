"""API Keys tab — render_api_keys_tab()"""
from __future__ import annotations
import streamlit as st


_STATUS_BADGE = {
    "active":   ("adm-badge-green",  "Active"),
    "disabled": ("adm-badge-yellow", "Disabled"),
    "revoked":  ("adm-badge-red",    "Revoked"),
}


def render_api_keys_tab() -> None:
    from core.rbac import has_permission
    from core.api_keys import generate_api_key, list_api_keys, revoke_api_key, set_key_status
    from core.db_logger import log_admin_action

    _actor    = st.session_state.get("admin_username", "")
    _can_mgr  = has_permission("api_keys.manage")

    st.subheader("🔑 API Keys")
    st.markdown(
        '<div class="adm-badge adm-badge-yellow" style="display:inline-block;margin-bottom:.75rem">'
        '⚠️ Keys are shown ONCE at creation time. Store them securely — they cannot be recovered.</div>',
        unsafe_allow_html=True,
    )

    # ── Generate ──────────────────────────────────────────────────────────────
    if _can_mgr:
        with st.expander("➕ Generate New API Key", expanded=bool(st.session_state.get("ak_just_created"))):
            if st.session_state.get("ak_just_created"):
                _new_key = st.session_state["ak_just_created"]
                st.success("✅ API key generated! **Copy it now — it will not be shown again.**")
                st.code(_new_key, language=None)
                if st.button("✅ I've copied it", key="ak_dismiss_key"):
                    st.session_state.pop("ak_just_created", None)
                    st.rerun()
            else:
                with st.form("ak_gen_form", clear_on_submit=True):
                    _ak_name   = st.text_input("Key name / description",
                                                placeholder="e.g. CI Pipeline, External Integration")
                    _ak_perms  = st.multiselect(
                        "Permissions (optional labels — for your reference only)",
                        options=["read:documents", "read:sources", "write:logs", "admin:all"],
                        key="ak_perms_sel",
                    )
                    _gen_btn = st.form_submit_button("🔑 Generate Key", type="primary",
                                                      use_container_width=True)
                if _gen_btn:
                    _raw, _err = generate_api_key(_ak_name, created_by=_actor,
                                                   permissions=_ak_perms)
                    if _err:
                        st.error(f"Failed: {_err}")
                    else:
                        log_admin_action("generate_api_key", _ak_name, actor=_actor)
                        st.session_state["ak_just_created"] = _raw
                        st.rerun()

    st.divider()

    # ── Key list ──────────────────────────────────────────────────────────────
    _inc_rev = st.checkbox("Show revoked keys", key="ak_show_revoked")
    _rows, _err = list_api_keys(include_revoked=_inc_rev)

    if _err:
        st.error(f"Could not load keys: {_err}")
        return

    if not _rows:
        st.info("No API keys found. Generate one above.")
        return

    # Header
    _ah1, _ah2, _ah3, _ah4, _ah5, _ah6 = st.columns([3, 2, 2, 2, 2, 2])
    _ah1.markdown("**Name**")
    _ah2.markdown("**Prefix**")
    _ah3.markdown("**Status**")
    _ah4.markdown("**Created**")
    _ah5.markdown("**Last Used**")
    _ah6.markdown("**Actions**")
    st.markdown("---")

    for _row in _rows:
        _rid   = _row["id"]
        _rname = _row.get("name", "—")
        _rpfx  = _row.get("key_prefix", "—") + "…"
        _rstat = _row.get("status", "unknown")
        _rcat  = str(_row.get("created_at", "—"))[:10]
        _rlast = str(_row.get("last_used_at", "") or "Never")[:16]
        _rby   = _row.get("created_by", "—")

        _badge_cls, _badge_txt = _STATUS_BADGE.get(_rstat, ("adm-badge-gray", _rstat))

        _c1, _c2, _c3, _c4, _c5, _c6 = st.columns([3, 2, 2, 2, 2, 2])
        with _c1:
            st.markdown(f"**{_rname}**")
            st.caption(f"by {_rby}")
        with _c2:
            st.code(_rpfx, language=None)
        with _c3:
            st.markdown(
                f'<span class="adm-badge {_badge_cls}">{_badge_txt}</span>',
                unsafe_allow_html=True,
            )
        with _c4:
            st.caption(_rcat)
        with _c5:
            st.caption(_rlast)
        with _c6:
            if _can_mgr and _rstat != "revoked":
                _btn_c1, _btn_c2 = st.columns(2)
                with _btn_c1:
                    _toggle_lbl  = "Enable"  if _rstat == "disabled" else "Disable"
                    _toggle_stat = "active"  if _rstat == "disabled" else "disabled"
                    if st.button(_toggle_lbl, key=f"ak_tog_{_rid}", use_container_width=True):
                        _terr = set_key_status(_rid, _toggle_stat)
                        if _terr:
                            st.error(_terr)
                        else:
                            log_admin_action(f"api_key_{_toggle_stat}", _rname, actor=_actor)
                            st.rerun()
                with _btn_c2:
                    if st.button("Revoke", key=f"ak_rev_{_rid}",
                                  use_container_width=True, type="primary"):
                        st.session_state[f"ak_confirm_rev_{_rid}"] = True

        if _can_mgr and st.session_state.get(f"ak_confirm_rev_{_rid}"):
            st.warning(f"Permanently revoke key **{_rname}**? This cannot be undone.")
            _ry, _rn = st.columns(2)
            with _ry:
                if st.button("Yes, revoke", key=f"ak_rev_yes_{_rid}", type="primary"):
                    _rerr = revoke_api_key(_rid)
                    if _rerr:
                        st.error(_rerr)
                    else:
                        log_admin_action("revoke_api_key", _rname, actor=_actor)
                        st.success(f"Key **{_rname}** revoked.")
                    st.session_state.pop(f"ak_confirm_rev_{_rid}", None)
                    st.rerun()
            with _rn:
                if st.button("Cancel", key=f"ak_rev_no_{_rid}"):
                    st.session_state.pop(f"ak_confirm_rev_{_rid}", None)
                    st.rerun()

        st.markdown("---")

    st.caption(f"{len(_rows)} key(s) listed.")
