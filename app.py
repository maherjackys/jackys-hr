"""
HR Policy Assistant — Streamlit entry point v7.0
Multi-source | Dark/Light Mode | Language Switcher (AR/EN + RTL/LTR)
Streaming responses | Thinking animation | Source citations
"""
from __future__ import annotations

import logging
import os

import streamlit as st
import streamlit.components.v1 as components

from config import get_groq_api_key, get_settings
from core.language import LANG_AR, LANG_EN, detect_language, detect_language_confidence, is_greeting, t
from core.rag_engine import RagEngine, format_history
from core.rate_limiter import is_rate_limited
from core.security import sanitize_input
from ui.styles import inject_css, inject_ui_controls

logging.basicConfig(level=logging.WARNING, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("hr_assistant")
logger.setLevel(logging.INFO)

# ── Social media links ────────────────────────────────────────────────────────
# Fill in your organization's profile URLs. Leave empty ("") to hide that icon.
_SOCIAL: dict[str, str] = {
    "linkedin":  "",   # https://linkedin.com/company/your-company
    "twitter":   "",   # https://x.com/yourhandle
    "instagram": "",   # https://instagram.com/yourhandle
    "facebook":  "",   # https://facebook.com/yourpage
    "youtube":   "",   # https://youtube.com/@yourchannel
    "whatsapp":  "",   # https://wa.me/971501234567
}

def _safe_url(url: str) -> str:
    """Only allow http/https social links — prevents javascript: injection."""
    url = url.strip()
    return url if url.startswith(("https://", "http://")) else ""



_SOCIAL_META: dict[str, dict] = {
    "linkedin":  {"label": "LinkedIn",    "hover": "#0A66C2",
                  "svg": '<path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>'},
    "twitter":   {"label": "X (Twitter)", "hover": "#000000",
                  "svg": '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.713 5.865zM17.083 20.75h1.833L7.084 4.126H5.117z"/>'},
    "instagram": {"label": "Instagram",   "hover": "#E1306C",
                  "svg": '<path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/>'},
    "facebook":  {"label": "Facebook",    "hover": "#1877F2",
                  "svg": '<path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>'},
    "youtube":   {"label": "YouTube",     "hover": "#FF0000",
                  "svg": '<path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>'},
    "whatsapp":  {"label": "WhatsApp",    "hover": "#25D366",
                  "svg": '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>'},
}

def _welcome(key: str) -> str:
    """Bilingual welcome message — CSS switches AR/EN via [dir] attribute."""
    en = t(key, LANG_EN).replace("\n", "<br>")
    ar = t(key, LANG_AR).replace("🇦🇪", "").replace("\n", "<br>").strip()
    return f'<span class="msg-en">{en}</span><span class="msg-ar">{ar}</span>'


settings = get_settings()

st.set_page_config(
    page_title="HR Policy Assistant | المساعد المعرفي للموارد البشرية",
    page_icon="🏢",
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

st.markdown("""
<style>
iframe[title="st.iframe"] {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100vw !important;
    height: 70px !important;
    z-index: 9999999 !important;
    pointer-events: none !important;
    border: none !important;
    background: transparent !important;
    overflow: visible !important;
    clip-path: none !important;
}
</style>
""", unsafe_allow_html=True)

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hr-header">
  <div class="hr-header-icon">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="52" height="52" fill="none">
      <circle cx="32" cy="18" r="8" fill="#C0392B"/>
      <path d="M18 46c0-7.732 6.268-14 14-14s14 6.268 14 14"
            stroke="#C0392B" stroke-width="4" stroke-linecap="round" fill="none"/>
      <circle cx="14" cy="22" r="6" fill="#E74C3C" opacity="0.7"/>
      <path d="M4 46c0-5.523 4.477-10 10-10s10 4.477 10 10"
            stroke="#E74C3C" stroke-width="3.5" stroke-linecap="round" fill="none" opacity="0.7"/>
      <circle cx="50" cy="22" r="6" fill="#E74C3C" opacity="0.7"/>
      <path d="M40 46c0-5.523 4.477-10 10-10s10 4.477 10 10"
            stroke="#E74C3C" stroke-width="3.5" stroke-linecap="round" fill="none" opacity="0.7"/>
    </svg>
  </div>
  <div class="hr-brand-pill">HR Policy Assistant</div>
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
<div class="source-card company {c_sel}" role="button" tabindex="0" data-cr="1"
     aria-label="Company Policy">
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
                {"role": "assistant", "content": _welcome("welcome_company"), "is_welcome": True}
            ]
            st.rerun()

with col2:
    d_sel = "selected" if current_source == "dubai_hr" else ""
    st.markdown(f"""
<div class="source-card dubai {d_sel}" role="button" tabindex="0" data-cr="1"
     aria-label="Dubai HR Policy">
  <div class="source-card-header">
    <span class="source-card-icon"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="20" viewBox="0 0 6 4" style="border-radius:2px;display:block"><rect width="2" height="4" fill="#CE1126"/><rect x="2" width="4" height="1.33" fill="#00732F"/><rect x="2" y="1.33" width="4" height="1.34" fill="#fff"/><rect x="2" y="2.67" width="4" height="1.33" fill="#000"/></svg></span>
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
                {"role": "assistant", "content": _welcome("welcome_dubai"), "is_welcome": True}
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
        {"role": "assistant", "content": _welcome("welcome_company"), "is_welcome": True}
    ]

# ── Active source badge ───────────────────────────────────────────────────────
src_i18n = "src_dxb_t" if current_source == "dubai_hr" else "src_co_t"
src_name_en = t("source_dubai", LANG_EN) if current_source == "dubai_hr" else t("source_company", LANG_EN)
badge_class = "active-source-badge dubai-badge" if current_source == "dubai_hr" else "active-source-badge"
st.markdown(
    f'<div class="{badge_class}"><span data-i18n="active_pfx">Active:</span> <span data-i18n="{src_i18n}">{src_name_en}</span></div>',
    unsafe_allow_html=True,
)

# ── Chat history ──────────────────────────────────────────────────────────────
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=message.get("is_welcome", False))
        # Show source citation if stored in the message
        if message["role"] == "assistant":
            srcs       = sorted({os.path.basename(s) for s in (message.get("sources") or []) if s})[:3]
            msg_score  = message.get("best_score", float("inf"))
            msg_lang   = detect_language(message.get("content", ""))
            if srcs and msg_score <= settings.min_score_to_show_source:
                with st.expander(t("source_label", msg_lang)):
                    for s in srcs:
                        st.markdown(f"- `{s}`")
            elif srcs:
                src_html = " · ".join(f"📄 {s}" for s in srcs)
                st.markdown(f'<div class="source-citation">{src_html}</div>', unsafe_allow_html=True)
            elif not message.get("is_welcome"):
                st.markdown(
                    f'<p style="font-size:0.75rem;color:var(--color-muted,#888);font-style:italic;margin:4px 0 0">'
                    f'{t("general_knowledge_note", msg_lang)}</p>',
                    unsafe_allow_html=True,
                )

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
_SUGGESTIONS: dict[str, dict[str, list[str]]] = {
    "company": {
        LANG_EN: [
            "What is the annual leave policy?",
            "How do I apply for sick leave?",
            "What is the travel allowance?",
        ],
        LANG_AR: [
            "ما سياسة الإجازة السنوية؟",
            "كيف أطلب إجازة مرضية؟",
            "ما سياسة بدل السفر؟",
        ],
    },
    "dubai_hr": {
        LANG_EN: [
            "What are working hours under UAE law?",
            "How is end-of-service calculated?",
            "What are maternity leave rights?",
        ],
        LANG_AR: [
            "ما ساعات العمل حسب قانون العمل الإماراتي؟",
            "ما مكافأة نهاية الخدمة؟",
            "ما حقوق الموظفة الحامل؟",
        ],
    },
}

# ui_lang tracks the preferred language for suggestions — defaults by source
if "ui_lang" not in st.session_state:
    st.session_state.ui_lang = LANG_AR if current_source == "dubai_hr" else LANG_EN

if len(st.session_state.messages) <= 1 and engine and engine.is_ready:
    sugg_lang = st.session_state.ui_lang
    sugg_list = _SUGGESTIONS.get(current_source, {}).get(sugg_lang, [])

    st.markdown('<p class="suggestions-label">💡 <span data-i18n="try_asking">Try asking:</span></p>', unsafe_allow_html=True)
    if sugg_list:
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
    # Update suggestion language preference based on what the user typed
    _, _conf = detect_language_confidence(clean_query)
    if _conf >= 0.7:
        st.session_state.ui_lang = lang

    history_text = format_history(st.session_state.messages, settings.history_turns_for_context)

    if error_key == "input_too_long":
        shortcut_response = t("input_too_long", lang)
    elif error_key == "injection_attempt":
        shortcut_response = t("injection_attempt", lang)
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
            response    = ""
            source_docs = []

            if engine is None:
                response = t("init_error", lang)
                st.markdown(response)
            else:
                try:
                    thinking_slot = st.empty()
                    thinking_slot.markdown(_THINKING_HTML, unsafe_allow_html=True)

                    result = engine.answer(clean_query, history_text)

                    thinking_slot.empty()

                    response    = result.text
                    source_docs = result.source_docs or []
                    st.markdown(response)

                    unique_sources = sorted({os.path.basename(s) for s in source_docs if s})[:3]
                    best_score    = getattr(engine, "last_best_score", float("inf"))

                    if unique_sources and best_score <= settings.min_score_to_show_source:
                        with st.expander(t("source_label", lang)):
                            for s in unique_sources:
                                st.markdown(f"- `{s}`")
                    elif unique_sources:
                        src_html = " · ".join(f"📄 {s}" for s in unique_sources)
                        st.markdown(f'<div class="source-citation">{src_html}</div>',
                                    unsafe_allow_html=True)
                    else:
                        st.markdown(
                            f'<p style="font-size:0.75rem;color:var(--color-muted,#888);font-style:italic;margin:4px 0 0">'
                            f'{t("general_knowledge_note", lang)}</p>',
                            unsafe_allow_html=True,
                        )

                except Exception:
                    logger.exception("Query failed: %r", clean_query)
                    response = t("system_error", lang)
                    st.markdown(response)

        st.session_state.messages.append({
            "role":       "assistant",
            "content":    response,
            "sources":    source_docs,
            "best_score": getattr(engine, "last_best_score", float("inf")),
        })

    if len(st.session_state.messages) > settings.max_history_messages:
        st.session_state.messages = (
            st.session_state.messages[:1]
            + st.session_state.messages[-(settings.max_history_messages - 1):]
        )

    st.session_state.scroll_to_bottom = True
    st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
_social_items = [
    f'<a href="{_safe_url(url)}" class="social-link social-{name}" '
    f'target="_blank" rel="noopener noreferrer" aria-label="{_SOCIAL_META[name]["label"]}" '
    f'style="--social-hover:{_SOCIAL_META[name]["hover"]}">'
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    f'fill="currentColor" aria-hidden="true">{_SOCIAL_META[name]["svg"]}</svg>'
    f'</a>'
    for name, url in _SOCIAL.items() if _safe_url(url)
]
_social_bar = (
    f'<div class="social-bar">{"".join(_social_items)}</div>'
    if _social_items else ""
)

st.markdown(f"""
<div class="hr-footer">
  {_social_bar}
  <div class="hr-footer-meta">
    <span>HR Policy Assistant</span>
    <span class="hr-footer-dot">·</span>
    <span>Powered by <strong>Groq</strong> + <strong>LangChain</strong></span>
    <span class="hr-footer-dot">·</span>
    <span>v7.0</span>
  </div>
</div>
""", unsafe_allow_html=True)
