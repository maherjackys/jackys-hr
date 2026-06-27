"""
UI helpers: CSS injection + Theme/Language controls via st.components.v1.html()

Language toggle: single-click button cycles EN ↔ AR (no dropdown = no clipping).
Theme toggle: single-click cycles Dark ↔ Light.
Both store preference in localStorage and post to parent Streamlit window.
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
  pointer-events: none !important;
}

.hr-controls-bar,
.hr-controls-bar * {
  pointer-events: auto !important;
}

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
  background: #FFFFFF;
  border: 1.5px solid rgba(0, 0, 0, 0.15);
  color: #111827;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08);
}

[data-theme="dark"] .theme-toggle-btn,
[data-theme="dark"] .lang-switch-btn {
  background: #252D3A;
  border: 1.5px solid rgba(255, 255, 255, 0.40);
  color: #E6EDF3;
  box-shadow: 0 1px 4px rgba(0,0,0,0.6), 0 3px 10px rgba(0,0,0,0.5);
}

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
.lang-flag   { font-size: 16px; line-height: 1; }
</style>

<div class="hr-controls-bar" role="toolbar" aria-label="Theme and language controls">
  <button id="hr-tt" class="theme-toggle-btn" aria-label="Toggle dark/light theme">
    <span class="toggle-icon" id="hr-ti" aria-hidden="true">&#9790;</span>
    <span id="hr-tl">Dark</span>
  </button>
  <button id="hr-lang-btn" class="lang-switch-btn" aria-label="Switch language — click to toggle">
    <span class="lang-flag" id="hr-lang-flag" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="15" viewBox="0 0 60 40" style="border-radius:2px;display:inline-block;vertical-align:middle"><rect width="60" height="40" fill="#012169"/><path d="M0,0 L60,40 M60,0 L0,40" stroke="#fff" stroke-width="8"/><path d="M0,0 L60,40 M60,0 L0,40" stroke="#C8102E" stroke-width="4"/><rect x="24" width="12" height="40" fill="#fff"/><rect y="14" width="60" height="12" fill="#fff"/><rect x="26" width="8" height="40" fill="#C8102E"/><rect y="16" width="60" height="8" fill="#C8102E"/></svg></span>
    <span id="hr-lang-label">EN</span>
  </button>
</div>

<script>
(function(){
  var TK = "hr_theme", LK = "hr_ui_lang", D = "dark", L = "light";

  function postToParent(type, payload){
    try { window.parent.postMessage({type:'hr_'+type, payload:payload}, '*'); } catch(e){}
  }

  /* ── Attach listener on the parent Streamlit window ── */
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
          if(app2){
            app2.setAttribute('dir',  rtl ? 'rtl' : 'ltr');
            app2.setAttribute('lang', lang);
          }
          translateI18n(T);
          var inp = p.querySelector('[data-testid="stChatInputTextArea"], textarea');
          if(inp && T.placeholder) inp.placeholder = T.placeholder;
          translateButtons(rtl);
        }
      });

      /* ── Bilingual suggestion button texts ──────────────────────────── */
      var _S_EN_AR = {
        "What is the annual leave policy?":           "ما هي سياسة الإجازة السنوية؟",
        "What are the working hours?":                "ما هي ساعات العمل؟",
        "What is the expense claim process?":         "ما هي إجراءات المطالبة بالمصاريف؟",
        "What is the notice period for resignation?": "ما هي مدة الإشعار عند الاستقالة؟",
        "What are maternity leave entitlements?":     "ما هي مستحقات إجازة الأمومة؟"
      };
      var _S_AR_EN = {};
      Object.keys(_S_EN_AR).forEach(function(en){ _S_AR_EN[_S_EN_AR[en]] = en; });
      _S_AR_EN["ما هي ساعات العمل في الإمارات؟"] = "What are the working hours in the UAE?";

      /* Translate Streamlit Python-rendered buttons — only changes DOM when needed */
      function translateButtons(rtl){
        p.querySelectorAll('button').forEach(function(btn){
          var node = btn.querySelector('p') || btn;
          var txt  = node.textContent.trim();
          var next = null;
          if(rtl){
            if(txt === 'Select')         next = 'اختر';
            else if(txt === '✓ Active') next = '✓ نشط';
            else if(_S_EN_AR[txt])      next = _S_EN_AR[txt];
          } else {
            if(txt === 'اختر')          next = 'Select';
            else if(txt === '✓ نشط')   next = '✓ Active';
            else if(_S_AR_EN[txt])      next = _S_AR_EN[txt];
          }
          if(next && node.textContent !== next) node.textContent = next;
        });
      }

      /* Translate [data-i18n] elements — only changes DOM when needed */
      function translateI18n(T){
        p.querySelectorAll('[data-i18n]').forEach(function(el){
          var k = el.getAttribute('data-i18n');
          if(T[k] !== undefined && el.textContent !== T[k]){
            if(el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'){
              el.placeholder = T[k];
            } else {
              el.textContent = T[k];
            }
          }
        });
      }

      /* Source card click delegation — data-cr set ONLY after button is found */
      function setupCardDelegation(){
        p.querySelectorAll('.source-card').forEach(function(card){
          if(card.hasAttribute('data-cr')) return;

          var btn = null;
          var selectors = [
            '[data-testid="stColumn"]',
            '[data-testid="stVerticalBlockBorderWrapper"]',
            '[data-testid="stVerticalBlock"]'
          ];
          for(var si = 0; si < selectors.length && !btn; si++){
            var container = card.closest(selectors[si]);
            if(!container) continue;
            var found = Array.from(container.querySelectorAll('button'));
            btn = found.find(function(b){ return !card.contains(b); }) || null;
          }
          if(!btn) return; /* button not yet rendered — try again on next mutation */

          card.setAttribute('data-cr', '1');
          card.setAttribute('role', 'button');
          card.setAttribute('tabindex', '0');
          var titleEl = card.querySelector('.source-card-title');
          if(titleEl) card.setAttribute('aria-label', titleEl.textContent.trim());
          card.style.cursor = 'pointer';
          card.addEventListener('click', function(e){
            if(!e.target.closest('button')) btn.click();
          });
          card.addEventListener('keydown', function(e){
            if(e.key==='Enter'||e.key===' '){ e.preventDefault(); btn.click(); }
          });
        });
      }
      setupCardDelegation();

      var _cardTimer;
      var _cardObs = new MutationObserver(function(){
        clearTimeout(_cardTimer);
        _cardTimer = setTimeout(function(){
          setupCardDelegation();
          var savedLang = localStorage.getItem(LK);
          if(savedLang){
            var rtl = savedLang === 'ar';
            var T   = getTranslations(savedLang);
            translateButtons(rtl);
            translateI18n(T);
          }
        }, 250);
      });
      _cardObs.observe(p.body, { childList: true, subtree: true });

      /* Re-stamp data-theme after Streamlit rerenders wipe it */
      if(window.MutationObserver && p.body){
        var _themeObs = new MutationObserver(function(){
          var saved = localStorage.getItem(TK) || L;
          if(p.documentElement.getAttribute('data-theme') !== saved){
            p.documentElement.setAttribute('data-theme', saved);
            if(p.body) p.body.setAttribute('data-theme', saved);
            var stApp = p.querySelector('[data-testid="stApp"]');
            if(stApp) stApp.setAttribute('data-theme', saved);
          }
        });
        _themeObs.observe(p.body, { childList: true, subtree: false });
      }
    } catch(ex){}
  }

  /* ── Flag SVG helper — avoids flag-emoji rendering as "AE"/"GB" on Windows ── */
  function flagSVG(lang){
    if(lang==='ar'){
      return '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="15" viewBox="0 0 6 4" style="border-radius:2px;display:inline-block;vertical-align:middle"><rect width="2" height="4" fill="#CE1126"/><rect x="2" width="4" height="1.33" fill="#00732F"/><rect x="2" y="1.33" width="4" height="1.34" fill="#fff"/><rect x="2" y="2.67" width="4" height="1.33" fill="#000"/></svg>';
    }
    return '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="15" viewBox="0 0 60 40" style="border-radius:2px;display:inline-block;vertical-align:middle"><rect width="60" height="40" fill="#012169"/><path d="M0,0 L60,40 M60,0 L0,40" stroke="#fff" stroke-width="8"/><path d="M0,0 L60,40 M60,0 L0,40" stroke="#C8102E" stroke-width="4"/><rect x="24" width="12" height="40" fill="#fff"/><rect y="14" width="60" height="12" fill="#fff"/><rect x="26" width="8" height="40" fill="#C8102E"/><rect y="16" width="60" height="8" fill="#C8102E"/></svg>';
  }

  /* ── i18n strings ── */
  var TRANS = {
    en:{
      app_title:"HR Policy Assistant",
      app_subtitle:"Ask about any policy in seconds — instead of browsing for hours",
      stat_ml_t:"Multilingual",   stat_ml_d:"Arabic & English",
      stat_ins_t:"Instant Answers", stat_ins_d:"Under a second",
      stat_sec_t:"Private & Secure", stat_sec_d:"Your data is safe",
      src_label:"SELECT KNOWLEDGE SOURCE",
      src_co_t:"Company Policy",
      src_co_d:"Answers based on your organization's internal HR policies.",
      src_dxb_t:"Dubai HR Policy",
      src_dxb_d:"Answers based on Dubai labor regulations and UAE HR policies.",
      active_pfx:"Active:",
      try_asking:"Try asking:",
      dark_lbl:"Dark", light_lbl:"Light",
      placeholder:"Type your question..."
    },
    ar:{
      app_title:"المساعد المعرفي للموارد البشرية",
      app_subtitle:"اسأل عن أي سياسة في ثوانٍ — بدلاً من التصفح لساعات",
      stat_ml_t:"متعدد اللغات",   stat_ml_d:"عربي وإنجليزي",
      stat_ins_t:"إجابات فورية", stat_ins_d:"بأقل من ثانية",
      stat_sec_t:"آمن وخاص",  stat_sec_d:"بياناتك محمية",
      src_label:"اختر مصدر المعرفة",
      src_co_t:"سياسة الشركة",
      src_co_d:"إجابات مبنية على السياسات الداخلية.",
      src_dxb_t:"سياسة دبي HR",
      src_dxb_d:"إجابات مبنية على قوانين العمل.",
      active_pfx:"المصدر:",
      try_asking:"جرب أن تسأل:",
      dark_lbl:"داكن", light_lbl:"فاتح",
      placeholder:"اكتب سؤالك..."
    }
  };
  function getTranslations(lang){ return TRANS[lang] || TRANS.en; }

  /* ── Theme ── */
  function getTheme(){
    var s = localStorage.getItem(TK);
    if(s === D || s === L) return s;
    return window.matchMedia("(prefers-color-scheme:dark)").matches ? D : L;
  }

  function applyTheme(t){
    localStorage.setItem(TK, t);
    document.documentElement.setAttribute('data-theme', t);
    document.body.setAttribute('data-theme', t);
    postToParent('theme', t);
    var T = getTranslations(localStorage.getItem(LK) || "en");
    var i = document.getElementById("hr-ti");
    var l = document.getElementById("hr-tl");
    if(i) i.innerHTML = (t === D) ? "&#9728;" : "&#9790;";
    if(l) l.textContent = (t === D) ? T.light_lbl : T.dark_lbl;
  }

  function toggleTheme(){
    applyTheme(localStorage.getItem(TK) === D ? L : D);
  }

  /* ── Language ── */
  function detectLang(){
    var s = localStorage.getItem(LK);
    if(s === "ar" || s === "en") return s;
    return (navigator.language || "en").toLowerCase().startsWith("ar") ? "ar" : "en";
  }

  function applyLang(lang){
    var T   = getTranslations(lang);
    var rtl = (lang === "ar");
    localStorage.setItem(LK, lang);
    postToParent('lang', {lang:lang, rtl:rtl});

    var flag = document.getElementById("hr-lang-flag");
    var lbl  = document.getElementById("hr-lang-label");
    if(flag) flag.innerHTML = flagSVG(lang);
    if(lbl)  lbl.textContent = (lang === "ar") ? "AR" : "EN";

    document.documentElement.setAttribute('dir', rtl ? 'rtl' : 'ltr');
    document.body.setAttribute('dir', rtl ? 'rtl' : 'ltr');
    postToParent('apply', {lang:lang, rtl:rtl, T:T});
  }

  /* ── Boot ── */
  function boot(){
    var initTheme = getTheme();
    document.documentElement.setAttribute('data-theme', initTheme);
    document.body.setAttribute('data-theme', initTheme);

    attachParentReceiver();

    /* Self-position this iframe via frameElement (targets only this iframe) */
    try {
      var _fe = window.frameElement;
      if(_fe && !window.parent.__hrFESet){
        window.parent.__hrFESet = true;
        var _s = {position:'fixed',top:'0',left:'0',width:'100vw',height:'70px',
                  'z-index':'9999999','pointer-events':'none',
                  border:'none',background:'transparent',overflow:'visible'};
        Object.keys(_s).forEach(function(k){
          _fe.style.setProperty(k, _s[k], 'important');
        });
        /* Enable clicks only when cursor is in the controls zone (top 65px) */
        window.parent.document.addEventListener('mousemove', function(e){
          _fe.style.setProperty(
            'pointer-events', e.clientY < 65 ? 'auto' : 'none', 'important'
          );
        }, { passive: true });
      }
    } catch(_ex){}

    applyTheme(initTheme);
    applyLang(detectLang());

    /* Theme button */
    var tt = document.getElementById("hr-tt");
    if(tt){
      tt.addEventListener("click", toggleTheme);
      tt.addEventListener("keydown", function(e){
        if(e.key === "Enter" || e.key === " "){ e.preventDefault(); toggleTheme(); }
      });
    }

    /* Language button — single click toggles EN ↔ AR (no dropdown needed) */
    var lb = document.getElementById("hr-lang-btn");
    if(lb){
      lb.addEventListener("click", function(){
        applyLang(localStorage.getItem(LK) === 'ar' ? 'en' : 'ar');
      });
      lb.addEventListener("keydown", function(e){
        if(e.key === "Enter" || e.key === " "){ e.preventDefault(); lb.click(); }
      });
    }
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
    """Inject the floating controls bar (single iframe, no dropdown)."""
    components.html(_UI_JS, height=70, scrolling=False)
