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

# ─── Page setup ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="HR Policy Assistant", page_icon="🤖", layout="centered")
inject_css(settings.css_path)

# لو عندك لوغو، فعّل السطر التالي وضع الصورة بنفس مجلد app.py:
# st.image("logo.png", width=180)

st.markdown('<h1 class="main-title">HR Policy Assistant</h1>', unsafe_allow_html=True)
st.markdown(
    '<h3 class="sub-title">المساعد المعرفي لسياسات الموارد البشرية</h3>',
    unsafe_allow_html=True,
)

settings.docs_dir.mkdir(parents=True, exist_ok=True)
settings.db_dir.mkdir(parents=True, exist_ok=True)

# ─── API key resolution ───────────────────────────────────────────────────
api_key = get_groq_api_key()
if not api_key:
    api_key = st.text_input(
        "🔑 أدخل Groq API Key (من console.groq.com):",
        type="password",
        placeholder="gsk_...",
    )
    if not api_key:
        st.info(
            "احصل على API key مجاني من [console.groq.com](https://console.groq.com) "
            "ثم أدخله أعلاه."
        )
        st.stop()


@st.cache_resource(show_spinner="جاري تحميل قاعدة المعرفة...")
def load_engine(_api_key: str) -> RagEngine | None:
    try:
        return RagEngine(settings, _api_key)
    except Exception:
        logger.exception("RAG engine initialization failed")
        return None


engine = load_engine(api_key)

# ─── Conversation state ─────────────────────────────────────────────────────
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

    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.write(user_query)

    with st.chat_message("assistant"):
        if error_key == "too_long":
            response = t("input_too_long", lang)

        elif is_rate_limited(settings.max_requests_per_minute):
            response = t("rate_limited", lang)

        elif is_greeting(clean_query):
            response = t("greeting_reply", lang)

        elif engine is None:
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
