"""UI helpers: CSS injection + Dark/Light mode."""
from __future__ import annotations
from pathlib import Path
import streamlit as st

_DARK_CSS = """
<style>
/* ── Dark mode: CSS variable overrides (aligned with V3 design system) ── */
:root {
  --bg-app:               #0F1117;
  --bg-app-rgb:           15,17,23;
  --bg-surface:           #1A1D2E;
  --bg-surface-2:         #252840;
  --bg-surface-hover:     #2D3561;
  --bg-chat-user:         #3A2221;
  --bg-chat-bot:          #1A1D2E;
  --bg-card:              #1A1D2E;
  --bg-card-hover:        #252840;
  --bg-card-selected:     #3A2221;
  --bg-input:             #1A1D2E;
  --bg-badge:             #3A2221;
  --text-primary:         #F7FAFC;
  --text-secondary:       #CBD5E0;
  --text-muted:           #718096;
  --text-inverse:         #0F1117;
  --text-brand:           #FF7060;
  --border-default:       #2D3561;
  --border-subtle:        #1F2547;
  --border-focus:         #E74C3C;
  --border-card:          #2D3561;
  --border-card-selected: #E74C3C;
  --border-input:         #3D4575;
  --shadow-xs:            0 1px 3px rgba(0,0,0,0.30);
  --shadow-sm:            0 2px 8px rgba(0,0,0,0.40);
  --shadow-md:            0 4px 20px rgba(0,0,0,0.50);
  --shadow-lg:            0 12px 40px rgba(0,0,0,0.65);
  --shadow-xl:            0 24px 48px rgba(0,0,0,0.75);
  --shadow-focus:         0 0 0 3px rgba(231,76,60,0.25);
  --shadow-card-hover:    0 8px 28px rgba(0,0,0,0.55);
  --scrollbar-track:      #1A1D2E;
  --scrollbar-thumb:      #2D3561;
  --scrollbar-thumb-hover:#3D4575;
  --color-dubai:          #4DD687;
  --color-dubai-border:   rgba(77,214,135,0.35);
  --bg-dubai-badge:       rgba(77,214,135,0.10);
  --border-chat-user:     rgba(255,112,96,0.22);
}

:root,
[data-theme="dark"] {
  color-scheme: dark;
}

/* ── App & page background ── */
[data-testid="stApp"],
[data-testid="stMain"],
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stAppToolbar"],
[data-testid="stDecoration"],
.main, section.main, .block-container,
[data-testid="stAppViewContainer"],
[data-testid="stVerticalBlock"],
[data-testid="stMainBlockContainer"] {
  background-color: #0F1117 !important;
  color: #F7FAFC !important;
}
[data-testid="stHeader"] {
  background: #0F1117 !important;
  border-bottom: none !important;
}

/* ── Fixed header dark background ── */
.hr-header {
  background: rgba(15,17,23,0.95) !important;
  border-bottom-color: #1F2547 !important;
  box-shadow: 0 2px 20px rgba(0,0,0,0.40) !important;
}

/* ── Chat bubbles — explicit overrides (Streamlit injects its own bg) ── */
[data-testid="stChatMessage"] {
  background: #1A1D2E !important;
  border-color: #2D3561 !important;
}
[data-testid="stChatMessage"] > div,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
  background-color: transparent !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  background: #3A2221 !important;
  border-color: rgba(255,112,96,0.22) !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) > div,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stMarkdownContainer"] {
  background-color: #3A2221 !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
  background: #1A1D2E !important;
  border-color: #2D3561 !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) > div,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stMarkdownContainer"] {
  background-color: #1A1D2E !important;
}
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] strong {
  color: #F7FAFC !important;
  -webkit-text-fill-color: #F7FAFC !important;
}
[data-testid="stChatMessage"] code {
  background: #252840 !important;
  color: #FF7060 !important;
}
[data-testid="chatAvatarIcon-assistant"] {
  background: linear-gradient(135deg, #C0392B, #E74C3C) !important;
  border-color: #2D3561 !important;
}

/* ── Chat input outer container — aggressive override ── */
[data-testid="stBottom"],
[data-testid="stBottom"] > *,
[data-testid="stBottom"] > * > *,
[data-testid="stBottom"] > * > * > *,
[data-testid="stBottom"] section {
  background-color: #0F1117 !important;
}
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] > div > div {
  background-color: #1A1D2E !important;
  border-color: #3D4575 !important;
  color: #F7FAFC !important;
}
[data-testid="stChatInput"] .e1vtqrcf1 {
  background-color: #1A1D2E !important;
  border-color: #3D4575 !important;
}
[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stChatInput"] [data-baseweb="base-input"],
[data-testid="stChatInput"] [data-baseweb="input"],
[data-testid="stChatInput"] [data-baseweb="textarea"] > div,
[data-testid="stChatInput"] [data-baseweb="base-input"] > div,
[data-testid="stChatInput"] [data-baseweb="input"] > div {
  background-color: #1A1D2E !important;
  border-color: transparent !important;
  color: #F7FAFC !important;
}
[data-testid="stChatInputTextArea"],
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] input,
[data-testid="stChatInput"] [contenteditable="true"] {
  background-color: #1A1D2E !important;
  color: #F7FAFC !important;
  -webkit-text-fill-color: #F7FAFC !important;
  caret-color: #FF7060 !important;
  border-color: transparent !important;
  box-shadow: none !important;
}
[data-testid="stChatInputTextArea"]::placeholder,
[data-testid="stChatInput"] textarea::placeholder,
[data-testid="stChatInput"] input::placeholder {
  color: #718096 !important;
  -webkit-text-fill-color: #718096 !important;
  opacity: 1 !important;
}
[data-testid="stChatInput"]:focus-within,
[data-testid="stChatInput"]:focus-within > div,
[data-testid="stChatInput"]:focus-within > div > div {
  border-color: rgba(255,112,96,0.65) !important;
  box-shadow: 0 0 0 3px rgba(231,76,60,0.20), 0 8px 32px rgba(0,0,0,0.50) !important;
}
[data-testid="stChatInput"] button {
  background: #E74C3C !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}
[data-testid="stChatInput"] button:hover { background: #C0392B !important; }

/* ── Expanders (source + suggestions) ── */
[data-testid="stExpander"],
[data-testid="stExpanderDetails"] {
  background: #1A1D2E !important;
  border-color: #2D3561 !important;
  color: #F7FAFC !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] p,
[data-testid="stExpander"] span {
  color: #CBD5E0 !important;
  -webkit-text-fill-color: #CBD5E0 !important;
}
[data-testid="stExpander"] svg { fill: #718096 !important; }

/* ── Buttons (secondary) ── */
[data-testid="stBaseButton-secondary"] {
  background: #1A1D2E !important;
  color: #CBD5E0 !important;
  border-color: #2D3561 !important;
  -webkit-text-fill-color: #CBD5E0 !important;
}
[data-testid="stBaseButton-secondary"]:hover {
  background: #252840 !important;
  border-color: #FF7060 !important;
  color: #F7FAFC !important;
  -webkit-text-fill-color: #F7FAFC !important;
}

/* ── Source selector ── */
.st-key-source_selectbox [data-testid="stSelectbox"],
.st-key-source_selectbox [data-baseweb="select"],
.st-key-source_selectbox [data-baseweb="select"] > div {
  background: #1A1D2E !important;
  border-color: #2D3561 !important;
  color: #F7FAFC !important;
}
.st-key-source_selectbox [data-baseweb="select"] div,
.st-key-source_selectbox [data-baseweb="select"] span,
.st-key-source_selectbox [data-baseweb="select"] svg {
  color: #F7FAFC !important;
  fill: #CBD5E0 !important;
  -webkit-text-fill-color: #F7FAFC !important;
}
[data-baseweb="popover"],
[data-baseweb="popover"] ul,
[data-baseweb="menu"] {
  background: #1A1D2E !important;
  border-color: #2D3561 !important;
  color: #F7FAFC !important;
}
[data-baseweb="menu"] li,
[role="option"] {
  background: #1A1D2E !important;
  color: #F7FAFC !important;
  -webkit-text-fill-color: #F7FAFC !important;
}
[data-baseweb="menu"] li:hover,
[role="option"]:hover {
  background: #252840 !important;
}

/* ── Source badge & active pill ── */
.active-source-badge {
  background: #3A2221 !important;
  border-color: rgba(255,112,96,0.35) !important;
  color: #FF7060 !important;
  -webkit-text-fill-color: #FF7060 !important;
}

/* ── Source cards ── */
.source-card {
  background: #1A1D2E !important;
  border-color: #2D3561 !important;
}
.source-card-title { color: #F7FAFC !important; -webkit-text-fill-color: #F7FAFC !important; }
.source-card-desc  { color: #718096 !important; -webkit-text-fill-color: #718096 !important; }
.source-card:hover { background: #252840 !important; border-color: rgba(255,112,96,0.50) !important; }
.source-card:not(.selected) { opacity: 0.78 !important; }
.source-card.selected {
  background: #3A2221 !important;
  border: 3px solid #FF7060 !important;
  border-bottom: none !important;
  box-shadow: 0 0 0 3px rgba(255,112,96,0.15), 0 4px 16px rgba(0,0,0,0.45) !important;
  opacity: 1 !important;
  transform: translateY(-2px);
}
.source-card.selected .source-card-check { color: #FFFFFF; }
.source-card.dubai.selected {
  border-color: #4DD687 !important;
  box-shadow: 0 0 0 3px rgba(77,214,135,0.15), 0 4px 16px rgba(0,0,0,0.45) !important;
}
.source-card.dubai::before { background: linear-gradient(90deg, #1a7a43, #4DD687); }

/* ── Primary buttons — white text ── */
[data-testid="stBaseButton-primary"] > button,
[data-testid="stBaseButton-primary"] > button p,
[data-testid="stBaseButton-primary"] > button span {
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}

/* ── Suggestions ── */
.suggestion-chip {
  background: #252840 !important;
  border-color: #2D3561 !important;
  color: #CBD5E0 !important;
  -webkit-text-fill-color: #CBD5E0 !important;
}
.suggestion-chip:hover {
  background: #3A2221 !important;
  border-color: #FF7060 !important;
  color: #FF7060 !important;
  -webkit-text-fill-color: #FF7060 !important;
}
[class*="st-key-sugg_row"] [data-testid="stButton"] > button,
[class*="st-key-sugg_row"] [data-testid="stBaseButton-secondary"] {
  background: #1A1D2E !important;
  border: 1.5px solid #2D3561 !important;
  color: #CBD5E0 !important;
  -webkit-text-fill-color: #CBD5E0 !important;
  box-shadow: var(--shadow-xs) !important;
}
[class*="st-key-sugg_row"] [data-testid="stButton"] > button p,
[class*="st-key-sugg_row"] [data-testid="stButton"] > button span {
  color: #CBD5E0 !important;
  -webkit-text-fill-color: #CBD5E0 !important;
}
[class*="st-key-sugg_row"] [data-testid="stButton"] > button:hover,
[class*="st-key-sugg_row"] [data-testid="stBaseButton-secondary"]:hover {
  background: #3A2221 !important;
  border-color: rgba(255,112,96,0.62) !important;
  color: #FF7060 !important;
  -webkit-text-fill-color: #FF7060 !important;
}

/* ── Footer & source citation ── */
.hr-footer, .hr-footer strong, .hr-footer-meta, .hr-footer a {
  color: #718096 !important;
  -webkit-text-fill-color: #718096 !important;
}
.hr-footer { border-top-color: #1F2547 !important; }
.source-citation {
  background: #1A1D2E !important;
  color: #CBD5E0 !important;
  -webkit-text-fill-color: #CBD5E0 !important;
  border-color: #2D3561 !important;
}

/* ── Typography ── */
h1,h2,h3,h4,h5,h6 { color: #F7FAFC !important; -webkit-text-fill-color: #F7FAFC !important; }
p, li { color: #CBD5E0 !important; }
a { color: #FF7060 !important; }
a:hover { color: #E74C3C !important; }
.main-title {
  background: linear-gradient(135deg, #E74C3C 0%, #FF6B5B 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent !important;
}
code, pre { background: #252840 !important; border-color: #2D3561 !important; color: #FF7060 !important; }

/* ── Alerts / spinners ── */
[data-testid="stAlert"] { background: #252840 !important; color: #F7FAFC !important; border-color: #2D3561 !important; }
[data-testid="stSpinner"] { color: #FF7060 !important; }

/* ── Social links ── */
.social-link { background: #252840 !important; border-color: #2D3561 !important; }
.social-link:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.55) !important; }

/* ── Misc ── */
.mini-header { background: #1A1D2E !important; border-bottom-color: #2D3561 !important; color: #F7FAFC !important; -webkit-text-fill-color: #F7FAFC !important; }
.hr-header-icon svg circle, .hr-header-icon svg path { opacity: 1 !important; }
.thinking-dot { background: #FF7060; }
[data-testid="stFeedback"] button { color: #718096 !important; background: #252840 !important; border-color: #2D3561 !important; }
[data-testid="stFeedback"] button[aria-pressed="true"]:first-child { color: #38A169 !important; background: rgba(56,161,105,0.14) !important; border-color: rgba(56,161,105,0.45) !important; }
[data-testid="stFeedback"] button[aria-pressed="true"]:last-child { color: #FF7060 !important; background: rgba(255,112,96,0.14) !important; border-color: rgba(255,112,96,0.45) !important; }
[data-testid="stToggle"] label { color: #718096 !important; }

/* ── Primary buttons keep white text in dark mode ── */
[data-testid="stBaseButton-primary"] > button,
[data-testid="stBaseButton-primary"] > button p,
[data-testid="stBaseButton-primary"] > button span {
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}

/* ── Topbar (dark) ── */
.hr-topbar { border-bottom-color: #1F2547 !important; }
.hr-topbar-name { color: #F7FAFC !important; -webkit-text-fill-color: #F7FAFC !important; }
.hr-topbar-dot, .hr-topbar-sub { color: #4A5568 !important; -webkit-text-fill-color: #4A5568 !important; }

/* ── Control bar (dark) ── */
.st-key-ctrl_bar [data-testid="stHorizontalBlock"] {
  background: transparent !important;
}
.st-key-btn_theme button,
.st-key-btn_lang  button {
  background: #252840 !important;
  border-color: #2D3561 !important;
  color: #718096 !important;
  -webkit-text-fill-color: #718096 !important;
}
.st-key-btn_theme button:hover,
.st-key-btn_lang  button:hover {
  background: #2D3561 !important;
  border-color: #FF7060 !important;
  color: #F7FAFC !important;
  -webkit-text-fill-color: #F7FAFC !important;
}

/* ── Loading spinner (dark) ── */
[data-testid="stSpinner"] > div,
[data-testid="stSpinnerContainer"],
div[aria-live="polite"] > div {
  background: #1A1D2E !important;
  color: #F7FAFC !important;
}
[data-testid="stSpinner"] { color: #FF7060 !important; }
</style>
"""


_CSS_CACHE: dict[str, str] = {}


def inject_css(css_path: Path) -> None:
    """Inject the main stylesheet into Streamlit.

    Caches the file read in a module-level dict (process-scoped) so repeated
    calls across reruns pay only a dict lookup instead of a disk read.
    """
    key = str(css_path)
    if key not in _CSS_CACHE:
        try:
            _CSS_CACHE[key] = css_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            st.warning("⚠️ style.css not found — the app will render without custom styling.")
            return
    st.markdown(f"<style>{_CSS_CACHE[key]}</style>", unsafe_allow_html=True)


def inject_dark_mode() -> None:
    """Inject dark-mode CSS overrides (no JS required)."""
    st.markdown(_DARK_CSS, unsafe_allow_html=True)


def inject_ui_controls() -> None:
    """Render Dark/Light and Language toggles using native Streamlit buttons."""
    # Handled directly in app_main.py via st.columns
    pass
