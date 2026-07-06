"""
Admin Dashboard — password-gated control panel.

Access: /admin_dashboard (URL-only, not shown in sidebar navigation).

Tabs:
  📋 Logs           — Supabase + local JSONL viewer
  📁 Manage Docs    — upload / delete files per source, rebuild index
  ➕ Add Source     — create new knowledge source end-to-end
  ⚙️  Settings       — toggle source visibility (fully dynamic)
  🐛 Debug          — runtime diagnostics with actionable index status
"""
from __future__ import annotations

import datetime
import os
import re
import sys
from pathlib import Path

import streamlit as st

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_secret(key: str, default: str = "") -> str:
    try:
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


def _require_password() -> bool:
    if st.session_state.get("admin_authed"):
        return True
    st.title("🔐 Admin Login")
    pwd = st.text_input("Password", type="password", key="admin_pwd_input")
    if st.button("Login", type="primary"):
        correct = _get_secret("ADMIN_PASSWORD")
        if correct and pwd == correct:
            st.session_state.admin_authed = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


def _safe_filename(name: str) -> str:
    """Strip path separators and null bytes; keep only safe characters."""
    name = Path(name).name  # strip any directory component
    name = re.sub(r"[^\w\s\-.]", "_", name)
    return name[:200]


def _index_status(db_dir: Path, docs_dir: Path) -> tuple[str, str]:
    """Return (status_emoji, detail) for a source's FAISS index."""
    if not docs_dir.exists():
        return "❌", f"Docs folder missing: {docs_dir.resolve()}"
    supported = [f for f in docs_dir.iterdir() if f.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}]
    if not supported:
        return "⚠️", f"No supported documents in {docs_dir.resolve()}"
    index_file = db_dir / "index.faiss"
    if not index_file.exists():
        return "⚠️", f"Index not built yet — {len(supported)} doc(s) ready. Click 'Rebuild'."
    return "✅", f"{index_file.resolve()} ({len(supported)} source docs)"


# ── Main ──────────────────────────────────────────────────────────────────────

if not _require_password():
    st.stop()

st.title("📊 Admin Dashboard")

tab_logs, tab_docs, tab_add, tab_settings, tab_debug = st.tabs(
    ["📋 Logs", "📁 Manage Docs", "➕ Add Source", "⚙️ Settings", "🐛 Debug"]
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB: Logs
# ─────────────────────────────────────────────────────────────────────────────
with tab_logs:
    st.subheader("Query Logs")

    col_filter, col_limit, col_btn = st.columns([2, 1, 1])
    with col_filter:
        log_type_filter = st.selectbox(
            "Log type",
            options=["all", "unanswered", "feedback", "admin_action"],
            key="log_type_filter",
        )
    with col_limit:
        log_limit = st.number_input("Max rows", min_value=10, max_value=1000, value=200, step=10, key="log_limit")
    with col_btn:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        fetch_btn = st.button("🔄 Fetch Logs", type="primary", use_container_width=True)

    if fetch_btn:
        from core.db_logger import fetch_logs
        ltype = log_type_filter if log_type_filter != "all" else None
        with st.spinner("Fetching…"):
            rows, err = fetch_logs(log_type=ltype, limit=int(log_limit))
        if err:
            st.error(f"Error: {err}")
        elif not rows:
            st.info("No rows found.")
        else:
            import pandas as pd
            df = pd.DataFrame(rows)
            st.success(f"Fetched {len(df)} rows.")
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download CSV",
                data=csv,
                file_name=f"logs_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

    st.divider()
    st.subheader("Local Fallback Logs")
    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    jsonl_files = sorted(logs_dir.glob("*.jsonl")) if logs_dir.exists() else []
    if not jsonl_files:
        st.info("No local JSONL log files found.")
    else:
        for jf in jsonl_files:
            with st.expander(f"📄 {jf.name}"):
                try:
                    lines = jf.read_text(encoding="utf-8").splitlines()[-100:]
                    st.code("\n".join(lines), language="json")
                except Exception as exc:
                    st.error(f"Could not read: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Manage Docs
# ─────────────────────────────────────────────────────────────────────────────
with tab_docs:
    st.subheader("Manage Policy Documents")

    try:
        from core.settings_store import get_enabled_sources
        _all_sources = get_enabled_sources()
    except Exception:
        _all_sources = ["company", "dubai_hr"]

    from config import get_settings as _get_settings
    _s = _get_settings()

    selected_source = st.selectbox(
        "Knowledge source",
        options=_all_sources,
        key="manage_docs_source",
    )

    _docs_dir = _s.docs_dir_for(selected_source)
    _db_dir   = _s.db_dir_for(selected_source)
    _docs_dir.mkdir(parents=True, exist_ok=True)

    # ── Upload ────────────────────────────────────────────────────────────────
    st.markdown("#### Upload Files")
    uploaded = st.file_uploader(
        "Select policy files (PDF, DOCX, TXT, MD)",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key=f"uploader_{selected_source}",
    )

    if uploaded:
        _existing = {f.name for f in _docs_dir.iterdir() if f.is_file()}
        _conflicts = [f.name for f in uploaded if f.name in _existing]

        if _conflicts and not st.session_state.get(f"overwrite_ok_{selected_source}"):
            st.warning(f"These files already exist and will be **overwritten**: {', '.join(_conflicts)}")
            if st.button("✅ Confirm overwrite", key=f"confirm_ow_{selected_source}"):
                st.session_state[f"overwrite_ok_{selected_source}"] = True
                st.rerun()
        else:
            if st.button("💾 Save Files", type="primary", key=f"save_files_{selected_source}"):
                from core.db_logger import log_admin_action
                saved, failed = [], []
                for uf in uploaded:
                    safe = _safe_filename(uf.name)
                    try:
                        (_docs_dir / safe).write_bytes(uf.read())
                        log_admin_action("upload", selected_source, safe)
                        saved.append(safe)
                    except Exception as exc:
                        failed.append(f"{safe}: {exc}")

                if saved:
                    st.success(f"Saved {len(saved)} file(s): {', '.join(saved)}")
                if failed:
                    st.error("Failed: " + "; ".join(failed))

                st.session_state.pop(f"overwrite_ok_{selected_source}", None)

                # Auto-rebuild after upload
                st.info("Rebuilding index…")
                from core.rag_engine import build_source_index
                with st.spinner("Building FAISS index…"):
                    ok, msg = build_source_index(_s, selected_source)
                if ok:
                    st.success(f"Index rebuilt: {msg}")
                    log_admin_action("rebuild", selected_source)
                else:
                    st.error(f"Index rebuild failed: {msg}")
                # Invalidate the cached engine so next query loads fresh index
                st.cache_resource.clear()
                st.rerun()

    # ── Existing files ────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Existing Files")

    _doc_files = sorted([
        f for f in _docs_dir.iterdir()
        if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}
    ]) if _docs_dir.exists() else []

    if not _doc_files:
        st.info(f"No documents in `{_docs_dir.name}/`.")
    else:
        st.caption(f"{len(_doc_files)} file(s) in `{_docs_dir.resolve()}`")
        for _f in _doc_files:
            col_name, col_size, col_del = st.columns([5, 1, 1])
            with col_name:
                st.markdown(f"📄 `{_f.name}`")
            with col_size:
                st.caption(f"{_f.stat().st_size // 1024} KB")
            with col_del:
                if st.button("🗑️", key=f"del_{selected_source}_{_f.name}", help="Delete"):
                    st.session_state[f"confirm_del_{selected_source}_{_f.name}"] = True

            if st.session_state.get(f"confirm_del_{selected_source}_{_f.name}"):
                st.warning(f"Delete `{_f.name}`?")
                col_y, col_n = st.columns(2)
                with col_y:
                    if st.button("Yes, delete", key=f"yes_del_{selected_source}_{_f.name}", type="primary"):
                        from core.db_logger import log_admin_action
                        try:
                            _f.unlink()
                            log_admin_action("delete", selected_source, _f.name)
                            st.session_state.pop(f"confirm_del_{selected_source}_{_f.name}", None)
                            st.success(f"Deleted `{_f.name}`.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Delete failed: {exc}")
                with col_n:
                    if st.button("Cancel", key=f"no_del_{selected_source}_{_f.name}"):
                        st.session_state.pop(f"confirm_del_{selected_source}_{_f.name}", None)
                        st.rerun()

    # ── Manual rebuild ────────────────────────────────────────────────────────
    st.divider()
    if st.button("🔨 Rebuild Index Now", key=f"rebuild_{selected_source}", use_container_width=True):
        from core.db_logger import log_admin_action
        from core.rag_engine import build_source_index
        with st.spinner("Building FAISS index…"):
            ok, msg = build_source_index(_s, selected_source)
        if ok:
            st.success(msg)
            log_admin_action("rebuild", selected_source)
            st.cache_resource.clear()
        else:
            st.error(msg)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Add Source
# ─────────────────────────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Add New Knowledge Source")
    st.caption("Creates a new source end-to-end: folder → upload docs → build index → register in Supabase.")

    new_key = st.text_input(
        "Source key (slug)",
        placeholder="e.g. labour_law_ksa",
        help="Lowercase letters, digits, underscores. Must start with a letter.",
        key="new_source_key",
    )
    new_display = st.text_input(
        "Display name",
        placeholder="e.g. Saudi Labour Law",
        key="new_source_display",
    )

    from core.settings_store import is_valid_source_key
    if new_key:
        if is_valid_source_key(new_key):
            st.success(f"✅ Key `{new_key}` is valid.")
        else:
            st.error("Invalid key. Use only lowercase letters, digits, and underscores. Must start with a letter.")

    new_files = st.file_uploader(
        "Initial documents (optional — you can add more later)",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key="new_source_files",
    )

    if st.button("➕ Create Source", type="primary", key="create_source_btn"):
        from config import get_settings as _get_settings
        from core.settings_store import get_enabled_sources, register_source
        from core.db_logger import log_admin_action

        _s2 = _get_settings()

        # Validate key
        if not new_key:
            st.error("Please enter a source key.")
        elif not is_valid_source_key(new_key):
            st.error("Invalid source key format.")
        elif not new_display.strip():
            st.error("Please enter a display name.")
        else:
            # Check for duplicate
            existing = get_enabled_sources()
            if new_key in existing:
                st.warning(f"Source `{new_key}` is already registered.")
            else:
                _new_docs_dir = _s2.docs_dir_for(new_key)
                _new_db_dir   = _s2.db_dir_for(new_key)
                _new_docs_dir.mkdir(parents=True, exist_ok=True)

                # Save uploaded files
                _saved_files = []
                for uf in (new_files or []):
                    safe = _safe_filename(uf.name)
                    try:
                        (_new_docs_dir / safe).write_bytes(uf.read())
                        _saved_files.append(safe)
                    except Exception as exc:
                        st.error(f"Failed to save {uf.name}: {exc}")

                # Build index if files were provided
                _index_ok = True
                if _saved_files:
                    st.info(f"Saved {len(_saved_files)} file(s). Building index…")
                    from core.rag_engine import build_source_index
                    with st.spinner("Building FAISS index…"):
                        _index_ok, _index_msg = build_source_index(_s2, new_key)
                    if _index_ok:
                        st.success(f"Index built: {_index_msg}")
                    else:
                        st.warning(f"Index build failed (you can rebuild later): {_index_msg}")

                # Register in Supabase
                err = register_source(new_key)
                if err:
                    st.error(f"Failed to register source: {err}")
                else:
                    log_admin_action("add_source", new_key, new_display)
                    st.success(f"Source `{new_key}` ({new_display}) created and registered!")
                    st.info("The new source will appear in the main app after the 60-second settings cache expires.")
                    # Invalidate caches
                    st.cache_data.clear()
                    st.cache_resource.clear()

                    # Clear inputs
                    for k in ("new_source_key", "new_source_display"):
                        st.session_state.pop(k, None)
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Settings
# ─────────────────────────────────────────────────────────────────────────────
with tab_settings:
    st.subheader("Source Visibility")
    st.caption("Toggle which knowledge sources are available to end users.")

    try:
        from core.settings_store import get_enabled_sources, set_enabled_sources
        _all_src = get_enabled_sources()

        # Get all known sources (enabled + any dirs that exist locally)
        from config import get_settings as _get_settings
        _cfg = _get_settings()
        _known = list(_all_src)

        # Build a toggle per source
        _new_enabled: list[str] = []
        for _src in _known:
            _on = st.toggle(
                f"{'🏢' if _src == 'company' else '🇦🇪' if _src == 'dubai_hr' else '📋'} {_src.replace('_', ' ').title()}",
                value=_src in _all_src,
                key=f"toggle_{_src}",
            )
            if _on:
                _new_enabled.append(_src)

        if st.button("💾 Save Settings", type="primary", key="save_settings_btn"):
            if not _new_enabled:
                st.warning("At least one source must remain enabled.")
            else:
                _err = set_enabled_sources(_new_enabled)
                if _err:
                    st.error(f"Error: {_err}")
                else:
                    st.success(f"Saved: {_new_enabled}")

    except ImportError:
        st.warning("`core.settings_store` not found.")
    except Exception as exc:
        st.error(f"Settings error: {exc}")

    st.divider()
    st.subheader("FAISS Index Management")

    try:
        from core.settings_store import get_enabled_sources as _get_srcs
        from config import get_settings as _get_settings
        _cfg2 = _get_settings()
        _srcs2 = _get_srcs()

        _idx_cols = st.columns(min(len(_srcs2), 3))
        for _ci, _src2 in enumerate(_srcs2):
            with _idx_cols[_ci % 3]:
                if st.button(f"🗑️ Clear {_src2} Index", key=f"clear_idx_{_src2}", use_container_width=True):
                    import shutil
                    _d = _cfg2.db_dir_for(_src2)
                    if _d.exists():
                        shutil.rmtree(_d)
                        st.success(f"{_src2} index cleared — rebuilds on next query.")
                    else:
                        st.info(f"No index found for {_src2}.")
    except Exception as exc:
        st.error(f"Index management error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: Debug
# ─────────────────────────────────────────────────────────────────────────────
with tab_debug:
    st.subheader("Runtime Diagnostics")

    if st.button("🔍 Run Diagnostics", type="primary", key="run_diag_btn"):
        results: list[tuple[str, str, str]] = []

        results.append(("Python", "✅", sys.version.split()[0]))
        results.append(("Streamlit", "✅", st.__version__))

        for sec_key in ("GROQ_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "ADMIN_PASSWORD"):
            val = _get_secret(sec_key)
            results.append((
                f"Secret: {sec_key}",
                "✅" if val else "⚠️",
                f"{val[:6]}…" if val else "not set",
            ))

        try:
            from core.db_logger import _get_client, get_logging_mode
            client = _get_client()
            results.append(("Supabase client", "✅" if client else "⚠️", get_logging_mode()))
        except Exception as exc:
            results.append(("Supabase client", "❌", str(exc)))

        try:
            from langchain_community.embeddings import FastEmbedEmbeddings  # noqa: F401
            results.append(("FastEmbedEmbeddings import", "✅", "ok"))
        except Exception as exc:
            results.append(("FastEmbedEmbeddings import", "❌", str(exc)))

        try:
            from config import get_settings
            from core.settings_store import get_enabled_sources
            _s3  = get_settings()
            _src3 = get_enabled_sources()
            results.append(("Config BASE_DIR", "✅", str(_s3.docs_dir.parent.resolve())))
            results.append(("Enabled sources", "✅", str(_src3)))

            for _src in _src3:
                _dd  = _s3.docs_dir_for(_src)
                _dbd = _s3.db_dir_for(_src)
                _em, _det = _index_status(_dbd, _dd)
                results.append((f"Index: {_src}", _em, _det))

        except Exception as exc:
            results.append(("Config / source check", "❌", str(exc)))

        import pandas as pd
        df = pd.DataFrame(results, columns=["Check", "Status", "Detail"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Per-source build buttons ──────────────────────────────────────────────
    st.divider()
    st.subheader("Build Missing Indexes")
    st.caption("Use these if Run Diagnostics shows ⚠️ for an index.")

    try:
        from config import get_settings as _gs4
        from core.settings_store import get_enabled_sources as _ges4
        _s4    = _gs4()
        _srcs4 = _ges4()
        _bcols = st.columns(min(len(_srcs4), 3))
        for _bi, _bsrc in enumerate(_srcs4):
            with _bcols[_bi % 3]:
                if st.button(f"🔨 Build {_bsrc}", key=f"build_{_bsrc}", use_container_width=True):
                    from core.db_logger import log_admin_action
                    from core.rag_engine import build_source_index
                    with st.spinner(f"Building {_bsrc} index…"):
                        _bok, _bmsg = build_source_index(_s4, _bsrc)
                    if _bok:
                        st.success(_bmsg)
                        log_admin_action("rebuild", _bsrc)
                        st.cache_resource.clear()
                    else:
                        st.error(_bmsg)
    except Exception as exc:
        st.error(f"Build section error: {exc}")

    st.divider()
    st.subheader("Session State")
    if st.button("👁️ Show Session State", key="show_session"):
        safe = {k: v for k, v in st.session_state.items() if "password" not in k.lower()}
        st.json(safe)

    st.divider()
    st.subheader("Environment Variables")
    if st.button("👁️ Show Env Vars", key="show_env"):
        safe_keys = ["STREAMLIT_SERVER_PORT", "HOME", "PATH", "PYTHONPATH", "HOSTNAME"]
        st.json({k: os.environ.get(k, "(not set)") for k in safe_keys})
