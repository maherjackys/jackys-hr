"""Admin tab for API key management."""
from __future__ import annotations

import streamlit as st


def render_api_keys_tab() -> None:
    from core.api_keys import generate_api_key, list_api_keys, revoke_api_key, set_key_status
    from core.rbac import has_permission

    st.subheader("API Keys")
    if not has_permission("api_keys.view"):
        st.warning("You do not have permission to view API keys.")
        return

    can_manage = has_permission("api_keys.manage")

    if can_manage:
        with st.expander("Create API Key", expanded=False):
            name = st.text_input("Name", key="api_key_name")
            created_by = st.text_input("Created by", key="api_key_created_by")
            submitted = st.button("Create Key", type="primary", key="api_key_create")
            if submitted:
                raw_key, err = generate_api_key(name=name.strip(), created_by=created_by.strip())
                if err:
                    st.error(err)
                else:
                    st.success("API key created. Copy it now; it will not be shown again.")
                    st.code(raw_key, language="text")

    keys, err = list_api_keys(include_revoked=True)
    if err:
        st.error(err)
        return
    if not keys:
        st.info("No API keys found.")
        return

    for item in keys:
        key_id = str(item.get("id", ""))
        status = item.get("status", "active")
        with st.container(border=True):
            cols = st.columns([2, 1, 1, 1])
            cols[0].markdown(f"**{item.get('name') or 'Unnamed key'}**")
            cols[0].caption(f"Created by: {item.get('created_by') or '-'}")
            cols[1].metric("Status", status)
            cols[2].caption(f"Created: {item.get('created_at') or '-'}")
            cols[2].caption(f"Last used: {item.get('last_used_at') or 'Never'}")
            if can_manage and key_id:
                if status == "active":
                    if cols[3].button("Disable", key=f"api_key_disable_{key_id}", use_container_width=True):
                        err = set_key_status(key_id, "disabled")
                        st.error(err) if err else st.rerun()
                elif status == "disabled":
                    if cols[3].button("Enable", key=f"api_key_enable_{key_id}", use_container_width=True):
                        err = set_key_status(key_id, "active")
                        st.error(err) if err else st.rerun()
                if status != "revoked" and cols[3].button("Revoke", key=f"api_key_revoke_{key_id}", use_container_width=True):
                    err = revoke_api_key(key_id)
                    st.error(err) if err else st.rerun()
