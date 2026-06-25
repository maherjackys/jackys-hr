"""
HR Policy Assistant — Streamlit entry point.

This file owns UI orchestration only. All business logic (RAG, language,
security, rate limiting) lives in the core/ package so it can be tested
and modified independently of the UI.
"""
from __future__ import annotations

import logging

import streamlit as st

from config import get_groq_api_key, get_settings
from core.language import detect_language, is_greeting, t, LANG_AR, LANG_EN
from core.rag_engine import RagEngine, format_history
from core.rate_limiter import is_rate_limited
from core.security import sanitize_input
from ui.styles import inject_css

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("hr_assistant")

settings = get_settings()

# ── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HR Policy Assistant | المساعد المعرفي للموارد البشرية",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
    menu_items={
        "About": "HR Policy Assistant v2.0 — مساعد ذكي لسياسات الموارد البشرية",
    },
)
inject_css(settings.css_path)

# ── Hero Section HTML ─────────────────────────────────────────────────────────
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

HOW_IT_WORKS_HTML = """
<div class="hr-how-it-works">
  <div class="hr-how-header">
    <div class="hr-how-badge">كيف يعمل</div>
    <h4 class="hr-how-title">ابدأ في 3 خطوات بسيطة</h4>
  </div>
  <div class="hr-steps-grid">
    <div class="hr-step-card">
      <div class="hr-step-num">01</div>
      <div class="hr-step-icon">📁</div>
      <h5>ارفع ملفاتك</h5>
      <p>ضع ملفات PDF لسياسات الموارد البشرية في مجلد hr_documents</p>
    </div>
    <div class="hr-step-card accent">
      <div class="hr-step-num">02</div>
      <div class="hr-step-icon">💬</div>
      <h5>اطرح سؤالك</h5>
      <p>اكتب سؤالك بالعربية أو الإنجليزية وانتظر الإجابة الفورية</p>
    </div>
    <div class="hr-step-card">
      <div class="hr-step-num">03</div>
      <div class="hr-step-icon">✅</div>
      <h5>احصل على إجابة دقيقة</h5>
      <p>يقتبس المساعد مباشرة من وثائقك مع الإشارة للمصدر</p>
    </div>
  </div>
</div>
"""

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown('<h1 class="main-title">🤖 HR Policy Assistant</h1>', unsafe_allow_html=True)
st.markdown(
    '<h3 class="sub-title">اسأل عن أي سياسة في ثوانٍ — بدلاً من التصفح لساعات</h3>',
    unsafe_allow_html=True,
)
st.markdown(HERO_STATS_HTML, unsafe_allow_html=True)

settings.docs_dir.mkdir(parents=True, exist_ok=True)
settings.db_dir.mkdir(parents=True, exist_ok=True)

# ── API key resolution ─────────────────────────────────────────────────────────
api_key = get_groq_api_key()
if not api_key:
    api_key = st.text_input(
        " 🔑 أدخل Groq API Key (من console.groq.com):",
        type="password",
        placeholder="gsk_...",
    )
    if not api_key:
        st.info("يرجى إدخال مفتاح API للمتابعة. | Please enter your API key to continue.")
        st.stop()

@st.cache_resource(show_spinner="⏳ جاري تحميل قاعدة المعرفة...")
def load_engine(_api_key: str) -> RagEngine | None:
    try:
        return RagEngine(settings, _api_key)
    except Exception:
        logger.exception("RAG engine initialization failed")
        return None


engine = load_engine(api_key)

# ── Conversation state ──────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": f"{t('welcome_ar', LANG_AR)} 👋\n\n{t('welcome_en', LANG_EN)}"}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

user_query = st.chat_input("Type your question... | اكتب سؤالك هنا...", key="hr_chat_input")

if user_query:
    lang = detect_language(user_query)
    clean_query, error_key = sanitize_input(user_query, settings.max_input_chars)

    # History is captured BEFORE appending the current turn, so the model
    # sees only prior context, not the question it is about to answer.
    history_text = format_history(st.session_state.messages, settings.history_turns_for_context)

    if error_key:
        response = t(error_key, lang)
    elif is_rate_limited(settings.max_requests_per_minute):
        response = t("rate_limit", lang)
    elif is_greeting(clean_query, lang):
        response = t("greeting_response", lang)
    else:
        st.session_state.messages.append({"role": "user", "content": clean_query})
        with st.chat_message("user"):
            st.write(clean_query)

        with st.chat_message("assistant"):
            if engine is None:
                response = t("init_error", lang)
            elif not engine.is_ready:
                response = t("no_documents", lang)
            else:
                try:
                    spinner_msg = "جاري البحث..." if lang == "ar" else "Searching documents..."
                    with st.spinner(spinner_msg):
                        result = engine.answer(clean_query, history_text)

                    if result.status == "out_of_scope":
                        response = t("out_of_scope", lang)
                    elif result.status == "no_answer":
                        response = t("no_answer", lang)
                    else:
                        response = result.text

                except Exception:
                    # Internal details are logged, never shown to the user.
                    logger.exception("Query failed for input: %r", clean_query)
                    response = t("system_error", lang)

            st.write(response)

        st.session_state.messages.append({"role": "assistant", "content": response})

    if len(st.session_state.messages) > settings.max_history_messages:
        st.session_state.messages = (
            st.session_state.messages[:1]
            + st.session_state.messages[-(settings.max_history_messages - 1):]
        )

# ── How It Works (shown only at start) ────────────────────────────────────────
if len(st.session_state.messages) <= 1:
    st.markdown(HOW_IT_WORKS_HTML, unsafe_allow_html=True)
