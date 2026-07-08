"""UI helpers: CSS injection + Dark/Light mode."""
from __future__ import annotations
from pathlib import Path
import streamlit as st

_DARK_CSS = """
<style>
/* ── Dark mode: CSS variable overrides ── */
:root {
  --bg-app:               #0D1117;
  --bg-app-rgb:           13,17,23;
  --bg-surface:           #161B22;
  --bg-surface-2:         #1C2128;
  --bg-surface-hover:     #21262D;
  --bg-chat-user:         #2D1B18;
  --bg-chat-bot:          #161B22;
  --bg-card:              #161B22;
  --bg-card-hover:        #1C2128;
  --bg-card-selected:     #2D1B18;
  --bg-input:             #1C2128;
  --bg-badge:             #2D1B18;
  --text-primary:         #E6EDF3;
  --text-secondary:       #8B949E;
  --text-muted:           #7D8590;
  --text-inverse:         #0D1117;
  --text-brand:           #FF7060;
  --border-default:       #30363D;
  --border-subtle:        #21262D;
  --border-focus:         #FF7060;
  --border-card:          #30363D;
  --border-card-selected: #FF7060;
  --border-input:         #484F58;
  --shadow-xs:            0 1px 3px rgba(0,0,0,0.3);
  --shadow-sm:            0 2px 8px rgba(0,0,0,0.4);
  --shadow-md:            0 4px 20px rgba(0,0,0,0.5);
  --shadow-lg:            0 12px 40px rgba(0,0,0,0.65);
  --shadow-focus:         0 0 0 3px rgba(231,76,60,0.25);
  --shadow-card-hover:    0 8px 28px rgba(0,0,0,0.55);
  --scrollbar-track:      #161B22;
  --scrollbar-thumb:      #30363D;
  --scrollbar-thumb-hover:#484F58;
  --color-dubai:          #4DD687;
  --color-dubai-border:   rgba(77,214,135,0.35);
  --bg-dubai-badge:       rgba(77,214,135,0.1);
  --border-chat-user:     rgba(255,112,96,0.22);
}

/* ── App & page background ── */
[data-testid="stApp"],
[data-testid="stMain"],
.main, section.main, .block-container,
[data-testid="stAppViewContainer"] {
  background-color: #0D1117 !important;
  color: #E6EDF3 !important;
}

/* ── Fixed header dark background ── */
.hr-header {
  background: rgba(13,17,23,0.95) !important;
  border-bottom-color: #21262D !important;
  box-shadow: 0 2px 20px rgba(0,0,0,0.35) !important;
}

/* ── Chat bubbles — explicit overrides (Streamlit injects its own bg) ── */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  background: #2D1B18 !important;
  border-color: rgba(255,112,96,0.22) !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
  background: #161B22 !important;
  border-color: #30363D !important;
}
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] strong {
  color: #E6EDF3 !important;
  -webkit-text-fill-color: #E6EDF3 !important;
}
[data-testid="stChatMessage"] code {
  background: #1C2128 !important;
  color: #FF7060 !important;
}
[data-testid="chatAvatarIcon-assistant"] {
  background: linear-gradient(135deg,#21262D,#30363D) !important;
  border-color: #30363D !important;
}

/* ── Chat input outer container — aggressive override ── */
[data-testid="stBottom"],
[data-testid="stBottom"] > *,
[data-testid="stBottom"] > * > *,
[data-testid="stBottom"] > * > * > *,
[data-testid="stBottom"] section {
  background-color: #0D1117 !important;
}
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] > div > div {
  background-color: #161B22 !important;
  border-color: #30363D !important;
}
[data-testid="stChatInput"] .e1vtqrcf1 {
  background-color: #161B22 !important;
  border-color: #30363D !important;
}
[data-testid="stChatInputTextArea"] {
  background-color: transparent !important;
  color: #E6EDF3 !important;
  -webkit-text-fill-color: #E6EDF3 !important;
  caret-color: #E6EDF3 !important;
}
[data-testid="stChatInputTextArea"]::placeholder {
  color: #8B949E !important;
  opacity: 1 !important;
}
[data-testid="stChatInput"] button { background: #E74C3C !important; }
[data-testid="stChatInput"] button:hover { background: #C0392B !important; }

/* ── Expanders (source + suggestions) ── */
[data-testid="stExpander"],
[data-testid="stExpanderDetails"] {
  background: #161B22 !important;
  border-color: #30363D !important;
  color: #E6EDF3 !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] p,
[data-testid="stExpander"] span {
  color: #8B949E !important;
  -webkit-text-fill-color: #8B949E !important;
}
[data-testid="stExpander"] svg { fill: #8B949E !important; }

/* ── Buttons (secondary) ── */
[data-testid="stBaseButton-secondary"] {
  background: #1C2128 !important;
  color: #8B949E !important;
  border-color: #30363D !important;
}
[data-testid="stBaseButton-secondary"]:hover {
  background: #21262D !important;
  border-color: #FF7060 !important;
  color: #E6EDF3 !important;
}

/* ── Source badge & active pill ── */
.active-source-badge {
  background: #2D1B18 !important;
  border-color: rgba(255,112,96,0.35) !important;
  color: #FF7060 !important;
  -webkit-text-fill-color: #FF7060 !important;
}

/* ── Source cards ── */
.source-card {
  background: #161B22 !important;
  border-color: #30363D !important;
}
.source-card-title { color: #E6EDF3 !important; -webkit-text-fill-color: #E6EDF3 !important; }
.source-card-desc  { color: #8B949E !important; -webkit-text-fill-color: #8B949E !important; }
.source-card:hover { background: #1C2128 !important; border-color: rgba(255,112,96,0.5) !important; }
.source-card:not(.selected) { opacity: 0.78 !important; }
.source-card.selected {
  background: #2D1B18 !important;
  border: 3px solid #FF7060 !important;
  border-bottom: none !important;
  box-shadow: 0 0 0 4px rgba(255,112,96,0.15), 0 4px 16px rgba(0,0,0,0.4) !important;
  opacity: 1 !important;
  transform: translateY(-2px);
}
.source-card.selected .source-card-check { color:#FFFFFF; }
.source-card.dubai.selected {
  border-color: #4DD687 !important;
  box-shadow: 0 0 0 4px rgba(77,214,135,0.15), 0 4px 16px rgba(0,0,0,0.4) !important;
}
.source-card.dubai::before { background: linear-gradient(90deg,#1a7a43,#4DD687); }

/* ── Primary buttons — white text ── */
[data-testid="stBaseButton-primary"] > button,
[data-testid="stBaseButton-primary"] > button p,
[data-testid="stBaseButton-primary"] > button span {
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}

/* ── Suggestions ── */
.suggestion-chip {
  background: #1C2128 !important;
  border-color: #30363D !important;
  color: #8B949E !important;
  -webkit-text-fill-color: #8B949E !important;
}
.suggestion-chip:hover {
  background: #2D1B18 !important;
  border-color: #FF7060 !important;
  color: #FF7060 !important;
  -webkit-text-fill-color: #FF7060 !important;
}

/* ── Footer & source citation ── */
.hr-footer, .hr-footer strong, .hr-footer-meta, .hr-footer a {
  color: #7D8590 !important;
  -webkit-text-fill-color: #7D8590 !important;
}
.hr-footer { border-top-color: #21262D !important; }
.source-citation {
  color: #7D8590 !important;
  -webkit-text-fill-color: #7D8590 !important;
  border-color: #21262D !important;
}

/* ── Typography ── */
h1,h2,h3,h4,h5,h6 { color: #E6EDF3 !important; -webkit-text-fill-color: #E6EDF3 !important; }
p, li { color: #8B949E !important; }
a { color: #FF7060 !important; }
a:hover { color: #E74C3C !important; }
.main-title {
  background: linear-gradient(135deg,#E74C3C 0%,#FF6B5B 100%);
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent !important;
}
code, pre { background: #1C2128 !important; border-color: #30363D !important; color: #FF7060 !important; }

/* ── Alerts / spinners ── */
[data-testid="stAlert"] { background:#1C2128!important; color:#E6EDF3!important; border-color:#30363D!important; }
[data-testid="stSpinner"] { color: #FF7060 !important; }

/* ── Social links ── */
.social-link { background: #1C2128; border-color: #30363D; }
.social-link:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.5); }

/* ── Misc ── */
.mini-header { background: #161B22 !important; border-bottom-color: #30363D !important; color: #E6EDF3 !important; -webkit-text-fill-color: #E6EDF3 !important; }
.hr-header-icon svg circle, .hr-header-icon svg path { opacity:1 !important; }
.thinking-dot { background: #E74C3C; }
[data-testid="stFeedback"] button { color: #8B949E !important; background: #1C2128 !important; border-color: #30363D !important; }
[data-testid="stFeedback"] button[aria-pressed="true"]:first-child { color:#27AE60!important; background:rgba(39,174,96,0.14)!important; border-color:rgba(39,174,96,0.5)!important; }
[data-testid="stFeedback"] button[aria-pressed="true"]:last-child { color:#FF7060!important; background:rgba(255,112,96,0.14)!important; border-color:rgba(255,112,96,0.5)!important; }
[data-testid="stToggle"] label { color: #8B949E !important; }

/* ── Suggestion chips — white text on buttons in dark mode ── */
[data-testid="stButton"] > button {
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}

/* ── Control bar (dark) ── */
.st-key-ctrl_bar [data-testid="stHorizontalBlock"] {
  background: transparent !important;
}
.st-key-btn_theme button,
.st-key-btn_lang  button {
  background: #1C2128 !important;
  border-color: #30363D !important;
  color: #8B949E !important;
  -webkit-text-fill-color: #8B949E !important;
}
.st-key-btn_theme button:hover,
.st-key-btn_lang  button:hover {
  background: #21262D !important;
  border-color: #FF7060 !important;
  color: #E6EDF3 !important;
  -webkit-text-fill-color: #E6EDF3 !important;
}

/* ── Loading spinner (dark) ── */
[data-testid="stSpinner"] > div,
[data-testid="stSpinnerContainer"],
div[aria-live="polite"] > div {
  background: #161B22 !important;
  color: #E6EDF3 !important;
}
[data-testid="stSpinner"] { color: #FF7060 !important; }
</style>
"""


def inject_css(css_path: Path) -> None:
    """Inject the main stylesheet into Streamlit."""
    try:
        css = css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        st.warning("⚠️ style.css not found — the app will render without custom styling.")
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def inject_dark_mode() -> None:
    """Inject dark-mode CSS overrides (no JS required)."""
    st.markdown(_DARK_CSS, unsafe_allow_html=True)


def inject_ui_controls() -> None:
    """Render Dark/Light and Language toggles using native Streamlit buttons."""
    # Handled directly in app_main.py via st.columns
    pass
