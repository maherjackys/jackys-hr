"""
Language detection and centralized UI strings.

Every user-facing message lives in one dictionary (STRINGS), keyed by a
short identifier and language code. Adding a new language means adding
one new key per entry here — no hunting through business logic.
"""
from __future__ import annotations

LANG_AR = "ar"
LANG_EN = "en"


def detect_language_confidence(text: str) -> tuple[str, float]:
    """
    Return (language_code, confidence) where confidence is 0.0–1.0.

    Heuristic:
    - Count Arabic Unicode chars (U+0600–U+06FF) and basic Latin letters.
    - If Arabic share > 30% → Arabic.
    - For very short inputs (≤ 2 words) that are ambiguous → default to Arabic,
      since most users of this UAE-focused assistant are Arabic speakers.
    - Confidence reflects how clear-cut the detection is.
    """
    if not text:
        return LANG_EN, 0.5

    stripped = text.strip()
    total_alpha = 0
    arabic_count = 0
    latin_count = 0

    for ch in stripped:
        if "؀" <= ch <= "ۿ":
            arabic_count += 1
            total_alpha += 1
        elif ch.isalpha() and ord(ch) < 0x0300:  # Basic Latin / Latin-1
            latin_count += 1
            total_alpha += 1

    if total_alpha == 0:
        # Only digits, punctuation, spaces — default Arabic (UAE context)
        return LANG_AR, 0.5

    arabic_ratio = arabic_count / total_alpha

    # Short ambiguous inputs (≤ 2 words with no clear script) → default Arabic
    word_count = len(stripped.split())
    if word_count <= 2 and arabic_ratio < 0.3 and latin_count == 0:
        return LANG_AR, 0.5

    if arabic_ratio > 0.30:
        # Confidence scales: pure Arabic → 1.0, barely over threshold → 0.6
        confidence = min(1.0, 0.6 + arabic_ratio * 0.4)
        return LANG_AR, round(confidence, 2)

    # Mostly Latin
    confidence = min(1.0, 0.6 + (1.0 - arabic_ratio) * 0.4)
    return LANG_EN, round(confidence, 2)


def detect_language(text: str) -> str:
    """Detect language of *text*. Returns LANG_AR or LANG_EN."""
    lang, _ = detect_language_confidence(text)
    return lang


STRINGS: dict[str, dict[str, str]] = {
    "welcome_company": {
        LANG_AR: "مرحباً بك! أنا مساعدك لسياسات الموارد البشرية.\nيمكنني الإجابة على أسئلتك فوراً استناداً إلى السياسات الرسمية للشركة.\n\nجرّب أن تسأل:\n• ما سياسة الإجازات السنوية؟\n• كيف أقدّم طلب إجازة مرضية؟",
        LANG_EN: "Welcome! I'm your HR Policy Assistant.\nI can answer your questions instantly based on your company's official HR policies.\n\nTry asking:\n• What is the annual leave policy?\n• How do I apply for sick leave?",
    },
    "welcome_dubai": {
        LANG_AR: "مرحباً في مساعد سياسات دبي للموارد البشرية 🇦🇪\nاسألني عن أنظمة العمل في دبي والإمارات.",
        LANG_EN: "Welcome to Dubai HR Policy Assistant! Ask me about Dubai labor regulations and UAE HR policies.",
    },
    "active_pfx": {
        LANG_AR: "المصدر النشط:",
        LANG_EN: "Active:",
    },
    "source_company": {
        LANG_AR: "سياسة الشركة",
        LANG_EN: "Company Policy",
    },
    "source_dubai": {
        LANG_AR: "سياسة دبي HR",
        LANG_EN: "Dubai HR Policy",
    },
    "greeting_reply": {
        LANG_AR: "أهلاً وسهلاً! كيف يمكنني مساعدتك في سياسات الموارد البشرية؟",
        LANG_EN: "Hello! How can I help you with HR policies today?",
    },
    "no_documents": {
        LANG_AR: "⚠️ لم أجد ملفات PDF في مجلد `hr_documents`. أضفها أولاً.",
        LANG_EN: "⚠️ No PDF files found in `hr_documents`. Please add your policy files first.",
    },
    "out_of_scope": {
        LANG_AR: "يبدو أن هذا السؤال خارج نطاق المستندات المتوفرة لديّ.",
        LANG_EN: "This question seems outside the scope of the available documents.",
    },
    "no_answer": {
        LANG_AR: "عذراً، لم أجد إجابة واضحة في المستندات. هل يمكنك إعادة صياغة سؤالك؟",
        LANG_EN: "Sorry, I couldn't find a clear answer. Could you rephrase your question?",
    },
    "rate_limited": {
        LANG_AR: "⏳ عدد كبير من الأسئلة بوقت قصير. خذ نفساً وحاول بعد لحظات.",
        LANG_EN: "⏳ You're sending requests too fast. Please wait a moment and try again.",
    },
    "input_too_long": {
        LANG_AR: "⚠️ سؤالك طويل جداً. حاول تلخيصه.",
        LANG_EN: "⚠️ Your question is too long. Please shorten it.",
    },
    "system_error": {
        LANG_AR: "⚠️ حدث خطأ غير متوقع. تم تسجيله وسنعمل على حله.",
        LANG_EN: "⚠️ An unexpected error occurred. It has been logged for review.",
    },
    "rate_limit_error": {
        LANG_AR: "⚠️ تم الوصول إلى الحد اليومي للطلبات{wait}. يرجى المحاولة لاحقاً.",
        LANG_EN: "⚠️ Daily request limit reached{wait}. Please try again later.",
    },
    "init_error": {
        LANG_AR: "⚠️ تعذّر تهيئة النظام. تأكد من صحة مفتاح API والاتصال بالإنترنت.",
        LANG_EN: "⚠️ System initialization failed. Check your API key and internet connection.",
    },
    "injection_attempt": {
        LANG_AR: "⚠️ تم اكتشاف محتوى غير مسموح به في سؤالك.",
        LANG_EN: "⚠️ Your input contains disallowed content and has been sanitized.",
    },
    "general_knowledge_note": {
        LANG_AR: "💡 إجابة من المعرفة العامة",
        LANG_EN: "💡 General knowledge answer",
    },
    "source_label": {
        LANG_AR: "📄 المصدر",
        LANG_EN: "📄 Source",
    },
    "confirm_switch_title": {
        LANG_AR: "تغيير مصدر المعرفة",
        LANG_EN: "Switch Knowledge Source",
    },
    "confirm_switch_body": {
        LANG_AR: "سيؤدي هذا إلى مسح سجل المحادثة الحالي. هل تريد المتابعة؟",
        LANG_EN: "This will clear your current conversation history. Do you want to continue?",
    },
    "confirm_yes": {
        LANG_AR: "نعم، تابع",
        LANG_EN: "Yes, continue",
    },
    "confirm_no": {
        LANG_AR: "لا، إلغاء",
        LANG_EN: "No, cancel",
    },
    "new_chat_btn": {
        LANG_AR: "🗑️ محادثة جديدة",
        LANG_EN: "🗑️ New Chat",
    },
    "try_asking": {
        LANG_AR: "جرب أن تسأل:",
        LANG_EN: "Try asking:",
    },
    "suggestions_label": {
        LANG_AR: "💡 اقتراحات",
        LANG_EN: "💡 Suggestions",
    },
    "card_active": {
        LANG_AR: "✓ نشط",
        LANG_EN: "✓ Active",
    },
    "card_select": {
        LANG_AR: "اختر",
        LANG_EN: "Select",
    },
    # ── Header / hero ────────────────────────────────────────────────────────
    "app_title": {
        LANG_AR: "مساعد سياسات الموارد البشرية",
        LANG_EN: "HR Policy Assistant",
    },
    "app_subtitle": {
        LANG_AR: "احصل على إجابات فورية لأي سياسة — بدلاً من البحث لساعات",
        LANG_EN: "Ask about any policy in seconds — instead of browsing for hours",
    },
    # ── Stats bar ────────────────────────────────────────────────────────────
    "stat_ml_t": {
        LANG_AR: "ثنائي اللغة",
        LANG_EN: "Multilingual",
    },
    "stat_ml_d": {
        LANG_AR: "عربي وإنجليزي",
        LANG_EN: "Arabic & English",
    },
    "stat_ins_t": {
        LANG_AR: "إجابات فورية",
        LANG_EN: "Instant Answers",
    },
    "stat_ins_d": {
        LANG_AR: "في أقل من ثانية",
        LANG_EN: "Under a second",
    },
    "stat_sec_t": {
        LANG_AR: "خاص وآمن",
        LANG_EN: "Private & Secure",
    },
    "stat_sec_d": {
        LANG_AR: "بياناتك محمية",
        LANG_EN: "Your data is safe",
    },
    # ── Source picker ────────────────────────────────────────────────────────
    "src_label": {
        LANG_AR: "اختر مصدر المعرفة",
        LANG_EN: "SELECT KNOWLEDGE SOURCE",
    },
    "src_co_t": {
        LANG_AR: "سياسة الشركة",
        LANG_EN: "Company Policy",
    },
    "src_co_d": {
        LANG_AR: "إجابات مستندة إلى سياسات الموارد البشرية الداخلية للمؤسسة.",
        LANG_EN: "Answers based on your organization's internal HR policies.",
    },
    "src_dxb_t": {
        LANG_AR: "سياسة دبي للموارد البشرية",
        LANG_EN: "Dubai HR Policy",
    },
    "src_dxb_d": {
        LANG_AR: "إجابات مستندة إلى أنظمة العمل في دبي والإمارات.",
        LANG_EN: "Answers based on Dubai labor regulations and UAE HR policies.",
    },
    # ── Chat input placeholder ────────────────────────────────────────────────
    "chat_placeholder": {
        LANG_AR: "اكتب سؤالك هنا…",
        LANG_EN: "Type your question… | اكتب سؤالك هنا…",
    },
}


def t(key: str, lang: str) -> str:
    """Translate a string key into the requested language, defaulting to English."""
    bucket = STRINGS.get(key, {})
    return bucket.get(lang, bucket.get(LANG_EN, key))


_GREETING_EXACT = frozenset({
    "مرحبا", "مرحباً", "هلا", "اهلين", "أهلاً", "السلام عليكم", "سلام",
    "hi", "hello", "hey",
})

_GREETING_PHRASES = (
    "good morning", "good evening", "good afternoon", "how are you",
    "صباح الخير", "مساء الخير",
)


def is_greeting(text: str) -> bool:
    """Return True only when the entire message is a short greeting."""
    import re as _re

    stripped = text.strip()
    lowered = stripped.lower()

    clean = _re.sub(r"[^\w\s]", "", lowered).strip()
    if clean in _GREETING_EXACT:
        return True

    clean_words = clean.split()
    if (
        1 < len(clean_words) <= 3
        and clean_words[0] in _GREETING_EXACT
        and "?" not in stripped
    ):
        return True

    for phrase in _GREETING_PHRASES:
        if lowered == phrase or lowered.startswith(phrase + " ") or lowered.startswith(phrase + "،"):
            return True

    return False
