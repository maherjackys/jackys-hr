"""
Language detection and centralized UI strings.

Every user-facing message lives in one dictionary (STRINGS), keyed by a
short identifier and language code. Adding a new language means adding
one new key per entry here — no hunting through business logic.
"""
from __future__ import annotations

LANG_AR = "ar"
LANG_EN = "en"


def detect_language(text: str) -> str:
    """Heuristic: if more than 20% of characters are Arabic, treat as Arabic."""
    if not text:
        return LANG_EN
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    return LANG_AR if arabic_chars > len(text) * 0.2 else LANG_EN


STRINGS: dict[str, dict[str, str]] = {
    "welcome_ar": {LANG_AR: (
        "مرحباً بك في المساعد المعرفي لسياسات الموارد البشرية 👋\n"
        "ضع ملفات PDF السياسات في مجلد hr_documents ثم اسألني عنها!"
    )},
    "welcome_en": {LANG_EN: "Hello! Place your HR policy PDFs in the hr_documents folder, then ask me anything."},
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
    "init_error": {
        LANG_AR: "⚠️ تعذّر تهيئة النظام. تأكد من صحة مفتاح API والاتصال بالإنترنت.",
        LANG_EN: "⚠️ System initialization failed. Check your API key and internet connection.",
    },
}


def t(key: str, lang: str) -> str:
    """Translate a string key into the requested language, defaulting to English."""
    bucket = STRINGS.get(key, {})
    return bucket.get(lang, bucket.get(LANG_EN, key))


GREETING_KEYWORDS = (
    "مرحبا", "مرحباً", "هلا", "اهلين", "أهلاً", "السلام عليكم", "سلام", "صباح", "مساء",
    "hi", "hello", "hey", "good morning", "good evening", "how are you",
)


def is_greeting(text: str) -> bool:
    lowered = text.strip().lower()
    return any(keyword in lowered for keyword in GREETING_KEYWORDS)
