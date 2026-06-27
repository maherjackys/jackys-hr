"""
UI helpers: CSS injection + Theme/Language controls via st.components.v1.html()

Architecture:
- _UI_JS      : injected in an iframe (height=56) — the visible controls bar.
                postMessage() sends theme/lang events to the parent window.
- _PARENT_RECEIVER_JS : injected in a zero-height iframe — attaches a
                window.parent.addEventListener('message') listener so it runs
                in the parent Streamlit page context. st.markdown() cannot
                execute <script> tags in modern Streamlit (React strips them),
                so components.html() is required for both halves.
"""
from __future__ import annotations
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components


# ── JS payload: Theme toggle + i18n (AR/EN + RTL/LTR) ───────────────────────
_UI_JS = """
<style>
html, body {
  background: transparent !important;
  overflow: visible !important;
  margin: 0 !important;
  padding: 0 !important;
}
/* ── UI Controls floating bar ── */
.hr-controls-bar {
  position: fixed;
  top: 8px;
  right: 16px;
  z-index: 99999;
  display: flex;
  align-items: center;
  gap: 10px;
}
[dir="rtl"] .hr-controls-bar { right: auto; left: 16px; }

/* Theme toggle */
.theme-toggle-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 20px; border: 1.5px solid rgba(0,0,0,0.15);
  background: rgba(255,255,255,0.9); cursor: pointer; font-size: 13px;
  font-weight: 500; color: #333; transition: all 0.2s ease;
  backdrop-filter: blur(8px); white-space: nowrap; box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}
[data-theme="dark"] .theme-toggle-btn {
  background: rgba(30,30,30,0.9); border-color: rgba(255,255,255,0.15); color: #eee;
}
.theme-toggle-btn:hover { transform: translateY(-1px); box-shadow: 0 3px 8px rgba(0,0,0,0.15); }
.toggle-icon { font-size: 15px; line-height: 1; }

/* Lang switcher */
.lang-switcher-wrap { position: relative; }
.lang-switch-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: 20px; border: 1.5px solid rgba(0,0,0,0.15);
  background: rgba(255,255,255,0.9); cursor: pointer; font-size: 13px;
  font-weight: 600; color: #333; transition: all 0.2s ease;
  backdrop-filter: blur(8px); box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}
[data-theme="dark"] .lang-switch-btn {
  background: rgba(30,30,30,0.9); border-color: rgba(255,255,255,0.15); color: #eee;
}
.lang-switch-btn:hover { transform: translateY(-1px); box-shadow: 0 3px 8px rgba(0,0,0,0.15); }
.lang-chevron { font-size: 9px; opacity: 0.6; transition: transform 0.2s; }
.lang-switch-btn[aria-expanded="true"] .lang-chevron { transform: rotate(180deg); }
.lang-dropdown {
  display: none; position: absolute; top: calc(100% + 6px); right: 0;
  min-width: 140px; border-radius: 10px; border: 1px solid rgba(0,0,0,0.1);
  background: rgba(255,255,255,0.97); box-shadow: 0 6px 20px rgba(0,0,0,0.12);
  backdrop-filter: blur(10px); overflow: hidden; z-index: 10000;
}
[dir="rtl"] .lang-dropdown { right: auto; left: 0; }
[data-theme="dark"] .lang-dropdown {
  background: rgba(28,28,28,0.97); border-color: rgba(255,255,255,0.12);
}
.lang-dropdown.open { display: block; }
.lang-option {
  display: flex; align-items: center; gap: 8px; padding: 9px 14px;
  width: 100%; border: none; background: transparent; cursor: pointer;
  font-size: 13px; font-weight: 500; color: #333; text-align: left; transition: background 0.15s;
}
[dir="rtl"] .lang-option { text-align: right; flex-direction: row-reverse; }
[data-theme="dark"] .lang-option { color: #eee; }
.lang-option:hover { background: rgba(0,0,0,0.05); }
[data-theme="dark"] .lang-option:hover { background: rgba(255,255,255,0.07); }
.lang-option.active { font-weight: 700; color: #c0392b; }
.lang-flag { font-size: 16px; }
</style>

<div class="hr-controls-bar">
  <button id="hr-tt" class="theme-toggle-btn" aria-label="Toggle theme">
    <span class="toggle-icon" id="hr-ti">&#9790;</span>
    <span id="hr-tl">Dark</span>
  </button>
  <div class="lang-switcher-wrap">
    <button id="hr-lang-btn" class="lang-switch-btn" aria-label="Switch language" aria-expanded="false">
      <span class="lang-flag" id="hr-lang-flag">&#127468;&#127463;</span>
      <span id="hr-lang-label">EN</span>
      <span class="lang-chevron">&#9660;</span>
    </button>
    <div class="lang-dropdown" id="hr-lang-dd" role="menu">
      <button class="lang-option" role="menuitem" id="opt-en">
        <span class="lang-flag">&#127468;&#127463;</span><span>English</span>
      </button>
      <button class="lang-option" role="menuitem" id="opt-ar">
        <span class="lang-flag">&#127462;&#127466;</span><span>&#1575;&#1604;&#1593;&#1585;&#1576;&#1610;&#1577;</span>
      </button>
    </div>
  </div>
</div>

<script>
(function(){
  /* post message to parent Streamlit window */
  function postToParent(type, payload){
    try { window.parent.postMessage({type:'hr_'+type, payload:payload}, '*'); } catch(e){}
  }

  var TK = "hr_theme", LK = "hr_ui_lang", D = "dark", L = "light";

  /* ── Theme ── */
  function getTheme(){
    var s = localStorage.getItem(TK);
    if(s===D||s===L) return s;
    return window.matchMedia("(prefers-color-scheme:dark)").matches ? D : L;
  }
  function applyTheme(t){
    localStorage.setItem(TK, t);
    postToParent('theme', t);
    var i = document.getElementById("hr-ti");
    var l = document.getElementById("hr-tl");
    var T = getTranslations(localStorage.getItem(LK)||"en");
    if(i) i.innerHTML = (t===D) ? "&#9728;" : "&#9790;";
    if(l) l.textContent = (t===D) ? T.light_lbl : T.dark_lbl;
  }
  function toggleTheme(){
    var cur = localStorage.getItem(TK)||getTheme();
    applyTheme(cur===D ? L : D);
  }

  /* ── i18n ── */
  var TRANS = {
    en:{app_title:"HR Policy Assistant",app_subtitle:"Ask about any policy in seconds — instead of browsing for hours",stat_ml_t:"Multilingual",stat_ml_d:"Arabic & English",stat_ins_t:"Instant Answers",stat_ins_d:"Under a second",stat_sec_t:"Private & Secure",stat_sec_d:"Your data is safe",src_label:"SELECT KNOWLEDGE SOURCE",src_co_t:"Company Policy",src_co_d:"Answers based on your organization's internal HR policies.",src_dxb_t:"Dubai HR Policy",src_dxb_d:"Answers based on Dubai labor regulations and UAE HR policies.",active_pfx:"Active:",dark_lbl:"Dark",light_lbl:"Light",placeholder:"Type your question..."},
    ar:{app_title:"المساعد المعرفي للموارد البشرية",app_subtitle:"اسأل عن أي سياسة في ثوانٍ — بدلاً من التصفح لساعات",stat_ml_t:"متعدد اللغات",stat_ml_d:"عربي وإنجليزي",stat_ins_t:"إجابات فورية",stat_ins_d:"بأقل من ثانية",stat_sec_t:"آمن وخاص",stat_sec_d:"بياناتك محمية",src_label:"اختر مصدر المعرفة",src_co_t:"سياسة الشركة",src_co_d:"إجابات مبنية على السياسات الداخلية.",src_dxb_t:"سياسة دبي HR",src_dxb_d:"إجابات مبنية على قوانين العمل.",active_pfx:"المصدر:",dark_lbl:"داكن",light_lbl:"فاتح",placeholder:"اكتب سؤالك..."}
  };
  function getTranslations(lang){ return TRANS[lang]||TRANS.en; }

  function applyLang(lang){
    var T = getTranslations(lang);
    var rtl = (lang==="ar");
    localStorage.setItem(LK, lang);
    postToParent('lang', {lang:lang, rtl:rtl});

    var flag = document.getElementById("hr-lang-flag");
    var lbl  = document.getElementById("hr-lang-label");
    if(flag) flag.innerHTML = (lang==="ar") ? "&#127462;&#127466;" : "&#127468;&#127463;";
    if(lbl)  lbl.textContent = (lang==="ar") ? "AR" : "EN";

    ["opt-en","opt-ar"].forEach(function(id){
      var el = document.getElementById(id);
      if(el) el.classList.toggle("active", (id==="opt-ar") === (lang==="ar"));
    });

    postToParent('apply', {lang:lang, rtl:rtl, T:T});
  }

  function detectLang(){
    var s = localStorage.getItem(LK);
    if(s==="ar"||s==="en") return s;
    var n = (navigator.language||"en").toLowerCase();
    return n.startsWith("ar") ? "ar" : "en";
  }

  function toggleDropdown(){
    var dd = document.getElementById("hr-lang-dd");
    var btn = document.getElementById("hr-lang-btn");
    if(!dd||!btn) return;
    var isOpen = dd.classList.toggle("open");
    btn.setAttribute("aria-expanded", isOpen?"true":"false");
  }
  function closeDropdown(e){
    var wrap = document.querySelector(".lang-switcher-wrap");
    if(wrap && !wrap.contains(e.target)){
      var dd = document.getElementById("hr-lang-dd");
      var btn = document.getElementById("hr-lang-btn");
      if(dd) dd.classList.remove("open");
      if(btn) btn.setAttribute("aria-expanded","false");
    }
  }

  function boot(){
    applyTheme(getTheme());
    applyLang(detectLang());

    var tt = document.getElementById("hr-tt");
    if(tt){
      tt.addEventListener("click", toggleTheme);
      tt.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();toggleTheme();}});
    }

    var lb = document.getElementById("hr-lang-btn");
    if(lb){
      lb.addEventListener("click", toggleDropdown);
      lb.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();toggleDropdown();}});
    }

    var oen = document.getElementById("opt-en");
    var oar = document.getElementById("opt-ar");
    if(oen) oen.addEventListener("click",function(){
      applyLang("en");
      document.getElementById("hr-lang-dd").classList.remove("open");
      document.getElementById("hr-lang-btn").setAttribute("aria-expanded","false");
    });
    if(oar) oar.addEventListener("click",function(){
      applyLang("ar");
      document.getElementById("hr-lang-dd").classList.remove("open");
      document.getElementById("hr-lang-btn").setAttribute("aria-expanded","false");
    });

    document.addEventListener("click", closeDropdown);
  }

  document.readyState==="loading" ? document.addEventListener("DOMContentLoaded",boot) : boot();
})();
</script>
""".strip()

# Injected in a zero-height iframe so window.parent refers to the Streamlit page.
# This is required because st.markdown() does NOT execute <script> tags in
# modern Streamlit (React sanitizes them). components.html() always executes JS.
_PARENT_RECEIVER_JS = """
<script>
(function(){
  /* Attach listener to the parent Streamlit window, not this iframe */
  if(window.parent.__hrListenerSet) return;
  window.parent.__hrListenerSet = true;

  window.parent.addEventListener('message', function(e){
    var d = e.data;
    if(!d || typeof d.type !== 'string' || !d.type.startsWith('hr_')) return;

    if(d.type === 'hr_theme'){
      var theme = d.payload;
      var p = window.parent.document;
      [p.documentElement, p.body].forEach(function(el){ if(el) el.setAttribute('data-theme', theme); });
      var app = p.querySelector('[data-testid="stApp"]');
      if(app) app.setAttribute('data-theme', theme);
    }

    if(d.type === 'hr_apply'){
      var lang = d.payload.lang, rtl = d.payload.rtl, T = d.payload.T;
      var p = window.parent.document;

      p.documentElement.setAttribute('lang', lang);
      p.documentElement.setAttribute('dir',  rtl ? 'rtl' : 'ltr');
      p.body.setAttribute('dir', rtl ? 'rtl' : 'ltr');
      var app2 = p.querySelector('[data-testid="stApp"]');
      if(app2){ app2.setAttribute('dir', rtl ? 'rtl' : 'ltr'); app2.setAttribute('lang', lang); }

      p.querySelectorAll('[data-i18n]').forEach(function(el){
        var k = el.getAttribute('data-i18n');
        if(T[k] !== undefined){
          if(el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'){ el.placeholder = T[k]; }
          else { el.textContent = T[k]; }
        }
      });

      var inp = p.querySelector('[data-testid="stChatInputTextArea"], textarea');
      if(inp && T.placeholder) inp.placeholder = T.placeholder;
    }
  });
})();
</script>
""".strip()


def inject_css(css_path: Path) -> None:
    """Inject the main stylesheet into Streamlit."""
    try:
        css = css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        st.warning("⚠️ style.css not found — the app will render without custom styling.")
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def inject_ui_controls() -> None:
    """Inject the floating Dark/Light toggle + Language Switcher.

    Two iframes:
    1. height=56  — the visible controls bar (postMessage sender)
    2. height=0   — the invisible parent-window message listener
    """
    components.html(_UI_JS, height=56, scrolling=False)
    components.html(_PARENT_RECEIVER_JS, height=0, scrolling=False)


# ── Kept for backwards compat (no-ops) ───────────────────────────────────────
def inject_theme_toggle() -> None:
    pass


def inject_language_switcher() -> None:
    pass
