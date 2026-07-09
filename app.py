"""
HR Policy Assistant — navigation hub.

Streamlit 1.36+ runs app.py for EVERY page.  Without st.navigation() the
full main-page widget tree (chat_input, buttons, etc.) renders on the admin
page too, creating a widget-tree conflict that spins in an infinite rerun.

Fix: app.py is now a 3-line hub.  Each page gets its own clean script.
"""
from core.monitoring import init_sentry
init_sentry()

import streamlit as st

st.set_page_config(
    page_title="HR Policy Assistant | المساعد المعرفي للموارد البشرية",
    page_icon="🏢",
    layout="centered",
    initial_sidebar_state="expanded",
    menu_items={"About": "HR Policy Assistant — Powered by Groq + LangChain"},
)

pg = st.navigation(
    [
        st.Page("app_main.py",              title="HR Policy Assistant", icon="🏢", default=True),
        st.Page("pages/admin_dashboard.py", title="Admin",               icon="📊"),
    ],
    position="hidden",   # admin is URL-only, not shown in sidebar
)
pg.run()
