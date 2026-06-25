"""
HR Policy Assistant — Streamlit entry point v3.0
Multi-source Knowledge | Dark/Light Mode | Card Source Selector
Production-ready UI/UX
"""
from __future__ import annotations

import logging

import streamlit as st
import streamlit.components.v1 as components

from config import get_groq_api_key, get_settings
from core.language import detect_language, is_greeting, t, LANG_AR, LANG_EN
from core.rag_engine import RagEngine, format_history
from core.rate_limiter import is_rate_limited
from core.security import sanitize_input
from ui.styles import inject_css, inject_theme_toggle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("hr_assistant")

settings = get_settings()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HR Policy Assistant | المساعد المعرفي للموارد البشرية",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
    menu_items={
        "About": "HR Policy Assistant v3.0 — مساعد ذكي لسياسات الموارد البشرية",
    },
)

inject_css(settings.css_path)
inject_theme_toggle()

# ── Hero HTML ─────────────────────────────────────────────────────────────────
HERO_STATS_HTML = """
<div class="hr-stats-bar">
  <div class="hr-stat-item">
    <span class="hr-stat-icon">📄</span>
    <div class="hr-stat-text">
      <strong>متعدد اللغات</strong>
      <span>عربي وإنجليزي</span>
    </div>
  </div>
  <div class="hr-stat-divider"></div>
  <div class="hr-stat-item">
    <span class="hr-stat-icon">⚡</span>
    <div class="hr-stat-text">
      <strong>إجابات فورية</strong>
      <span>بأقل من ثانية</span>
    </div>
  </div>
  <div class="hr-stat-divider"></div>
  <div class="hr-stat-item">
    <span class="hr-stat-icon">🔒</span>
    <div class="hr-stat-text">
      <strong>آمن وخاص</strong>
      <span>بياناتك محمية</span>
    </div>
  </div>
</div>
"""

# Source selector cards HTML (JS handles selection state)
SOURCE_SELECTOR_HTML = """
<div class="source-selector-wrap">
  <span class="source-selector-label">اختر مصدر المعرفة / Select Knowledge Source</span>
  <div class="source-cards-grid">

    <button
      class="source-card company selected"
      id="src-company"
      onclick="selectSource('company')"
      aria-pressed="true"
    >
      <div class="source-card-header">
        <span class="source-card-icon">🏢</span>
        <div class="source-card-check">✓</div>
      </div>
      <div class="source-card-title">Company Policy</div>
      <div class="source-card-desc">Answers based on your organization's internal HR policies and documents.</div>
    </button>

    <button
      class="source-card dubai"
      id="src-dubai"
      onclick="selectSource('dubai_hr')"
      aria-pressed="false"
    >
      <div class="source-card-header">
        <span class="source-card-icon">🇦🇪</span>
        <div class="source-card-check">✓</div>
      </div>
      <div class="source-card-title">Dubai HR Policy</div>
      <div class="source-card-desc">Answers based on Dubai labor regulations and UAE HR policies.</div>
    </button>

  </div>
</div>

<script>
(function() {
  var STORAGE_KEY = "hr_source_selection";

  function selectSource(src) {
    // Update visual state
    var company = document.getElementById("src-company");
    var dubai   = document.getElementById("src-dubai");
    if (!company || !dubai) return;

    if (src === "company") {
      company.classList.add("selected");    company.setAttribute("aria-pressed","true");
      dubai.classList.remove("selected");   dubai.setAttribute("aria-pressed","false");
    } else {
      dubai.classList.add("selected");     dubai.setAttribute("aria-pressed","true");
      company.classList.remove("selected"); company.setAttribute("aria-pressed","false");
    }

    // Persist & notify Streamlit
    localStorage.setItem(STORAGE_KEY, src);
    window.parent.postMessage({type:"streamlit:sourceChange", source: src}, "*");
  }

  // Restore saved selection
  var saved = localStorage.getItem(STORAGE_KEY) || "company";
  selectSource(saved);

  // Expose globally so onclick can reach it
  window.selectSource = selectSource;
})();
</script>
"""


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown('<h1 class="main-title">🤖 HR Policy Assistant</h1>', unsafe_allow_html=True)
st.markdown(
    '<h3 class="sub-title">اسأل عن أي سياسة في ثوانٍ — بدلاً من التصفح لساعات</h3>',
    unsafe_allow_html=True,
)
st.markdown(HERO_STATS_HTML, unsafe_allow_html=True)

# ── Source selector ───────────────────────────────────────────────────────────
st.markdown(SOURCE_SELECTOR_HTML, unsafe_allow_html=True)

# Source state — stored in session_state, changed via radio (hidden via CSS)
if "knowledge_source" not in st.session_state:
    st.session_state.knowledge_source = "company"

# Streamlit radio (hidden via CSS — cards are the visible UI)
# We use a radio so Streamlit properly reruns when source changes
col1, col2 = st.columns(2)
with col1:
    if st.button("🏢 Company Policy", key="btn_company",
                 type="primary" if st.session_state.knowledge_source == "company" else "secondary",
                 use_container_width=True):
        if st.session_state.knowledge_source != "company":
            st.session_state.knowledge_source = "company"
            # Reset conversation on source change
            st.session_state.messages = [
                {"role": "assistant", "content": _welcome_msg("company")}
            ]
            st.rerun()
with col2:
    if st.button("🇦🇪 Dubai HR Policy", key="btn_dubai",
                 type="primary" if st.session_state.knowledge_source == "dubai_hr" else "secondary",
                 use_container_width=True):
        if st.session_state.knowledge_source != "dubai_hr":
            st.session_state.knowledge_source = "dubai_hr"
            st.session_state.messages = [
                {"role": "assistant", "content": _welcome_msg("dubai_hr")}
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
    api_key = st.text_input(
        "🔑 أدخل Groq API Key (من console.groq.com):",
        type="password",
        placeholder="gsk_...",
    )
    if not api_key:
        st.info("يرجى إدخال مفتاح API للمتابعة. | Please enter your API key to continue.")
        st.stop()


# ── Welcome messages per source ───────────────────────────────────────────────
def _welcome_msg(source: str) -> str:
    if source == "dubai_hr":
        return (
            "مرحباً بك في مساعد سياسات دبي للموارد البشرية 🇦🇪\n"
            "ضع ملفات PDF لسياسات دبي في مجلد dubai_hr_documents ثم اسألني!\n\n"
            "Welcome to the Dubai HR Policy Assistant 🇦🇪\n"
            "Place your Dubai HR policy PDFs in the dubai_hr_documents folder, then ask me anything."
        )
    return (
        f"{t('welcome_ar', LANG_AR)} 👋\n\n{t('welcome_en', LANG_EN)}"
    )


# ── Engine loader (cached per api_key + source) ───────────────────────────────
@st.cache_resource(show_spinner="⏳ جاري تحميل قاعدة المعرفة...")
def load_engine(_api_key: str, source: str) -> RagEngine | None:
    try:
        return RagEngine(settings, _api_key, source=source)
    except Exception:
        logger.exception("RAG engine init failed for source: %s", source)
        return None


current_source = st.session_state.knowledge_source
engine = load_engine(api_key, current_source)

# ── Conversation state ────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": _welcome_msg(current_source)}
    ]

# Show active source badge
source_name = "Dubai HR Policy 🇦🇪" if current_source == "dubai_hr" else "Company Policy 🏢"
badge_class  = "active-source-badge dubai-badge" if current_source == "dubai_hr" else "active-source-badge"
st.markdown(
    f'<div class="{badge_class}">📌 Active source: {source_name}</div>',
    unsafe_allow_html=True,
)

# Render conversation history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# ── Chat input ────────────────────────────────────────────────────────────────
user_query = st.chat_input("Type your question... | اكتب سؤالك هنا...", key="hr_chat_input")

if user_query:
    lang        = detect_language(user_query)
    clean_query, error_key = sanitize_input(user_query, settings.max_input_chars)
    history_text = format_history(st.session_state.messages, settings.history_turns_for_context)

    if error_key:
        response = t(error_key, lang)

    elif is_rate_limited(settings.max_requests_per_minute):
        response = t("rate_limited", lang)

    elif is_greeting(clean_query):
        response = t("greeting_reply", lang)

    else:
        # ── Normal RAG flow ───────────────────────────────────────────────
        st.session_state.messages.append({"role": "user", "content": clean_query})
        with st.chat_message("user"):
            st.write(clean_query)

        with st.chat_message("assistant"):
            if engine is None:
                response = t("init_error", lang)
            elif not engine.is_ready:
                if current_source == "dubai_hr":
                    response = (
                        "⚠️ لم أجد ملفات PDF في مجلد dubai_hr_documents. أضفها أولاً."
                        if lang == LANG_AR else
                        "⚠️ No PDF files found in dubai_hr_documents. Please add your Dubai HR policy files first."
                    )
                else:
                    response = t("no_documents", lang)
            else:
                try:
                    spinner_msg = "جاري البحث في " + ("سياسات دبي..." if current_source == "dubai_hr" else "سياسات الشركة...")
                    if lang != LANG_AR:
                        spinner_msg = "Searching " + ("Dubai HR policies..." if current_source == "dubai_hr" else "company policies...")
                    with st.spinner(spinner_msg):
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

    # ── Short-circuit responses (error / rate_limit / greeting) ──────────
    if error_key or is_rate_limited(settings.max_requests_per_minute) or is_greeting(clean_query):
        st.session_state.messages.append({"role": "user",      "content": user_query})
        st.session_state.messages.append({"role": "assistant", "content": response})
        if len(st.session_state.messages) > settings.max_history_messages:
            st.session_state.messages = (
                st.session_state.messages[:1]
                + st.session_state.messages[-(settings.max_history_messages - 1):]
            )
        st.rerun()
