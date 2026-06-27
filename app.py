"""
HR Policy Assistant — Streamlit entry point v5.0
Multi-source | Dark/Light Mode | Language Switcher (AR/EN + RTL/LTR)
i18n runs client-side via JS (data-i18n attributes) — no page reload needed.
"""
from __future__ import annotations

import itertools
import logging

import streamlit as st

from config import get_groq_api_key, get_settings
from core.language import LANG_EN, detect_language, is_greeting, t
from core.rag_engine import RagEngine, format_history
from core.rate_limiter import is_rate_limited
from core.security import sanitize_input
from ui.styles import inject_css, inject_ui_controls

# Root logger at WARNING so LangChain/HuggingFace noise is suppressed;
# the app-specific logger stays at INFO.
logging.basicConfig(level=logging.WARNING, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("hr_assistant")
logger.setLevel(logging.INFO)

settings = get_settings()

st.set_page_config(
    page_title="HR Policy Assistant | المساعد المعرفي للموارد البشرية",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
    menu_items={"About": "HR Policy Assistant v5.0"},
)

# Google Fonts — <link> preload avoids the render-blocking @import in CSS
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;500;600;700;800;900&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

inject_css(settings.css_path)
inject_ui_controls()

# Position both st.components iframes as a single fixed overlay at top-right
st.markdown("""
<style>
iframe[title="st.iframe"] {
    position: fixed !important;
    top: 0 !important;
    right: 0 !important;
    width: 260px !important;
    height: 56px !important;
    z-index: 99998 !important;
    pointer-events: auto !important;
    border: none !important;
    background: transparent !important;
    overflow: visible !important;
}
</style>
""", unsafe_allow_html=True)

# ── Hero Stats Bar ────────────────────────────────────────────────────────────
HERO_STATS_HTML = """
<div class="hr-stats-bar">
  <div class="hr-stat-item">
    <span class="hr-stat-icon">📄</span>
    <div class="hr-stat-text">
      <strong data-i18n="stat_ml_t">Multilingual</strong>
      <span data-i18n="stat_ml_d">Arabic &amp; English</span>
    </div>
  </div>
  <div class="hr-stat-divider"></div>
  <div class="hr-stat-item">
    <span class="hr-stat-icon">&#x26A1;</span>
    <div class="hr-stat-text">
      <strong data-i18n="stat_ins_t">Instant Answers</strong>
      <span data-i18n="stat_ins_d">Under a second</span>
    </div>
  </div>
  <div class="hr-stat-divider"></div>
  <div class="hr-stat-item">
    <span class="hr-stat-icon">&#x1F512;</span>
    <div class="hr-stat-text">
      <strong data-i18n="stat_sec_t">Private &amp; Secure</strong>
      <span data-i18n="stat_sec_d">Your data is safe</span>
    </div>
  </div>
</div>
"""


def _source_cards_html(active: str) -> str:
    c_sel = "selected" if active == "company"  else ""
    d_sel = "selected" if active == "dubai_hr" else ""
    return f"""
<div class="source-selector-wrap">
  <span class="source-selector-label" data-i18n="src_label">SELECT KNOWLEDGE SOURCE</span>
  <div class="source-cards-grid">
    <div class="source-card company {c_sel}">
      <div class="source-card-header">
        <span class="source-card-icon">&#x1F3E2;</span>
        <div class="source-card-check">&#x2713;</div>
      </div>
      <div class="source-card-title" data-i18n="src_co_t">Company Policy</div>
      <div class="source-card-desc"  data-i18n="src_co_d">Answers based on your organization's internal HR policies.</div>
    </div>
    <div class="source-card dubai {d_sel}">
      <div class="source-card-header">
        <span class="source-card-icon">&#x1F1E6;&#x1F1EA;</span>
        <div class="source-card-check">&#x2713;</div>
      </div>
      <div class="source-card-title" data-i18n="src_dxb_t">Dubai HR Policy</div>
      <div class="source-card-desc"  data-i18n="src_dxb_d">Answers based on Dubai labor regulations and UAE HR policies.</div>
    </div>
  </div>
</div>
"""


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(
    '<h1 class="main-title" data-i18n="app_title">HR Policy Assistant</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<h3 class="sub-title" data-i18n="app_subtitle">Ask about any policy in seconds &mdash; instead of browsing for hours</h3>',
    unsafe_allow_html=True,
)
st.markdown(HERO_STATS_HTML, unsafe_allow_html=True)

# ── Sidebar — admin controls ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    if st.button("🔄 Rebuild Index", help="Force reload of the knowledge base after adding new PDF files"):
        st.cache_resource.clear()
        st.rerun()

# ── Source selection ──────────────────────────────────────────────────────────
if "knowledge_source" not in st.session_state:
    st.session_state.knowledge_source = "company"

st.markdown(_source_cards_html(st.session_state.knowledge_source), unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    if st.button(
        t("source_company", LANG_EN),
        key="btn_company",
        use_container_width=True,
        type="primary" if st.session_state.knowledge_source == "company" else "secondary",
    ):
        if st.session_state.knowledge_source != "company":
            st.session_state.knowledge_source = "company"
            st.session_state.messages = [
                {"role": "assistant", "content": t("welcome_company", LANG_EN)}
            ]
            st.rerun()
with col2:
    if st.button(
        t("source_dubai", LANG_EN),
        key="btn_dubai",
        use_container_width=True,
        type="primary" if st.session_state.knowledge_source == "dubai_hr" else "secondary",
    ):
        if st.session_state.knowledge_source != "dubai_hr":
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
        st.info("Please enter your API key to continue.")
        st.stop()

# ── Engine loader ─────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading knowledge base...")
def load_engine(_api_key: str, source: str) -> RagEngine | None:
    try:
        return RagEngine(settings, _api_key, source=source)
    except Exception:
        logger.exception("Engine init failed for: %s", source)
        return None


current_source = st.session_state.knowledge_source
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

# ── Chat input ────────────────────────────────────────────────────────────────
user_query = st.chat_input("Type your question... | اكتب سؤالك هنا...", key="hr_chat_input")

if user_query:
    lang        = detect_language(user_query)
    clean_query, error_key = sanitize_input(user_query, settings.max_input_chars)
    history_text = format_history(st.session_state.messages, settings.history_turns_for_context)

    # Determine shortcut response — greeting checked BEFORE rate limit
    # so saying "hello" never consumes a rate-limit slot.
    if error_key:
        shortcut_response = t(error_key, lang)
    elif is_greeting(clean_query):
        shortcut_response = t("greeting_reply", lang)
    elif is_rate_limited(settings.max_requests_per_minute):
        shortcut_response = t("rate_limited", lang)
    else:
        shortcut_response = None

    if shortcut_response is not None:
        # Show user message + canned response immediately (no rerun delay)
        with st.chat_message("user"):
            st.markdown(clean_query)
        with st.chat_message("assistant"):
            st.markdown(shortcut_response)
        st.session_state.messages.append({"role": "user",      "content": clean_query})
        st.session_state.messages.append({"role": "assistant", "content": shortcut_response})

    else:
        # Real RAG query
        st.session_state.messages.append({"role": "user", "content": clean_query})
        with st.chat_message("user"):
            st.markdown(clean_query)

        with st.chat_message("assistant"):
            if engine is None:
                response = t("init_error", lang)
                st.markdown(response)

            elif not engine.is_ready:
                if current_source == "dubai_hr":
                    pdf_count = len(list(settings.dubai_docs_dir.glob("*.pdf")))
                    response = (
                        f"⏳ Loading Dubai HR documents… ({pdf_count} PDF files found). "
                        "Use ⚙️ **Rebuild Index** in the sidebar."
                    ) if pdf_count > 0 else (
                        "⚠️ No PDF files found in `dubai_hr_documents`. Please add your files first."
                    )
                else:
                    response = t("no_documents", lang)
                st.markdown(response)

            else:
                try:
                    stream_gen  = engine.answer_stream(clean_query, history_text)
                    first_chunk = next(stream_gen, None)

                    if first_chunk is not None:
                        # Stream: prepend the already-retrieved first chunk
                        response = st.write_stream(
                            itertools.chain([first_chunk], stream_gen)
                        )
                    else:
                        # Empty stream means no relevant context — use blocking
                        # answer() which returns a proper status code.
                        result = engine.answer(clean_query, history_text)
                        if result.status == "out_of_scope":
                            response = t("out_of_scope", lang)
                        elif result.status in ("no_answer", "error"):
                            response = t("no_answer", lang)
                        else:
                            response = result.text
                        st.markdown(response)

                except Exception:
                    logger.exception("Query failed: %r", clean_query)
                    response = t("system_error", lang)
                    st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})

    # Trim history — keep welcome message + last N messages
    if len(st.session_state.messages) > settings.max_history_messages:
        st.session_state.messages = (
            st.session_state.messages[:1]
            + st.session_state.messages[-(settings.max_history_messages - 1):]
        )
    st.rerun()
