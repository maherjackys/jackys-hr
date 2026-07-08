"""Admin tab for feature flags."""
from __future__ import annotations

import streamlit as st


def render_feature_flags_tab() -> None:
    from core.feature_flags import delete_feature_flag, list_feature_flags, set_feature_flag
    from core.rbac import has_permission

    st.subheader("Feature Flags")
    if not has_permission("features.view"):
        st.warning("You do not have permission to view feature flags.")
        return

    can_manage = has_permission("features.manage")

    if can_manage:
        with st.expander("Create or Update Flag", expanded=False):
            key = st.text_input("Key", placeholder="example_feature", key="flag_key")
            enabled = st.toggle("Enabled", value=True, key="flag_enabled")
            description = st.text_area("Description", key="flag_description")
            if st.button("Save Flag", type="primary", key="flag_save"):
                err = set_feature_flag(key.strip(), enabled, description.strip())
                st.error(err) if err else st.rerun()

    flags = list_feature_flags()
    if not flags:
        st.info("No feature flags found.")
        return

    for flag in flags:
        key = str(flag.get("key", ""))
        with st.container(border=True):
            cols = st.columns([2, 1, 1])
            cols[0].markdown(f"**{key}**")
            cols[0].caption(flag.get("description") or "No description")
            cols[1].metric("State", "On" if flag.get("enabled") else "Off")
            if can_manage and key:
                current = bool(flag.get("enabled"))
                new_state = cols[2].toggle("Enabled", value=current, key=f"flag_toggle_{key}")
                if new_state != current:
                    err = set_feature_flag(key, new_state, flag.get("description") or "")
                    st.error(err) if err else st.rerun()
                if cols[2].button("Delete", key=f"flag_delete_{key}", use_container_width=True):
                    err = delete_feature_flag(key)
                    st.error(err) if err else st.rerun()
