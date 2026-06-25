"""
UI helpers: CSS injection + Dark/Light Mode toggle.
"""
from __future__ import annotations
from pathlib import Path
import streamlit as st


# JavaScript: minified theme toggle logic (ASCII-safe)
_THEME_JS = """
<script>
(function(){
  var K="hr_theme",D="dark",L="light";
  function gi(){
    var s=localStorage.getItem(K);
    if(s===D||s===L)return s;
    return window.matchMedia("(prefers-color-scheme: dark)").matches?D:L;
  }
  function ap(t){
    [document.documentElement,document.body].forEach(function(e){
      if(e)e.setAttribute("data-theme",t);
    });
    var a=document.querySelector("[data-testid=\'stApp\']");
    if(a)a.setAttribute("data-theme",t);
    localStorage.setItem(K,t);
  }
  function ui(t){
    var i=document.getElementById("hr-ti");
    var l=document.getElementById("hr-tl");
    if(i)i.textContent=(t===D)?"Sun":"Moon";
    if(l)l.textContent=(t===D)?"Light":"Dark";
  }
  function tog(){
    var c=localStorage.getItem(K)||gi();
    var n=(c===D)?L:D;
    ap(n);ui(n);
  }
  function boot(){
    var t=gi();ap(t);ui(t);
    var b=document.getElementById("hr-tt");
    if(b){
      b.addEventListener("click",tog);
      b.addEventListener("keydown",function(e){
        if(e.key==="Enter"||e.key===" "){e.preventDefault();tog();}
      });
    }
    new MutationObserver(function(){
      ap(localStorage.getItem(K)||L);
    }).observe(document.body,{childList:true,subtree:false});
  }
  if(document.readyState==="loading"){
    document.addEventListener("DOMContentLoaded",boot);
  }else{boot();}
})();
</script>
"""

# HTML: toggle button widget
_TOGGLE_HTML = """
<div class="theme-toggle-wrap">
  <button
    id="hr-tt"
    class="theme-toggle-btn"
    role="switch"
    aria-checked="false"
    aria-label="Toggle dark/light mode"
    tabindex="0"
  >
    <div class="toggle-track"><div class="toggle-knob"></div></div>
    <span id="hr-ti" class="toggle-icon">Moon</span>
    <span id="hr-tl">Dark</span>
  </button>
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
    """Inject the Dark/Light toggle button + JS. Call after inject_css()."""
    st.markdown(_TOGGLE_HTML, unsafe_allow_html=True)
    st.markdown(_THEME_JS,    unsafe_allow_html=True)
