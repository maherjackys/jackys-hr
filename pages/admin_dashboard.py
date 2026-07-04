"""
Admin Dashboard — MINIMAL DIAGNOSTIC VERSION
Every step uses print(flush=True) so output is guaranteed in Cloud logs.
"""
# ── Absolute first line ───────────────────────────────────────────────────────
import sys
print("ADMIN_TOP: script entered", flush=True, file=sys.stderr)
print("ADMIN_TOP: script entered", flush=True)         # stdout too

# ── Standard-library imports only ────────────────────────────────────────────
import os
print("ADMIN_STEP_1: os imported", flush=True)

import logging
print("ADMIN_STEP_2: logging imported", flush=True)

# ── Streamlit ─────────────────────────────────────────────────────────────────
print("ADMIN_STEP_3: about to import streamlit", flush=True)
import streamlit as st
print("ADMIN_STEP_4: streamlit imported OK", flush=True)

# ── Minimal page ──────────────────────────────────────────────────────────────
print("ADMIN_STEP_5: about to call set_page_config", flush=True)
st.set_page_config(page_title="Admin", page_icon="📊", layout="wide")
print("ADMIN_STEP_6: set_page_config done", flush=True)

print("ADMIN_STEP_7: about to call st.write", flush=True)
st.write("## ✅ admin page loaded")
st.write(f"Python {sys.version}")
print("ADMIN_STEP_8: st.write done", flush=True)

# ── Secret check ──────────────────────────────────────────────────────────────
print("ADMIN_STEP_9: checking secrets", flush=True)
for _k in ("ADMIN_PASSWORD", "GROQ_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"):
    try:
        _v = st.secrets.get(_k, "")
        _status = "SET" if _v else "MISSING"
    except Exception as _e:
        _status = f"ERROR({_e})"
    print(f"ADMIN_SECRET_{_k}: {_status}", flush=True)
    st.write(f"- `{_k}`: **{_status}**")

print("ADMIN_BOTTOM: script completed", flush=True, file=sys.stderr)
print("ADMIN_BOTTOM: script completed", flush=True)
