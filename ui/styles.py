"""
UI helpers: CSS injection + Theme/Language controls via st.components.v1.html()

Architecture:
- _UI_JS: single iframe (height=56) — the visible controls bar.
  It sends postMessage() to the parent window AND sets up the parent's
  message listener from within the iframe (window.parent.addEventListener).
  This single-iframe approach avoids a phantom zero-height iframe that would
  block pointer events in the top-right corner.

Dark-mode fix:
  applyTheme() sets data-theme on the IFRAME's own document.documentElement AND
  posts to the parent. Without the local set, [data-theme="dark"] CSS rules inside
  the iframe's stylesheet never activate, leaving the controls always white.
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
  /* Area below the controls bar must not block Streamlit clicks */
  pointer-events: none !important;
}

/* Only interactive elements re-enable pointer events */
.hr-controls-bar,
.hr-controls-bar *,
.lang-dropdown,
.lang-dropdown * {
  pointer-events: auto !important;
}

/* Controls bar sits at top-left of the iframe viewport.
   The iframe itself is positioned fixed top-right by app.py CSS. */
.hr-controls-bar {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: flex-end;
}
[dir="rtl"] .hr-controls-bar { flex-direction: row-reverse; }

/* ── Shared pill button base ── */
.theme-toggle-btn,
.lang-switch-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  transition: background 0.18s, border-color 0.18s, box-shadow 0.18s, transform 0.12s;
}

/* ── Light mode pill ── */
.theme-toggle-btn,
.lang-switch-btn {
  background: #FFFFFF;
  border: 1.5px solid rgba(0, 0, 0, 0.15);
  color: #111827;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08);
}

/* ── Dark mode pill ──
   #252D3A = noticeably lighter than the page bg #0D1117 → creates visual
   separation. White border at 40% opacity ensures the pill is always visible. */
[data-theme="dark"] .theme-toggle-btn,
[data-theme="dark"] .lang-switch-btn {
  background: #252D3A;
  border: 1.5px solid rgba(255, 255, 255, 0.40);
  color: #E6EDF3;
  box-shadow: 0 1px 4px rgba(0,0,0,0.6), 0 3px 10px rgba(0,0,0,0.5);
}

/* ── Hover ── */
.theme-toggle-btn:hover,
.lang-switch-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.18);
  border-color: rgba(192,57,43,0.55);
}
[data-theme="dark"] .theme-toggle-btn:hover,
[data-theme="dark"] .lang-switch-btn:hover {
  background: #2E3849;
  border-color: rgba(255,112,96,0.65);
  box-shadow: 0 4px 16px rgba(0,0,0,0.65);
}

/* ── Active / Focus ── */
.theme-toggle-btn:active,
.lang-switch-btn:active { transform: scale(0.97); }
.theme-toggle-btn:focus-visible,
.lang-switch-btn:focus-visible {
  outline: 2px solid #C0392B;
  outline-offset: 2px;
}
[data-theme="dark"] .theme-toggle-btn:focus-visible,
[data-theme="dark"] .lang-switch-btn:focus-visible { outline-color: #FF7060; }
.toggle-icon { font-size: 14px; line-height: 1; }

/* ── Language switcher ── */
.lang-switcher-wrap { position: relative; }

.lang-chevron { font-size: 9px; opacity: 0.55; transition: transform 0.2s; margin-left: 2px; }
[data-theme="dark"] .lang-chevron { opacity: 0.7; }
.lang-switch-btn[aria-expanded="true"] .lang-chevron { transform: rotate(180deg); }

/* ── Language dropdown ── */
.lang-dropdown {
  display: none;
  position: absolute;
  top: calc(100% + 7px);
  right: 0;
  /* Wider dropdown to fit flags + language names and allow scrolling */
  min-width: 260px;
  max-height: 180px;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  background: rgba(255, 255, 255, 0.99);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.14), 0 2px 8px rgba(0, 0, 0, 0.08);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  overflow-y: auto;
  z-index: 10000;
}
[dir="rtl"] .lang-dropdown { right: auto; left: 0; }
[data-theme="dark"] .lang-dropdown {
  background: #252D3A;
  border-color: rgba(255, 255, 255, 0.28);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.7), 0 2px 8px rgba(0, 0, 0, 0.5);
}
.lang-dropdown.open {
  display: block;
  animation: dd-in 0.14s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes dd-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); }
  to   { opacity: 1; transform: none; }
}

/* ── Language options ── */
.lang-option {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 14px;
  width: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #1F2937;
  text-align: left;
  transition: background 0.12s;
}
[dir="rtl"] .lang-option { text-align: right; flex-direction: row-reverse; }
[data-theme="dark"] .lang-option { color: #E6EDF3; }
.lang-option:hover {
  background: rgba(0, 0, 0, 0.055);
}
[data-theme="dark"] .lang-option:hover {
  background: rgba(255, 255, 255, 0.09);
}
.lang-option:focus-visible {
  outline: 2px solid #C0392B;
  outline-offset: -2px;
}
[data-theme="dark"] .lang-option:focus-visible { outline-color: #FF7060; }
.lang-option.active {
  font-weight: 700;
  color: #C0392B;
  background: rgba(192, 57, 43, 0.06);
}
[data-theme="dark"] .lang-option.active {
  color: #FF7060;
  background: rgba(255, 112, 96, 0.1);
}
.lang-option-check {
  margin-left: auto;
  font-size: 11px;
  color: #C0392B;
  opacity: 0;
}
[data-theme="dark"] .lang-option-check { color: #FF7060; }
.lang-option.active .lang-option-check { opacity: 1; }
[dir="rtl"] .lang-option-check { margin-left: 0; margin-right: auto; }
.lang-flag { font-size: 16px; line-height: 1; }
.lang-name { flex: 1; }
</style>

<div class="hr-controls-bar" role="toolbar" aria-label="Theme and language controls">
  <button id="hr-tt" class="theme-toggle-btn" aria-label="Toggle dark/light theme">
    <span class="toggle-icon" id="hr-ti" aria-hidden="true">&#9790;</span>
    <span id="hr-tl">Dark</span>
  </button>
  <div class="lang-switcher-wrap">
    <button id="hr-lang-btn" class="lang-switch-btn" aria-label="Switch language" aria-haspopup="true" aria-expanded="false">
      <span class="lang-flag" id="hr-lang-flag" aria-hidden="true">&#127468;&#127463;</span>
      <span id="hr-lang-label">EN</span>
      <span class="lang-chevron" aria-hidden="true">&#9660;</span>
    </button>
    <div class="lang-dropdown" id="hr-lang-dd" role="menu" aria-label="Language selection">
      <button class="lang-option" role="menuitem" id="opt-en">
        <span class="lang-flag" aria-hidden="true">&#127468;&#127463;</span>
        <span class="lang-name">English</span>
        <span class="lang-option-check" aria-hidden="true">&#10003;</span>
      </button>
      <button class="lang-option" role="menuitem" id="opt-ar">
        <span class="lang-flag" aria-hidden="true">&#127462;&#127466;</span>
        <span class="lang-name">&#1575;&#1604;&#1593;&#1585;&#1576;&#1610;&#1577;</span>
        <span class="lang-option-check" aria-hidden="true">&#10003;</span>
      </button>
    </div>
  </div>
</div>

<script>
(function(){
  var TK = "hr_theme", LK = "hr_ui_lang", D = "dark", L = "light";

  /* ── Post message to parent Streamlit window ── */
  function postToParent(type, payload){
    try { window.parent.postMessage({type:'hr_'+type, payload:payload}, '*'); } catch(e){}
  }

  /* ── Attach receiver on the PARENT window ─────────────────────────────────
     Runs from inside this iframe so it can cross the iframe boundary.
     Sets data-theme / lang / dir on the parent document, translates data-i18n
     elements, and keeps the chat input placeholder in sync.
  ── */
  function attachParentReceiver(){
    try {
      if(window.parent.__hrListenerSet) return;
      window.parent.__hrListenerSet = true;
      var p = window.parent.document;

      window.parent.addEventListener('message', function(e){
        var d = e.data;
        if(!d || typeof d.type !== 'string' || !d.type.startsWith('hr_')) return;

        if(d.type === 'hr_theme'){
          var th = d.payload;
          [p.documentElement, p.body].forEach(function(el){
            if(el) el.setAttribute('data-theme', th);
          });
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
            if(T[k] !== undefined){
              if(el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'){
                el.placeholder = T[k];
              } else {
                el.textContent = T[k];
              }
            }
          });
          var inp = p.querySelector('[data-testid="stChatInputTextArea"], textarea');
          if(inp && T.placeholder) inp.placeholder = T.placeholder;
        }
      });

      /* Close dropdown when user clicks anywhere on the parent (Streamlit) page */
      p.addEventListener('click', function(){ _closeDD(); });

      /* BUG 2 FIX: MutationObserver re-stamps data-theme after Streamlit reruns.
         Streamlit's React reconciler can strip custom DOM attributes when it
         re-renders the component tree. The observer catches childList mutations
         on the parent body and restores the theme from localStorage. */
      if(window.MutationObserver && p.body){
        var _themeObserver = new MutationObserver(function(){
          var saved = localStorage.getItem(TK) || L;
          if(p.documentElement.getAttribute('data-theme') !== saved){
            p.documentElement.setAttribute('data-theme', saved);
            if(p.body) p.body.setAttribute('data-theme', saved);
            var stApp = p.querySelector('[data-testid="stApp"]');
            if(stApp) stApp.setAttribute('data-theme', saved);
          }
        });
        _themeObserver.observe(p.body, { childList: true, subtree: false });
      }
    } catch(ex){}
  }

  /* ── i18n strings ── */
  var TRANS = {
    en:{
      app_title:"HR Policy Assistant",
      app_subtitle:"Ask about any policy in seconds — instead of browsing for hours",
      stat_ml_t:"Multilingual",stat_ml_d:"Arabic & English",
      stat_ins_t:"Instant Answers",stat_ins_d:"Under a second",
      stat_sec_t:"Private & Secure",stat_sec_d:"Your data is safe",
      src_label:"SELECT KNOWLEDGE SOURCE",
      src_co_t:"Company Policy",
      src_co_d:"Answers based on your organization's internal HR policies.",
      src_dxb_t:"Dubai HR Policy",
      src_dxb_d:"Answers based on Dubai labor regulations and UAE HR policies.",
      active_pfx:"Active:",
      dark_lbl:"Dark",light_lbl:"Light",
      placeholder:"Type your question..."
    },
    ar:{
      app_title:"المساعد المعرفي للموارد البشرية",
      app_subtitle:"اسأل عن أي سياسة في ثوانٍ — بدلاً من التصفح لساعات",
      stat_ml_t:"متعدد اللغات",stat_ml_d:"عربي وإنجليزي",
      stat_ins_t:"إجابات فورية",stat_ins_d:"بأقل من ثانية",
      stat_sec_t:"آمن وخاص",stat_sec_d:"بياناتك محمية",
      src_label:"اختر مصدر المعرفة",
      src_co_t:"سياسة الشركة",
      src_co_d:"إجابات مبنية على السياسات الداخلية.",
      src_dxb_t:"سياسة دبي HR",
      src_dxb_d:"إجابات مبنية على قوانين العمل.",
      active_pfx:"المصدر:",
      dark_lbl:"داكن",light_lbl:"فاتح",
      placeholder:"اكتب سؤالك..."
    }
  };
  function getTranslations(lang){ return TRANS[lang] || TRANS.en; }

  /* ── Theme ───────────────────────────────────────────────────────────────── */
  function getTheme(){
    var s = localStorage.getItem(TK);
    if(s === D || s === L) return s;
    return window.matchMedia("(prefers-color-scheme:dark)").matches ? D : L;
  }

  function applyTheme(t){
    localStorage.setItem(TK, t);

    /* CRITICAL FIX: set data-theme on the IFRAME's own document so
       [data-theme="dark"] CSS rules inside this iframe's stylesheet activate. */
    document.documentElement.setAttribute('data-theme', t);
    document.body.setAttribute('data-theme', t);

    /* Tell the parent page to update its own data-theme */
    postToParent('theme', t);

    /* Update the button icon and label */
    var T = getTranslations(localStorage.getItem(LK) || "en");
    var i = document.getElementById("hr-ti");
    var l = document.getElementById("hr-tl");
    if(i) i.innerHTML = (t === D) ? "&#9728;" : "&#9790;";
    if(l) l.textContent = (t === D) ? T.light_lbl : T.dark_lbl;
  }

  function toggleTheme(){
    applyTheme(localStorage.getItem(TK) === D ? L : D);
  }

  /* ── Language ────────────────────────────────────────────────────────────── */
  function detectLang(){
    var s = localStorage.getItem(LK);
    if(s === "ar" || s === "en") return s;
    return (navigator.language || "en").toLowerCase().startsWith("ar") ? "ar" : "en";
  }

  function applyLang(lang){
    var T = getTranslations(lang);
    var rtl = (lang === "ar");
    localStorage.setItem(LK, lang);
    postToParent('lang', {lang:lang, rtl:rtl});

    var flag = document.getElementById("hr-lang-flag");
    var lbl  = document.getElementById("hr-lang-label");
    if(flag) flag.innerHTML = (lang === "ar") ? "&#127462;&#127466;" : "&#127468;&#127463;";
    if(lbl)  lbl.textContent = (lang === "ar") ? "AR" : "EN";

    /* Mark active option and set aria state */
    ["opt-en", "opt-ar"].forEach(function(id){
      var el = document.getElementById(id);
      if(el) el.classList.toggle("active", (id === "opt-ar") === (lang === "ar"));
    });

    /* Also apply RTL to the iframe itself */
    document.documentElement.setAttribute('dir', rtl ? 'rtl' : 'ltr');
    document.body.setAttribute('dir', rtl ? 'rtl' : 'ltr');

    postToParent('apply', {lang:lang, rtl:rtl, T:T});
  }

  /* ── Dropdown ────────────────────────────────────────────────────────────── */
  /* NOTE: No iframe resizing needed. The iframe is always 150px tall (set in
     app.py CSS). The 94px below the button bar has pointer-events:none (body
     CSS above) so it never blocks Streamlit. The dropdown renders within that
     space without clipping. */

  function _closeDD(){
    var dd  = document.getElementById("hr-lang-dd");
    var btn = document.getElementById("hr-lang-btn");
    if(dd)  dd.classList.remove("open");
    if(btn) btn.setAttribute("aria-expanded", "false");
  }

  function toggleDropdown(){
    var dd  = document.getElementById("hr-lang-dd");
    var btn = document.getElementById("hr-lang-btn");
    if(!dd || !btn) return;
    var isOpen = dd.classList.toggle("open");
    btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    if(isOpen){
      var first = dd.querySelector(".lang-option");
      if(first) setTimeout(function(){ first.focus(); }, 50);
    }
  }

  function closeDropdown(e){
    var wrap = document.querySelector(".lang-switcher-wrap");
    if(wrap && !wrap.contains(e.target)) _closeDD();
  }

  /* ── Boot ────────────────────────────────────────────────────────────────── */
  function boot(){
    /* Eagerly stamp data-theme on this iframe BEFORE postMessage round-trip
       to prevent a flash of wrong-theme controls on load. */
    var initTheme = getTheme();
    document.documentElement.setAttribute('data-theme', initTheme);
    document.body.setAttribute('data-theme', initTheme);

    attachParentReceiver();
    applyTheme(initTheme);
    applyLang(detectLang());

    /* Theme toggle */
    var tt = document.getElementById("hr-tt");
    if(tt){
      tt.addEventListener("click", toggleTheme);
      tt.addEventListener("keydown", function(e){
        if(e.key === "Enter" || e.key === " "){ e.preventDefault(); toggleTheme(); }
      });
    }

    /* Language dropdown toggle */
    var lb = document.getElementById("hr-lang-btn");
    if(lb){
      lb.addEventListener("click", toggleDropdown);
      lb.addEventListener("keydown", function(e){
        if(e.key === "Enter" || e.key === " "){ e.preventDefault(); toggleDropdown(); }
        if(e.key === "Escape"){ closeDropdown({target: document.body}); }
      });
    }

    /* Language options */
    var oen = document.getElementById("opt-en");
    var oar = document.getElementById("opt-ar");
    if(oen) oen.addEventListener("click", function(){ applyLang("en"); _closeDD(); });
    if(oar) oar.addEventListener("click", function(){ applyLang("ar"); _closeDD(); });

    /* Keyboard nav within dropdown */
    var dd = document.getElementById("hr-lang-dd");
    if(dd){
      dd.addEventListener("keydown", function(e){
        if(e.key === "Escape"){ _closeDD(); lb && lb.focus(); }
        if(e.key === "ArrowDown" || e.key === "ArrowUp"){
          e.preventDefault();
          var opts = Array.from(dd.querySelectorAll(".lang-option"));
          var idx = opts.indexOf(document.activeElement);
          var next = e.key === "ArrowDown" ? Math.min(idx+1, opts.length-1) : Math.max(idx-1, 0);
          opts[next] && opts[next].focus();
        }
      });
    }

    /* Close on outside click */
    document.addEventListener("click", closeDropdown);
  }

  document.readyState === "loading"
    ? document.addEventListener("DOMContentLoaded", boot)
    : boot();
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
    """Inject the floating controls bar (single iframe).

    The controls iframe sets up the parent-window message listener via
    window.parent.addEventListener() directly from within the iframe's script.
    It also stamps data-theme on its OWN document so the iframe-internal CSS
    dark-mode rules activate immediately — no second iframe needed.
    """
    # 150px = 56px button bar + 94px dropdown space.
    # The 94px below the bar is transparent & pointer-events:none (set in CSS above)
    # so it never visually covers or blocks Streamlit content.
    components.html(_UI_JS, height=150, scrolling=False)


def inject_theme_toggle() -> None:
    pass


def inject_language_switcher() -> None:
    pass
