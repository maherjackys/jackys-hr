"""
UI helpers: CSS + Theme Toggle + Language Switcher.
All HTML/JS runs in the SAME Streamlit document context via st.markdown().
"""
from __future__ import annotations
from pathlib import Path
import streamlit as st


# ── Combined HTML: Dark Mode Toggle + Language Switcher ───────────────────────
_UI_CONTROLS_HTML = """
<div class="theme-toggle-wrap">
  <button id="hr-tt" class="theme-toggle-btn" role="switch"
          aria-checked="false" aria-label="Toggle dark/light mode" tabindex="0">
    <div class="toggle-track"><div class="toggle-knob"></div></div>
    <span id="hr-ti" class="toggle-icon">Moon</span>
    <span id="hr-tl">Dark</span>
  </button>
</div>
<div class="lang-switcher-wrap">
  <button id="hr-lang-btn" class="lang-switch-btn"
          aria-label="Switch language" aria-haspopup="true" tabindex="0">
    <span id="hr-lang-flag">GB</span>
    <span id="hr-lang-label">EN</span>
    <span class="lang-chevron">&#9660;</span>
  </button>
  <div class="lang-dropdown" id="hr-lang-dd" role="menu">
    <button class="lang-option" role="menuitem" id="opt-en">
      <span>GB</span><span>English</span>
    </button>
    <button class="lang-option" role="menuitem" id="opt-ar">
      <span>AE</span><span>&#1575;&#1604;&#1593;&#1585;&#1576;&#1610;&#1577;</span>
    </button>
  </div>
</div>
"""

# ── Combined JS: Theme + i18n (runs in Streamlit document) ───────────────────
_UI_CONTROLS_JS = """
<script>
(function(){
  /* ===== THEME ===== */
  var TK="hr_theme", D="dark", L="light";
  function tgi(){var s=localStorage.getItem(TK);if(s===D||s===L)return s;return window.matchMedia("(prefers-color-scheme: dark)").matches?D:L;}
  function tap(t){[document.documentElement,document.body].forEach(function(e){if(e)e.setAttribute("data-theme",t);});var a=document.querySelector("[data-testid=\'stApp\']");if(a)a.setAttribute("data-theme",t);localStorage.setItem(TK,t);}
  function tui(t){var i=document.getElementById("hr-ti"),l=document.getElementById("hr-tl"),tr=ltr(localStorage.getItem("hr_ui_lang")||"en");if(i)i.textContent=(t===D)?"Sun":"Moon";if(l)l.textContent=(t===D)?tr.light_lbl:tr.dark_lbl;}
  function ttog(){var c=localStorage.getItem(TK)||tgi(),n=(c===D)?L:D;tap(n);tui(n);}

  /* ===== i18n ===== */
  var LK="hr_ui_lang";
  var TRANS={
    en:{app_title:"HR Policy Assistant",app_subtitle:"Ask about any policy in seconds — instead of browsing for hours",stat_ml_t:"Multilingual",stat_ml_d:"Arabic & English",stat_ins_t:"Instant Answers",stat_ins_d:"Under a second",stat_sec_t:"Private & Secure",stat_sec_d:"Your data is safe",src_label:"SELECT KNOWLEDGE SOURCE",src_co_t:"Company Policy",src_co_d:"Answers based on your organization's internal HR policies.",src_dxb_t:"Dubai HR Policy",src_dxb_d:"Answers based on Dubai labor regulations and UAE HR policies.",active_pfx:"Active:",dark_lbl:"Dark",light_lbl:"Light"},
    ar:{app_title:"\u0627\u0644\u0645\u0633\u0627\u0639\u062f \u0627\u0644\u0645\u0639\u0631\u0641\u064a \u0644\u0644\u0645\u0648\u0627\u0631\u062f \u0627\u0644\u0628\u0634\u0631\u064a\u0629",app_subtitle:"\u0627\u0633\u0623\u0644 \u0639\u0646 \u0623\u064a \u0633\u064a\u0627\u0633\u0629 \u0641\u064a \u062b\u0648\u0627\u0646\u064d \u2014 \u0628\u062f\u0644\u0627\u064b \u0645\u0646 \u0627\u0644\u062a\u0635\u0641\u062d \u0644\u0633\u0627\u0639\u0627\u062a",stat_ml_t:"\u0645\u062a\u0639\u062f\u062f \u0627\u0644\u0644\u063a\u0627\u062a",stat_ml_d:"\u0639\u0631\u0628\u064a \u0648\u0625\u0646\u062c\u0644\u064a\u0632\u064a",stat_ins_t:"\u0625\u062c\u0627\u0628\u0627\u062a \u0641\u0648\u0631\u064a\u0629",stat_ins_d:"\u0628\u0623\u0642\u0644 \u0645\u0646 \u062b\u0627\u0646\u064a\u0629",stat_sec_t:"\u0622\u0645\u0646 \u0648\u062e\u0627\u0635",stat_sec_d:"\u0628\u064a\u0627\u0646\u0627\u062a\u0643 \u0645\u062d\u0645\u064a\u0629",src_label:"\u0627\u062e\u062a\u0631 \u0645\u0635\u062f\u0631 \u0627\u0644\u0645\u0639\u0631\u0641\u0629",src_co_t:"\u0633\u064a\u0627\u0633\u0629 \u0627\u0644\u0634\u0631\u0643\u0629",src_co_d:"\u0625\u062c\u0627\u0628\u0627\u062a \u0645\u0628\u0646\u064a\u0629 \u0639\u0644\u0649 \u0627\u0644\u0633\u064a\u0627\u0633\u0627\u062a \u0627\u0644\u062f\u0627\u062e\u0644\u064a\u0629.",src_dxb_t:"\u0633\u064a\u0627\u0633\u0629 \u062f\u0628\u064a HR",src_dxb_d:"\u0625\u062c\u0627\u0628\u0627\u062a \u0645\u0628\u0646\u064a\u0629 \u0639\u0644\u0649 \u0642\u0648\u0627\u0646\u064a\u0646 \u0627\u0644\u0639\u0645\u0644.",active_pfx:"\u0627\u0644\u0645\u0635\u062f\u0631:",dark_lbl:"\u062f\u0627\u0643\u0646",light_lbl:"\u0641\u0627\u062a\u062d"}
  };

  function ltr(lang){return TRANS[lang]||TRANS.en;}

  function lapply(lang){
    var T=ltr(lang),rtl=(lang==="ar");
    document.documentElement.setAttribute("lang",lang);
    document.documentElement.setAttribute("dir",rtl?"rtl":"ltr");
    document.body.setAttribute("dir",rtl?"rtl":"ltr");
    var sa=document.querySelector("[data-testid=\'stApp\']");
    if(sa){sa.setAttribute("dir",rtl?"rtl":"ltr");sa.setAttribute("lang",lang);}
    document.querySelectorAll("[data-i18n]").forEach(function(el){
      var k=el.getAttribute("data-i18n");
      if(T[k]!==undefined){
        if(el.tagName==="INPUT"||el.tagName==="TEXTAREA"){el.placeholder=T[k];}
        else{el.textContent=T[k];}
      }
    });
    var f=document.getElementById("hr-lang-flag"),lb=document.getElementById("hr-lang-label");
    if(f)f.textContent=(lang==="ar")?"AE":"GB";
    if(lb)lb.textContent=(lang==="ar")?"AR":"EN";
    var tl=document.getElementById("hr-tl"),th=localStorage.getItem(TK)||"light";
    if(tl)tl.textContent=(th===D)?T.light_lbl:T.dark_lbl;
    localStorage.setItem(LK,lang);
  }

  function ldetect(){var s=localStorage.getItem(LK);if(s==="ar"||s==="en")return s;var n=(navigator.language||"en").toLowerCase();return n.startsWith("ar")?"ar":"en";}

  function ldd(){var dd=document.getElementById("hr-lang-dd");if(dd)dd.classList.toggle("open");}
  function lclose(e){var w=document.querySelector(".lang-switcher-wrap");if(w&&!w.contains(e.target)){var dd=document.getElementById("hr-lang-dd");if(dd)dd.classList.remove("open");}}

  /* ===== BOOT ===== */
  function boot(){
    var theme=tgi();tap(theme);tui(theme);
    var tb=document.getElementById("hr-tt");
    if(tb){tb.addEventListener("click",ttog);tb.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();ttog();}});}

    var lang=ldetect();lapply(lang);
    var lb=document.getElementById("hr-lang-btn");
    if(lb){lb.addEventListener("click",ldd);lb.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();ldd();}});}

    var oen=document.getElementById("opt-en"),oar=document.getElementById("opt-ar");
    if(oen)oen.addEventListener("click",function(){lapply("en");document.getElementById("hr-lang-dd").classList.remove("open");});
    if(oar)oar.addEventListener("click",function(){lapply("ar");document.getElementById("hr-lang-dd").classList.remove("open");});
    document.addEventListener("click",lclose);

    new MutationObserver(function(){
      tap(localStorage.getItem(TK)||L);
      lapply(localStorage.getItem(LK)||"en");
    }).observe(document.body,{childList:true,subtree:false});
  }

  document.readyState==="loading"?document.addEventListener("DOMContentLoaded",boot):boot();
})();
</script>
"""


def inject_css(css_path: Path) -> None:
    """Inject the main stylesheet into Streamlit."""
    try:
        css = css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def inject_theme_toggle() -> None:
    """Inject Dark/Light toggle HTML. Call after inject_css()."""
    pass  # Handled by inject_ui_controls()


def inject_language_switcher() -> None:
    """Inject Language Switcher HTML. Call after inject_css()."""
    pass  # Handled by inject_ui_controls()


def inject_ui_controls() -> None:
    """
    Inject BOTH the Dark/Light toggle AND Language Switcher in ONE st.markdown() call.
    This ensures all JS runs in the same document context (no iframe isolation).
    Call after inject_css().
    """
    st.markdown(_UI_CONTROLS_HTML, unsafe_allow_html=True)
    st.markdown(_UI_CONTROLS_JS,   unsafe_allow_html=True)
