"""
UI helpers: CSS + Dark/Light Mode toggle.
"""
from __future__ import annotations
from pathlib import Path
import streamlit as st

_JS = """<script>
(function(){
  var K="hr_theme",D="dark",L="light";
  function gi(){var s=localStorage.getItem(K);if(s===D||s===L)return s;return window.matchMedia("(prefers-color-scheme: dark)").matches?D:L;}
  function ap(t){[document.documentElement,document.body].forEach(function(e){if(e)e.setAttribute("data-theme",t);});var a=document.querySelector("[data-testid='stApp']");if(a)a.setAttribute("data-theme",t);localStorage.setItem(K,t);}
  function ui(t){var i=document.getElementById("hr-ti"),l=document.getElementById("hr-tl");if(i)i.textContent=t===D?"\u2600\uFE0F":"\uD83C\uDF19";if(l)l.textContent=t===D?"Light":"Dark";}
  function tog(){var c=localStorage.getItem(K)||gi(),n=c===D?L:D;ap(n);ui(n);}
  function boot(){var t=gi();ap(t);ui(t);var b=document.getElementById("hr-tt");if(b){b.addEventListener("click",tog);b.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();tog();}});}new MutationObserver(function(){ap(localStorage.getItem(K)||L);}).observe(document.body,{childList:true,subtree:false});}
  document.readyState==="loading"?document.addEventListener("DOMContentLoaded",boot):boot();
})();
</script>"""

_HTML = """<div class="theme-toggle-wrap"><button id="hr-tt" class="theme-toggle-btn" role="switch" aria-checked="false" aria-label="Toggle dark/light mode" tabindex="0"><div class="toggle-track"><div class="toggle-knob"></div></div><span id="hr-ti" class="toggle-icon">&#x1F319;</span><span id="hr-tl">Dark</span></button></div>"""


def inject_css(css_path: Path) -> None:
    try:
        css = css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def inject_theme_toggle() -> None:
    st.markdown(_HTML, unsafe_allow_html=True)
    st.markdown(_JS,   unsafe_allow_html=True)
