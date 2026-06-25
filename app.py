"""
HR Policy Assistant - Streamlit entry point v4.0
Multi-source Knowledge | Dark/Light Mode | Language Switcher (AR/EN/RTL)
"""
from __future__ import annotations
import logging
import streamlit as st
from config import get_groq_api_key, get_settings
from core.language import detect_language, is_greeting, t, LANG_AR, LANG_EN
from core.rag_engine import RagEngine, format_history
from core.rate_limiter import is_rate_limited
from core.security import sanitize_input
from ui.styles import inject_css, inject_theme_toggle, inject_language_switcher
from ui.i18n import ui, get_ui_lang, AR, EN

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("hr_assistant")
settings = get_settings()

st.set_page_config(
    page_title="HR Policy Assistant | المساعد المعرفي للموارد البشرية",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
    menu_items={"About": "HR Policy Assistant v4.0"},
)

inject_css(settings.css_path)
inject_theme_toggle()
inject_language_switcher()

# ── UI Language (from session or default EN) ──────────────────────────────────
if "ui_lang" not in st.session_state:
    st.session_state.ui_lang = EN

ul = st.session_state.ui_lang  # shorthand for current UI language

# ── Hero Stats Bar — with data-i18n for JS translation ───────────────────────
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

# ── Source selection state ────────────────────────────────────────────────────
if "knowledge_source" not in st.session_state:
    st.session_state.knowledge_source = "company"

st.markdown(_source_cards_html(st.session_state.knowledge_source), unsafe_allow_html=True)

# Source switch buttons
col1, col2 = st.columns(2)
with col1:
    if st.button(
        "Company Policy",
        key="btn_company", use_container_width=True,
        type="primary" if st.session_state.knowledge_source == "company" else "secondary",
    ):
        if st.session_state.knowledge_source != "company":
            st.session_state.knowledge_source = "company"
            st.session_state.messages = [{"role": "assistant", "content":
                "Welcome! Place your HR policy PDFs in the hr_documents folder, then ask me anything."}]
            st.rerun()
with col2:
    if st.button(
        "Dubai HR Policy",
        key="btn_dubai", use_container_width=True,
        type="primary" if st.session_state.knowledge_source == "dubai_hr" else "secondary",
    ):
        if st.session_state.knowledge_source != "dubai_hr":
            st.session_state.knowledge_source = "dubai_hr"
            st.session_state.messages = [{"role": "assistant", "content":
                "Welcome to the Dubai HR Policy Assistant! Place your PDFs in dubai_hr_documents folder."}]
            st.rerun()

# ── Directories ───────────────────────────────────────────────────────────────
settings.docs_dir.mkdir(parents=True, exist_ok=True)
settings.dubai_docs_dir.mkdir(parents=True, exist_ok=True)
settings.db_dir.mkdir(parents=True, exist_ok=True)
settings.dubai_db_dir.mkdir(parents=True, exist_ok=True)

# ── API key ───────────────────────────────────────────────────────────────────
api_key = get_groq_api_key()
if not api_key:
    api_key = st.text_input(
        "Enter your Groq API Key (from console.groq.com):",
        type="password", placeholder="gsk_...",
    )
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
        {"role": "assistant", "content":
         "Welcome! Place your HR policy PDFs in the hr_documents folder, then ask me anything."}
    ]

# Active source badge
source_name = "Dubai HR Policy" if current_source == "dubai_hr" else "Company Policy"
badge_class = "active-source-badge dubai-badge" if current_source == "dubai_hr" else "active-source-badge"
st.markdown(
    f'<div class="{badge_class}"><span data-i18n="active_pfx">Active:</span> {source_name}</div>',
    unsafe_allow_html=True,
)

# Chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# ── Chat input ────────────────────────────────────────────────────────────────
user_query = st.chat_input("Type your question... | اكتب سؤالك هنا...", key="hr_chat_input")

if user_query:
    lang = detect_language(user_query)
    clean_query, error_key = sanitize_input(user_query, settings.max_input_chars)
    history_text = format_history(st.session_state.messages, settings.history_turns_for_context)

    if error_key:
        response = t(error_key, lang)

    elif is_rate_limited(settings.max_requests_per_minute):
        response = t("rate_limited", lang)

    elif is_greeting(clean_query):
        response = t("greeting_reply", lang)

    else:
        st.session_state.messages.append({"role": "user", "content": clean_query})
        with st.chat_message("user"):
            st.write(clean_query)

        with st.chat_message("assistant"):
            if engine is None:
                response = t("init_error", lang)
            elif not engine.is_ready:
                if current_source == "dubai_hr":
                    response = ("⚠️ لم أجد ملفات في مجلد dubai_hr_documents. أضفها أولاً."
                                if lang == LANG_AR else
                                "⚠️ No PDF files found in dubai_hr_documents. Please add your Dubai HR policy files first.")
                else:
                    response = t("no_documents", lang)
            else:
                try:
                    spin = "جاري البحث..." if lang == LANG_AR else "Searching..."
                    with st.spinner(spin):
                        result = engine.answer(clean_query, history_text)
                    if result.status == "out_of_scope":
                        response = t("out_of_scope", lang)
                    elif result.status in ("no_answer", "error"):
                        response = t("no_answer", lang)
                    else:
                        response = result.text
                except Exception:
                    logger.exception("Query failed: %r", clean_query)
                    response = t("system_error", lang)

            st.write(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
        if len(st.session_state.messages) > settings.max_history_messages:
            st.session_state.messages = (
                st.session_state.messages[:1]
                + st.session_state.messages[-(settings.max_history_messages - 1):]
            )
        st.rerun()

    # Short-circuit
    if error_key or is_rate_limited(settings.max_requests_per_minute) or is_greeting(clean_query):
        st.session_state.messages.append({"role": "user",      "content": user_query})
        st.session_state.messages.append({"role": "assistant", "content": response})
        if len(st.session_state.messages) > settings.max_history_messages:
            st.session_state.messages = (
                st.session_state.messages[:1]
                + st.session_state.messages[-(settings.max_history_messages - 1):]
            )
        st.rerun()
