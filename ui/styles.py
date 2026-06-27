"""
UI helpers: CSS injection + Theme/Language controls via st.components.v1.html()

Architecture:
- _UI_JS: single iframe (height=56) — the visible controls bar.
  It sends postMessage() to the parent window AND sets up the parent's
  message listener from within the iframe (window.parent.addEventListener).
  This single-iframe approach avoids a phantom zero-height iframe that would
  block pointer events in the top-right corner.
"""
from __future__ import annotations
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components


_UI_JS = """
<style>
html, body {
  background: transparent !important;
  overflow: visible !important;
  margin: 0 !important;
  padding: 0 !important;
}
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

.theme-toggle-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: 20px; border: 1.5px solid rgba(0,0,0,0.15);
  background: rgba(255,255,255,0.92); cursor: pointer; font-size: 13px;
  font-weight: 500; color: #333; transition: all 0.2s ease;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  white-space: nowrap; box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}
[data-theme="dark"] .theme-toggle-btn {
  background: rgba(22,27,34,0.92); border-color: rgba(255,255,255,0.15); color: #e6edf3;
}
.theme-toggle-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.18); }
.theme-toggle-btn:active { transform: scale(0.97); }
.toggle-icon { font-size: 14px; line-height: 1; }

.lang-switcher-wrap { position: relative; }
.lang-switch-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: 20px; border: 1.5px solid rgba(0,0,0,0.15);
  background: rgba(255,255,255,0.92); cursor: pointer; font-size: 13px;
  font-weight: 600; color: #333; transition: all 0.2s ease;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}
[data-theme="dark"] .lang-switch-btn {
  background: rgba(22,27,34,0.92); border-color: rgba(255,255,255,0.15); color: #e6edf3;
}
.lang-switch-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.18); }
.lang-chevron { font-size: 9px; opacity: 0.5; transition: transform 0.2s; }
.lang-switch-btn[aria-expanded="true"] .lang-chevron { transform: rotate(180deg); }
.lang-dropdown {
  display: none; position: absolute; top: calc(100% + 6px); right: 0;
  min-width: 148px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.1);
  background: rgba(255,255,255,0.98); box-shadow: 0 8px 24px rgba(0,0,0,0.14);
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  overflow: hidden; z-index: 10000;
}
[dir="rtl"] .lang-dropdown { right: auto; left: 0; }
[data-theme="dark"] .lang-dropdown {
  background: rgba(22,27,34,0.98); border-color: rgba(255,255,255,0.12);
  box-shadow: 0 8px 24px rgba(0,0,0,0.45);
}
.lang-dropdown.open { display: block; animation: dd-in 0.15s ease; }
@keyframes dd-in { from { opacity:0; transform:translateY(-4px) } to { opacity:1; transform:none } }
.lang-option {
  display: flex; align-items: center; gap: 8px; padding: 10px 14px;
  width: 100%; border: none; background: transparent; cursor: pointer;
  font-size: 13px; font-weight: 500; color: #333; text-align: left;
  transition: background 0.12s;
}
[dir="rtl"] .lang-option { text-align: right; flex-direction: row-reverse; }
[data-theme="dark"] .lang-option { color: #e6edf3; }
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
  var TK = "hr_theme", LK = "hr_ui_lang", D = "dark", L = "light";

  /* ── Send message to parent Streamlit window ── */
  function postToParent(type, payload){
    try { window.parent.postMessage({type:'hr_'+type, payload:payload}, '*'); } catch(e){}
  }

  /* ── Attach receiver on the PARENT window (runs from inside this iframe) ── */
  function attachParentReceiver(){
    try {
      if(window.parent.__hrListenerSet) return;
      window.parent.__hrListenerSet = true;
      window.parent.addEventListener('message', function(e){
        var d = e.data;
        if(!d || typeof d.type !== 'string' || !d.type.startsWith('hr_')) return;
        var p = window.parent.document;

        if(d.type === 'hr_theme'){
          var th = d.payload;
          [p.documentElement, p.body].forEach(function(el){ if(el) el.setAttribute('data-theme', th); });
          var app = p.querySelector('[data-testid="stApp"]');
          if(app) app.setAttribute('data-theme', th);
        }

        if(d.type === 'hr_apply'){
          var lang = d.payload.lang, rtl = d.payload.rtl, T = d.payload.T;
          p.documentElement.setAttribute('lang', lang);
          p.documentElement.setAttribute('dir',  rtl ? 'rtl' : 'ltr');
          p.body.setAttribute('dir', rtl ? 'rtl' : 'ltr');
          var app2 = p.querySelector('[data-testid="stApp"]');
          if(app2){ app2.setAttribute('dir', rtl?'rtl':'ltr'); app2.setAttribute('lang', lang); }
          p.querySelectorAll('[data-i18n]').forEach(function(el){
            var k = el.getAttribute('data-i18n');
            if(T[k]!==undefined){
              if(el.tagName==='INPUT'||el.tagName==='TEXTAREA'){ el.placeholder=T[k]; }
              else { el.textContent=T[k]; }
            }
          });
          var inp = p.querySelector('[data-testid="stChatInputTextArea"], textarea');
          if(inp && T.placeholder) inp.placeholder = T.placeholder;
        }
      });
    } catch(ex){}
  }

  /* ── i18n ── */
  var TRANS = {
    en:{app_title:"HR Policy Assistant",app_subtitle:"Ask about any policy in seconds — instead of browsing for hours",stat_ml_t:"Multilingual",stat_ml_d:"Arabic & English",stat_ins_t:"Instant Answers",stat_ins_d:"Under a second",stat_sec_t:"Private & Secure",stat_sec_d:"Your data is safe",src_label:"SELECT KNOWLEDGE SOURCE",src_co_t:"Company Policy",src_co_d:"Answers based on your organization's internal HR policies.",src_dxb_t:"Dubai HR Policy",src_dxb_d:"Answers based on Dubai labor regulations and UAE HR policies.",active_pfx:"Active:",dark_lbl:"Dark",light_lbl:"Light",placeholder:"Type your question..."},
    ar:{app_title:"المساعد المعرفي للموارد البشرية",app_subtitle:"اسأل عن أي سياسة في ثوانٍ — بدلاً من التصفح لساعات",stat_ml_t:"متعدد اللغات",stat_ml_d:"عربي وإنجليزي",stat_ins_t:"إجابات فورية",stat_ins_d:"بأقل من ثانية",stat_sec_t:"آمن وخاص",stat_sec_d:"بياناتك محمية",src_label:"اختر مصدر المعرفة",src_co_t:"سياسة الشركة",src_co_d:"إجابات مبنية على السياسات الداخلية.",src_dxb_t:"سياسة دبي HR",src_dxb_d:"إجابات مبنية على قوانين العمل.",active_pfx:"المصدر:",dark_lbl:"داكن",light_lbl:"فاتح",placeholder:"اكتب سؤالك..."}
  };
  function getTranslations(lang){ return TRANS[lang]||TRANS.en; }

  function getTheme(){
    var s = localStorage.getItem(TK);
    if(s==="dark"||s==="light") return s;
    return window.matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light";
  }
  function applyTheme(t){
    localStorage.setItem(TK, t);
    postToParent('theme', t);
    var T = getTranslations(localStorage.getItem(LK)||"en");
    var i = document.getElementById("hr-ti");
    var l = document.getElementById("hr-tl");
    if(i) i.innerHTML = (t===D) ? "&#9728;" : "&#9790;";
    if(l) l.textContent = (t===D) ? T.light_lbl : T.dark_lbl;
  }
  function toggleTheme(){
    applyTheme(localStorage.getItem(TK)===D ? L : D);
  }

  function detectLang(){
    var s = localStorage.getItem(LK);
    if(s==="ar"||s==="en") return s;
    return (navigator.language||"en").toLowerCase().startsWith("ar") ? "ar" : "en";
  }
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
      if(el) el.classList.toggle("active", (id==="opt-ar")===(lang==="ar"));
    });
    postToParent('apply', {lang:lang, rtl:rtl, T:T});
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
    attachParentReceiver();
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
    function closeDD(){ document.getElementById("hr-lang-dd").classList.remove("open"); document.getElementById("hr-lang-btn").setAttribute("aria-expanded","false"); }
    if(oen) oen.addEventListener("click",function(){ applyLang("en"); closeDD(); });
    if(oar) oar.addEventListener("click",function(){ applyLang("ar"); closeDD(); });
    document.addEventListener("click", closeDropdown);
  }

  document.readyState==="loading" ? document.addEventListener("DOMContentLoaded",boot) : boot();
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
    """Inject the floating controls bar.

    Single iframe approach: the controls iframe sets up the parent-window
    message listener via window.parent.addEventListener() directly from
    within the iframe's script. No second phantom iframe needed.
    """
    components.html(_UI_JS, height=56, scrolling=False)


def inject_theme_toggle() -> None:
    pass


def inject_language_switcher() -> None:
    pass
