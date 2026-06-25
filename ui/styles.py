"""
UI helpers: CSS injection + Dark/Light Mode toggle + Language Switcher.
"""
from __future__ import annotations
from pathlib import Path
import streamlit as st

# ── Dark/Light Mode JS ────────────────────────────────────────────────────────
_THEME_JS = """
<script>
(function(){
  var K="hr_theme",D="dark",L="light";
  function gi(){var s=localStorage.getItem(K);if(s===D||s===L)return s;return window.matchMedia("(prefers-color-scheme: dark)").matches?D:L;}
  function ap(t){[document.documentElement,document.body].forEach(function(e){if(e)e.setAttribute("data-theme",t);});var a=document.querySelector("[data-testid=\'stApp\']");if(a)a.setAttribute("data-theme",t);localStorage.setItem(K,t);}
  function ui(t){var i=document.getElementById("hr-ti"),l=document.getElementById("hr-tl");if(i)i.textContent=(t===D)?"Sun":"Moon";if(l)l.textContent=(t===D)?"Light":"Dark";}
  function tog(){var c=localStorage.getItem(K)||gi(),n=(c===D)?L:D;ap(n);ui(n);}
  function boot(){var t=gi();ap(t);ui(t);var b=document.getElementById("hr-tt");if(b){b.addEventListener("click",tog);b.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();tog();}});}new MutationObserver(function(){ap(localStorage.getItem(K)||L);}).observe(document.body,{childList:true,subtree:false});}
  document.readyState==="loading"?document.addEventListener("DOMContentLoaded",boot):boot();
})();
</script>
"""

_TOGGLE_HTML = """
<div class="theme-toggle-wrap">
  <button id="hr-tt" class="theme-toggle-btn" role="switch" aria-checked="false" aria-label="Toggle dark/light mode" tabindex="0">
    <div class="toggle-track"><div class="toggle-knob"></div></div>
    <span id="hr-ti" class="toggle-icon">Moon</span>
    <span id="hr-tl">Dark</span>
  </button>
</div>
"""

# ── Language Switcher JS ──────────────────────────────────────────────────────
_LANG_JS = """
<script>
(function(){
  var LK = "hr_ui_lang";
  var T = {
    en: {
      app_title:       "HR Policy Assistant",
      app_subtitle:    "Ask about any policy in seconds — instead of browsing for hours",
      stat_ml_t:       "Multilingual",    stat_ml_d: "Arabic & English",
      stat_ins_t:      "Instant Answers", stat_ins_d: "Under a second",
      stat_sec_t:      "Private & Secure",stat_sec_d: "Your data is safe",
      src_label:       "SELECT KNOWLEDGE SOURCE",
      src_co_t:        "Company Policy",
      src_co_d:        "Answers based on your organization's internal HR policies.",
      src_dxb_t:       "Dubai HR Policy",
      src_dxb_d:       "Answers based on Dubai labor regulations and UAE HR policies.",
      active_pfx:      "Active:",
      dark_lbl:        "Dark",
      light_lbl:       "Light"
    },
    ar: {
      app_title:       "المساعد المعرفي للموارد البشرية",
      app_subtitle:    "اسأل عن أي سياسة في ثوانٍ — بدلاً من التصفح لساعات",
      stat_ml_t:       "متعدد اللغات",    stat_ml_d: "عربي وإنجليزي",
      stat_ins_t:      "إجابات فورية",    stat_ins_d: "بأقل من ثانية",
      stat_sec_t:      "آمن وخاص",        stat_sec_d: "بياناتك محمية",
      src_label:       "اختر مصدر المعرفة",
      src_co_t:        "سياسة الشركة",
      src_co_d:        "إجابات مبنية على السياسات الداخلية لمؤسستك.",
      src_dxb_t:       "سياسة دبي HR",
      src_dxb_d:       "إجابات مبنية على قوانين العمل الإماراتية وسياسات دبي.",
      active_pfx:      "المصدر:",
      dark_lbl:        "داكن",
      light_lbl:       "فاتح"
    }
  };

  function detectLang(){
    var s=localStorage.getItem(LK);
    if(s==="ar"||s==="en")return s;
    var n=(navigator.language||navigator.userLanguage||"en").toLowerCase();
    return n.startsWith("ar")?"ar":"en";
  }

  function applyLang(lang){
    var tr=T[lang]||T.en;
    var rtl=(lang==="ar");
    document.documentElement.setAttribute("lang",lang);
    document.documentElement.setAttribute("dir",rtl?"rtl":"ltr");
    document.body.setAttribute("dir",rtl?"rtl":"ltr");
    var sa=document.querySelector("[data-testid=\'stApp\']");
    if(sa){sa.setAttribute("dir",rtl?"rtl":"ltr");sa.setAttribute("lang",lang);}

    // Update i18n elements
    document.querySelectorAll("[data-i18n]").forEach(function(el){
      var k=el.getAttribute("data-i18n");
      if(tr[k]!==undefined){
        if(el.tagName==="INPUT"||el.tagName==="TEXTAREA"){el.placeholder=tr[k];}
        else{el.textContent=tr[k];}
      }
    });

    // Update switcher badge
    var flag=document.getElementById("hr-lang-flag"),lbl=document.getElementById("hr-lang-label");
    if(flag)flag.textContent=(lang==="ar")?"AE":"GB";
    if(lbl)lbl.textContent=(lang==="ar")?"AR":"EN";

    // Update theme toggle label too
    var tl=document.getElementById("hr-tl"),theme=localStorage.getItem("hr_theme")||"light";
    if(tl)tl.textContent=(theme==="dark")?tr.light_lbl:tr.dark_lbl;

    localStorage.setItem(LK,lang);
  }

  window.hrSetLang=function(lang){
    applyLang(lang);
    var dd=document.getElementById("hr-lang-dd");
    if(dd)dd.classList.remove("open");
  };

  function toggleDD(){
    var dd=document.getElementById("hr-lang-dd");
    if(dd)dd.classList.toggle("open");
  }

  function closeDD(e){
    var w=document.querySelector(".lang-switcher-wrap");
    if(w&&!w.contains(e.target)){
      var dd=document.getElementById("hr-lang-dd");
      if(dd)dd.classList.remove("open");
    }
  }

  function boot(){
    var lang=detectLang();
    applyLang(lang);
    var btn=document.getElementById("hr-lang-btn");
    if(btn){btn.addEventListener("click",toggleDD);btn.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();toggleDD();}});}
    document.addEventListener("click",closeDD);
    new MutationObserver(function(){applyLang(localStorage.getItem(LK)||"en");}).observe(document.body,{childList:true,subtree:false});
  }

  document.readyState==="loading"?document.addEventListener("DOMContentLoaded",boot):boot();
})();
</script>
"""

_LANG_HTML = """
<div class="lang-switcher-wrap">
  <button id="hr-lang-btn" class="lang-switch-btn" aria-label="Switch language" aria-haspopup="true" tabindex="0">
    <span id="hr-lang-flag">GB</span>
    <span id="hr-lang-label">EN</span>
    <span class="lang-chevron">&#9660;</span>
  </button>
  <div class="lang-dropdown" id="hr-lang-dd" role="menu">
    <button class="lang-option" role="menuitem" onclick="window.hrSetLang('en')">
      <span>GB</span><span>English</span>
    </button>
    <button class="lang-option" role="menuitem" onclick="window.hrSetLang('ar')">
      <span>AE</span><span>العربية</span>
    </button>
  </div>
</div>
"""


def inject_css(css_path: Path) -> None:
    """Inject the main stylesheet into Streamlit."""
    try:
        css = css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def inject_theme_toggle() -> None:
    """Inject the Dark/Light toggle. Call after inject_css()."""
    st.markdown(_TOGGLE_HTML, unsafe_allow_html=True)
    st.markdown(_THEME_JS,    unsafe_allow_html=True)


def inject_language_switcher() -> None:
    """Inject the Language Switcher + i18n JS engine. Call after inject_css()."""
    st.markdown(_LANG_HTML, unsafe_allow_html=True)
    st.markdown(_LANG_JS,   unsafe_allow_html=True)
