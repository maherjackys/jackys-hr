"""
UI helpers: CSS injection + Theme/Language controls via st.components.v1.html()
Using components.html() ensures <script> tags always execute properly in Streamlit.
"""
from __future__ import annotations
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components


# ── JS payload: Theme toggle + i18n (AR/EN + RTL/LTR) ───────────────────────
_UI_JS = """
<style>
/* ── UI Controls floating bar ── */
.hr-controls-bar {
  position: fixed;
  top: 14px;
  right: 18px;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 10px;
}
[dir="rtl"] .hr-controls-bar { right: auto; left: 18px; }

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
.lang-dropdown.open + * .lang-chevron,
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
  /* ── post message to parent Streamlit window ── */
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
    en:{app_title:"HR Policy Assistant",app_subtitle:"Ask about any policy in seconds \u2014 instead of browsing for hours",stat_ml_t:"Multilingual",stat_ml_d:"Arabic & English",stat_ins_t:"Instant Answers",stat_ins_d:"Under a second",stat_sec_t:"Private & Secure",stat_sec_d:"Your data is safe",src_label:"SELECT KNOWLEDGE SOURCE",src_co_t:"Company Policy",src_co_d:"Answers based on your organization's internal HR policies.",src_dxb_t:"Dubai HR Policy",src_dxb_d:"Answers based on Dubai labor regulations and UAE HR policies.",active_pfx:"Active:",dark_lbl:"Dark",light_lbl:"Light",placeholder:"Type your question..."},
    ar:{app_title:"\u0627\u0644\u0645\u0633\u0627\u0639\u062f \u0627\u0644\u0645\u0639\u0631\u0641\u064a \u0644\u0644\u0645\u0648\u0627\u0631\u062f \u0627\u0644\u0628\u0634\u0631\u064a\u0629",app_subtitle:"\u0627\u0633\u0623\u0644 \u0639\u0646 \u0623\u064a \u0633\u064a\u0627\u0633\u0629 \u0641\u064a \u062b\u0648\u0627\u0646\u064d \u2014 \u0628\u062f\u0644\u0627\u064b \u0645\u0646 \u0627\u0644\u062a\u0635\u0641\u062d \u0644\u0633\u0627\u0639\u0627\u062a",stat_ml_t:"\u0645\u062a\u0639\u062f\u062f \u0627\u0644\u0644\u063a\u0627\u062a",stat_ml_d:"\u0639\u0631\u0628\u064a \u0648\u0625\u0646\u062c\u0644\u064a\u0632\u064a",stat_ins_t:"\u0625\u062c\u0627\u0628\u0627\u062a \u0641\u0648\u0631\u064a\u0629",stat_ins_d:"\u0628\u0623\u0642\u0644 \u0645\u0646 \u062b\u0627\u0646\u064a\u0629",stat_sec_t:"\u0622\u0645\u0646 \u0648\u062e\u0627\u0635",stat_sec_d:"\u0628\u064a\u0627\u0646\u0627\u062a\u0643 \u0645\u062d\u0645\u064a\u0629",src_label:"\u0627\u062e\u062a\u0631 \u0645\u0635\u062f\u0631 \u0627\u0644\u0645\u0639\u0631\u0641\u0629",src_co_t:"\u0633\u064a\u0627\u0633\u0629 \u0627\u0644\u0634\u0631\u0643\u0629",src_co_d:"\u0625\u062c\u0627\u0628\u0627\u062a \u0645\u0628\u0646\u064a\u0629 \u0639\u0644\u0649 \u0627\u0644\u0633\u064a\u0627\u0633\u0627\u062a \u0627\u0644\u062f\u0627\u062e\u0644\u064a\u0629.",src_dxb_t:"\u0633\u064a\u0627\u0633\u0629 \u062f\u0628\u064a HR",src_dxb_d:"\u0625\u062c\u0627\u0628\u0627\u062a \u0645\u0628\u0646\u064a\u0629 \u0639\u0644\u0649 \u0642\u0648\u0627\u0646\u064a\u0646 \u0627\u0644\u0639\u0645\u0644.",active_pfx:"\u0627\u0644\u0645\u0635\u062f\u0631:",dark_lbl:"\u062f\u0627\u0643\u0646",light_lbl:"\u0641\u0627\u062a\u062d",placeholder:"\u0627\u0643\u062a\u0628 \u0633\u0624\u0627\u0644\u0643..."}
  };
  function getTranslations(lang){ return TRANS[lang]||TRANS.en; }

  function applyLang(lang){
    var T = getTranslations(lang);
    var rtl = (lang==="ar");
    localStorage.setItem(LK, lang);
    postToParent('lang', {lang:lang, rtl:rtl});

    /* flag + label in this iframe */
    var flag = document.getElementById("hr-lang-flag");
    var lbl  = document.getElementById("hr-lang-label");
    if(flag) flag.innerHTML = (lang==="ar") ? "&#127462;&#127466;" : "&#127468;&#127463;";
    if(lbl)  lbl.textContent = (lang==="ar") ? "AR" : "EN";

    /* active class on options */
    ["opt-en","opt-ar"].forEach(function(id){
      var el = document.getElementById(id);
      if(el) el.classList.toggle("active", (id==="opt-ar") === (lang==="ar"));
    });

    /* send full translations + rtl to parent for DOM update */
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

  /* ── Boot ── */
  function boot(){
    var theme = getTheme();
    applyTheme(theme);

    var lang = detectLang();
    applyLang(lang);

    /* Event listeners */
    var tt = document.getElementById("hr-tt");
    if(tt){ tt.addEventListener("click", toggleTheme); tt.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();toggleTheme();}}); }

    var lb = document.getElementById("hr-lang-btn");
    if(lb){ lb.addEventListener("click", toggleDropdown); lb.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();toggleDropdown();}}); }

    var oen = document.getElementById("opt-en");
    var oar = document.getElementById("opt-ar");
    if(oen) oen.addEventListener("click",function(){ applyLang("en"); document.getElementById("hr-lang-dd").classList.remove("open"); document.getElementById("hr-lang-btn").setAttribute("aria-expanded","false"); });
    if(oar) oar.addEventListener("click",function(){ applyLang("ar"); document.getElementById("hr-lang-dd").classList.remove("open"); document.getElementById("hr-lang-btn").setAttribute("aria-expanded","false"); });

    document.addEventListener("click", closeDropdown);
  }

  document.readyState==="loading" ? document.addEventListener("DOMContentLoaded",boot) : boot();
})();
</script>
""".strip()

_PARENT_RECEIVER_JS = """
<script>
(function(){
  /* Listen for messages from the controls iframe */
  if(window.__hrListenerSet) return;
  window.__hrListenerSet = true;

  window.addEventListener('message', function(e){
    var d = e.data;
    if(!d||typeof d.type!=='string'||!d.type.startsWith('hr_')) return;

    if(d.type==='hr_theme'){
      var theme = d.payload;
      [document.documentElement, document.body].forEach(function(el){ if(el) el.setAttribute('data-theme', theme); });
      var app = document.querySelector('[data-testid="stApp"]');
      if(app) app.setAttribute('data-theme', theme);
    }

    if(d.type==='hr_apply'){
      var lang = d.payload.lang, rtl = d.payload.rtl, T = d.payload.T;

      /* dir + lang on root elements */
      document.documentElement.setAttribute('lang', lang);
      document.documentElement.setAttribute('dir', rtl?'rtl':'ltr');
      document.body.setAttribute('dir', rtl?'rtl':'ltr');
      var app2 = document.querySelector('[data-testid="stApp"]');
      if(app2){ app2.setAttribute('dir', rtl?'rtl':'ltr'); app2.setAttribute('lang', lang); }

      /* translate all [data-i18n] elements */
      document.querySelectorAll('[data-i18n]').forEach(function(el){
        var k = el.getAttribute('data-i18n');
        if(T[k]!==undefined){
          if(el.tagName==='INPUT'||el.tagName==='TEXTAREA'){ el.placeholder=T[k]; }
          else { el.textContent=T[k]; }
        }
      });

      /* update chat input placeholder */
      var inp = document.querySelector('[data-testid="stChatInputTextArea"], textarea');
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
        return
    # Also inject the parent-side message receiver
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)



def inject_ui_controls() -> None:
    """Inject the floating Dark/Light toggle + Language Switcher.
    Uses st.components.v1.html() so the <script> always executes."""
    components.html(_UI_JS + _PARENT_RECEIVER_JS, height=56, scrolling=False)


# ── Kept for backwards compat (no-ops) ───────────────────────────────────────
def inject_theme_toggle() -> None:
    pass


def inject_language_switcher() -> None:
    pass
