"""
HR Policy Assistant — Streamlit entry point v7.0
Multi-source | Dark/Light Mode | Language Switcher (AR/EN + RTL/LTR)
Streaming responses | Thinking animation | Source citations
"""
from __future__ import annotations

import itertools
import logging
import os

import streamlit as st
import streamlit.components.v1 as components

from config import get_groq_api_key, get_settings
from core.language import LANG_EN, detect_language, is_greeting, t
from core.rag_engine import RagEngine, format_history
from core.rate_limiter import is_rate_limited
from core.security import sanitize_input
from ui.styles import inject_css, inject_ui_controls

logging.basicConfig(level=logging.WARNING, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("hr_assistant")
logger.setLevel(logging.INFO)

settings = get_settings()

st.set_page_config(
    page_title="HR Policy Assistant | المساعد المعرفي للموارد البشرية",
    page_icon="🏛️",
    layout="centered",
    initial_sidebar_state="collapsed",
    menu_items={"About": "HR Policy Assistant — Powered by Groq + LangChain"},
)

# ── Fonts ─────────────────────────────────────────────────────────────────────
# Cairo: Arabic + Latin. Noto Sans Arabic: fallback for Arabic.
# <link> avoids render-blocking @import
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;500;600;700;800;900&family=Inter:wght@400;500;600;700&family=Noto+Sans+Arabic:wght@400;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

inject_css(settings.css_path)
inject_ui_controls()

# ── Controls bar CSS ───────────────────────────────────────────────────────────
# BUG 1 FIX:
# stHeader z-index is 999990 in Streamlit → our iframe must be higher.
# We keep stHeader visible but transparent (instead of hiding it) so
# Streamlit's own navigation still works if present.
# z-index: 9999999 > 999990 ← iframe always on top.
st.markdown("""
<style>
/* Keep stHeader in DOM but visually invisible — avoids Streamlit nav issues */
[data-testid="stHeader"] {
    background: transparent !important;
    box-shadow: none !important;
}

/* Controls iframe — pinned top-right, above stHeader (9999999 > 999990).
   Height 150px = 56px button bar + 94px dropdown space.
   The 94px below the bar has pointer-events:none inside the iframe so it
   never blocks Streamlit content (set via html/body CSS in ui/styles.py). */
iframe[title="st.iframe"] {
    position: fixed !important;
    top: 0 !important;
    right: 0 !important;
     /* Expand iframe to full viewport width so dropdowns never get clipped
         by the browser's right edge. Interactive elements inside the iframe
         keep pointer-events enabled while the rest remains transparent. */
     left: 0 !important;
     right: 0 !important;
     width: 100vw !important;
     height: 220px !important;
    z-index: 9999999 !important;
    pointer-events: auto !important;
    border: none !important;
    background: transparent !important;
    overflow: visible !important;
    clip-path: none !important;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    if st.button("🔄 Rebuild Index",
                 help="Force reload after adding new PDF files",
                 use_container_width=True):
        st.cache_resource.clear()
        st.rerun()
    st.markdown("---")
    st.markdown(
        "<small>Add PDF files to<br>"
        "<code>hr_documents/</code> or<br>"
        "<code>dubai_hr_documents/</code><br>"
        "then click Rebuild.</small>",
        unsafe_allow_html=True,
    )

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hr-header">
  <div class="hr-header-icon">🏛️</div>
  <h1 class="main-title" data-i18n="app_title">HR Policy Assistant</h1>
  <p class="sub-title" data-i18n="app_subtitle">Ask about any policy in seconds — instead of browsing for hours</p>
</div>
""", unsafe_allow_html=True)

# ── Stats bar ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hr-stats-bar">
  <div class="hr-stat-item">
    <span class="hr-stat-icon">🌐</span>
    <div class="hr-stat-text">
      <strong data-i18n="stat_ml_t">Multilingual</strong>
      <span data-i18n="stat_ml_d">Arabic &amp; English</span>
    </div>
  </div>
  <div class="hr-stat-divider"></div>
  <div class="hr-stat-item">
    <span class="hr-stat-icon">⚡</span>
    <div class="hr-stat-text">
      <strong data-i18n="stat_ins_t">Instant Answers</strong>
      <span data-i18n="stat_ins_d">Under a second</span>
    </div>
  </div>
  <div class="hr-stat-divider"></div>
  <div class="hr-stat-item">
    <span class="hr-stat-icon">🔒</span>
    <div class="hr-stat-text">
      <strong data-i18n="stat_sec_t">Private &amp; Secure</strong>
      <span data-i18n="stat_sec_d">Your data is safe</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Source selection ──────────────────────────────────────────────────────────
if "knowledge_source" not in st.session_state:
    st.session_state.knowledge_source = "company"

current_source = st.session_state.knowledge_source

st.markdown(
    '<p class="source-selector-label" data-i18n="src_label">SELECT KNOWLEDGE SOURCE</p>',
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2)

with col1:
    c_sel = "selected" if current_source == "company" else ""
    st.markdown(f"""
<div class="source-card company {c_sel}">
  <div class="source-card-header">
    <span class="source-card-icon">🏢</span>
    <div class="source-card-check">&#x2713;</div>
  </div>
  <div class="source-card-title" data-i18n="src_co_t">Company Policy</div>
  <div class="source-card-desc" data-i18n="src_co_d">Answers based on your organization's internal HR policies.</div>
</div>""", unsafe_allow_html=True)
    if st.button(
        "✓ Active" if current_source == "company" else "Select",
        key="btn_company",
        use_container_width=True,
        type="primary" if current_source == "company" else "secondary",
    ):
        if current_source != "company":
            st.session_state.knowledge_source = "company"
            st.session_state.messages = [
                {"role": "assistant", "content": t("welcome_company", LANG_EN)}
            ]
            st.rerun()

with col2:
    d_sel = "selected" if current_source == "dubai_hr" else ""
    st.markdown(f"""
<div class="source-card dubai {d_sel}">
  <div class="source-card-header">
    <span class="source-card-icon">🇦🇪</span>
    <div class="source-card-check">&#x2713;</div>
  </div>
  <div class="source-card-title" data-i18n="src_dxb_t">Dubai HR Policy</div>
  <div class="source-card-desc" data-i18n="src_dxb_d">Answers based on Dubai labor regulations and UAE HR policies.</div>
</div>""", unsafe_allow_html=True)
    if st.button(
        "✓ Active" if current_source == "dubai_hr" else "Select",
        key="btn_dubai",
        use_container_width=True,
        type="primary" if current_source == "dubai_hr" else "secondary",
    ):
        if current_source != "dubai_hr":
            st.session_state.knowledge_source = "dubai_hr"
            st.session_state.messages = [
                {"role": "assistant", "content": t("welcome_dubai", LANG_EN)}
            ]
            st.rerun()

# ── Directories ───────────────────────────────────────────────────────────────
settings.docs_dir.mkdir(parents=True, exist_ok=True)
settings.dubai_docs_dir.mkdir(parents=True, exist_ok=True)
settings.db_dir.mkdir(parents=True, exist_ok=True)
settings.dubai_db_dir.mkdir(parents=True, exist_ok=True)

# ── API key ───────────────────────────────────────────────────────────────────
api_key = get_groq_api_key()
if not api_key:
    api_key = st.text_input("Enter your Groq API Key:", type="password", placeholder="gsk_...")
    if not api_key:
        st.info("Please enter your Groq API key to continue.")
        st.stop()

# ── Engine ────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="⏳ Loading knowledge base…")
def load_engine(_api_key: str, source: str) -> RagEngine | None:
    try:
        return RagEngine(settings, _api_key, source=source)
    except Exception:
        logger.exception("Engine init failed for: %s", source)
        return None


engine = load_engine(api_key, current_source)

# ── Conversation state ────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": t("welcome_company", LANG_EN)}
    ]

# ── Active source badge ───────────────────────────────────────────────────────
source_name = t("source_dubai", LANG_EN) if current_source == "dubai_hr" else t("source_company", LANG_EN)
badge_class = "active-source-badge dubai-badge" if current_source == "dubai_hr" else "active-source-badge"
st.markdown(
    f'<div class="{badge_class}"><span data-i18n="active_pfx">Active:</span> {source_name}</div>',
    unsafe_allow_html=True,
)

# ── Chat history ──────────────────────────────────────────────────────────────
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # Show source citation if stored in the message
        if message["role"] == "assistant" and message.get("sources"):
            srcs = sorted({os.path.basename(s) for s in message["sources"] if s})
            if srcs:
                src_html = " · ".join(f"📄 {s}" for s in srcs)
                st.markdown(f'<div class="source-citation">{src_html}</div>', unsafe_allow_html=True)

# Scroll to bottom after a new response (flag set before st.rerun())
if st.session_state.pop("scroll_to_bottom", False):
    components.html("""
<script>
(function(){
  try {
    var p = window.parent;
    p.scrollTo({ top: p.document.body.scrollHeight, behavior: 'smooth' });
  } catch(e) {}
})();
</script>
""", height=0, scrolling=False)

# ── Suggested questions (empty state) ────────────────────────────────────────
_SUGGESTIONS: dict[str, list[str]] = {
    "company": [
        "What is the annual leave policy?",
        "What are the working hours?",
        "What is the expense claim process?",
    ],
    "dubai_hr": [
        "ما هي ساعات العمل في الإمارات؟",
        "What is the notice period for resignation?",
        "What are maternity leave entitlements?",
    ],
}

if len(st.session_state.messages) <= 1 and engine and engine.is_ready:
    st.markdown('<p class="suggestions-label">💡 Try asking:</p>', unsafe_allow_html=True)
    sugg_list = _SUGGESTIONS.get(current_source, [])
    s_cols = st.columns(len(sugg_list))
    for i, (sc, q) in enumerate(zip(s_cols, sugg_list)):
        with sc:
            if st.button(q, key=f"sugg_{i}", use_container_width=True):
                st.session_state.suggested_query = q
                st.rerun()

# ── Chat input ────────────────────────────────────────────────────────────────
user_query = st.chat_input("Type your question… | اكتب سؤالك هنا…", key="hr_chat_input")
if not user_query:
    user_query = st.session_state.pop("suggested_query", None)

# ── Thinking animation HTML ───────────────────────────────────────────────────
_THINKING_HTML = """
<div class="thinking-indicator" aria-label="Thinking…">
  <span class="thinking-dot"></span>
  <span class="thinking-dot"></span>
  <span class="thinking-dot"></span>
</div>"""

if user_query:
    lang        = detect_language(user_query)
    clean_query, error_key = sanitize_input(user_query, settings.max_input_chars)

    # Skip entirely on empty/whitespace-only input
    if not clean_query:
        user_query = None

if user_query and clean_query:
    history_text = format_history(st.session_state.messages, settings.history_turns_for_context)

    if error_key == "too_long":
        shortcut_response = t("input_too_long", lang)
    elif is_greeting(clean_query):
        shortcut_response = t("greeting_reply", lang)
    elif is_rate_limited(settings.max_requests_per_minute):
        shortcut_response = t("rate_limited", lang)
    else:
        shortcut_response = None

    if shortcut_response is not None:
        with st.chat_message("user"):
            st.markdown(clean_query)
        with st.chat_message("assistant"):
            st.markdown(shortcut_response)
        st.session_state.messages.append({"role": "user",      "content": clean_query})
        st.session_state.messages.append({"role": "assistant", "content": shortcut_response})

    else:
        st.session_state.messages.append({"role": "user", "content": clean_query})
        with st.chat_message("user"):
            st.markdown(clean_query)

        with st.chat_message("assistant"):
            response       = ""
            source_docs    = []

            if engine is None:
                response = t("init_error", lang)
                st.markdown(response)

            elif not engine.is_ready:
                if current_source == "dubai_hr":
                    pdf_count = len(list(settings.dubai_docs_dir.glob("*.pdf")))
                    response = (
                        f"⏳ Loading Dubai HR documents… ({pdf_count} PDF found). "
                        "Click **⚙️ Rebuild Index** in the sidebar."
                    ) if pdf_count > 0 else (
                        "⚠️ No PDF files in `dubai_hr_documents`. "
                        "Add policy files and click **Rebuild Index**."
                    )
                else:
                    response = t("no_documents", lang)
                st.markdown(response)

            else:
                try:
                    # Show thinking dots while waiting for first token
                    thinking_slot = st.empty()
                    thinking_slot.markdown(_THINKING_HTML, unsafe_allow_html=True)

                    stream_gen  = engine.answer_stream(clean_query, history_text)
                    first_chunk = next(stream_gen, None)

                    thinking_slot.empty()  # Remove dots the moment content arrives

                    if first_chunk is not None:
                        response = st.write_stream(
                            itertools.chain([first_chunk], stream_gen)
                        )
                        source_docs = engine.last_source_docs
                    else:
                        result = engine.answer(clean_query, history_text)
                        if result.status == "out_of_scope":
                            response = t("out_of_scope", lang)
                        elif result.status in ("no_answer", "error"):
                            response = t("no_answer", lang)
                        else:
                            response    = result.text
                            source_docs = result.source_docs or []
                        st.markdown(response)

                    # Show source citation badge
                    unique_sources = sorted({os.path.basename(s) for s in source_docs if s})
                    if unique_sources:
                        src_html = " · ".join(f"📄 {s}" for s in unique_sources)
                        st.markdown(f'<div class="source-citation">{src_html}</div>',
                                    unsafe_allow_html=True)

                except Exception:
                    logger.exception("Query failed: %r", clean_query)
                    response = t("system_error", lang)
                    st.markdown(response)

        st.session_state.messages.append({
            "role":    "assistant",
            "content": response,
            "sources": source_docs,
        })

    if len(st.session_state.messages) > settings.max_history_messages:
        st.session_state.messages = (
            st.session_state.messages[:1]
            + st.session_state.messages[-(settings.max_history_messages - 1):]
        )

    st.session_state.scroll_to_bottom = True
    st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hr-footer">
  <span>HR Policy Assistant</span>
  <span class="hr-footer-dot">·</span>
  <span>Powered by <strong>Groq</strong> + <strong>LangChain</strong></span>
  <span class="hr-footer-dot">·</span>
  <span>v7.0</span>
</div>
""", unsafe_allow_html=True)
